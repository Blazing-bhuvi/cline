"""BLO verification workflow, routing, escalation, and FIR trigger for MyVote-D.

State machine (per flag):

    FLAGGED -> ASSIGNED -> BLO_REVIEW -> CONFIRMED
                                     \\-> REJECTED

Escalation (blind double-review):
    A HIGH-confidence flag that the FIRST BLO rejects is escalated to a second,
    independent reviewer. If the second reviewer overturns (i.e. confirms the
    flag is genuine), we:
      * generate a "Negligence Review Dossier" (JSON + PDF) for the ERO, and
      * trigger a FIR-evidence flag (a clearly-rejected-then-confirmed genuine
        anomaly is strong evidence of first-reviewer negligence).

Safety invariants enforced here (Phase 3 hardening):
  * NO path deletes or mutates an Elector. Ever.
  * Every transition is validated against the state machine (no illegal jumps).
  * Every transition is written to the hash-chained audit log.
  * Concurrency: flag transitions use a row lock + re-check to avoid two
    reviewers acting on the same flag simultaneously (race guard).
  * Idempotency: a BLO cannot submit two round-1 reviews for the same flag.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from .audit import AuditChain
from .config import Config, get_config
from .enums import (AuditAction, BLOReviewDecision, ConfidenceTier, FlagState,
                    FlagCategory)
from .models import BLOReviewSubmission, DiscrepancyFlag
from .timeutil import utcnow


class WorkflowError(Exception):
    """Raised on an illegal state transition or invalid input."""


# Legal transitions allowed by the state machine.
_ALLOWED = {
    FlagState.FLAGGED: {FlagState.ASSIGNED},
    FlagState.ASSIGNED: {FlagState.BLO_REVIEW},
    FlagState.BLO_REVIEW: {FlagState.CONFIRMED, FlagState.REJECTED},
    FlagState.CONFIRMED: set(),
    FlagState.REJECTED: set(),
}


@dataclass
class WorkflowResult:
    flag: DiscrepancyFlag
    message: str
    escalated: bool = False
    fir_triggered: bool = False
    dossier_path: str | None = None


class VerificationWorkflow:
    """Coordinates flag routing, BLO review, escalation, and FIR triggers."""

    def __init__(self, session: Session, config: Config | None = None):
        self.session = session
        self.config = config or get_config()
        self.audit = AuditChain(session, self.config)

    # ------------------------------------------------------------------ #
    #  Internal helpers
    # ------------------------------------------------------------------ #
    def _log(self, *, actor, action, entity_id, payload=None):
        self.audit.append(actor=actor, action=action.value,
                          entity_type="discrepancy_flag", entity_id=str(entity_id),
                          payload=payload or {})

    def _get_flag_locked(self, flag_id: int) -> DiscrepancyFlag:
        """Fetch the flag with a row lock to serialise concurrent transitions."""
        flag = (self.session.query(DiscrepancyFlag)
                .filter(DiscrepancyFlag.id == flag_id)
                .with_for_update()
                .first())
        if flag is None:
            raise WorkflowError(f"Flag {flag_id} not found")
        return flag

    @staticmethod
    def _as_state(value) -> FlagState:
        return value if isinstance(value, FlagState) else FlagState(str(value))

    def _transition(self, flag: DiscrepancyFlag, to_state: FlagState) -> None:
        current = self._as_state(flag.state)
        if to_state not in _ALLOWED[current]:
            raise WorkflowError(
                f"Illegal transition {current.value} -> {to_state.value}")

    # ------------------------------------------------------------------ #
    #  Routing
    # ------------------------------------------------------------------ #
    def assign(self, flag_id: int, blo_id: str, actor: str = "system") -> WorkflowResult:
        """Route a FLAGGED discrepancy to a specific BLO. FLAGGED -> ASSIGNED."""
        flag = self._get_flag_locked(flag_id)
        self._transition(flag, FlagState.ASSIGNED)
        flag.assigned_blo_id = blo_id
        flag.assigned_at = utcnow()
        flag.state = FlagState.ASSIGNED.value
        self.session.flush()
        self._log(actor=actor, action=AuditAction.FLAG_ASSIGNED,
                  entity_id=flag.id,
                  payload={"blo_id": blo_id, "tier": self._tier_value(flag)})
        return WorkflowResult(flag=flag, message=f"Assigned to BLO {blo_id}")

    def start_review(self, flag_id: int, blo_id: str, actor: str) -> WorkflowResult:
        """BLO begins review. ASSIGNED -> BLO_REVIEW. Enforces assignment."""
        flag = self._get_flag_locked(flag_id)
        self._transition(flag, FlagState.BLO_REVIEW)
        # A BLO can only review a flag assigned to them.
        if flag.assigned_blo_id != blo_id:
            raise WorkflowError(
                f"BLO {blo_id} is not the assigned reviewer for flag {flag_id}")
        flag.state = FlagState.BLO_REVIEW.value
        self.session.flush()
        self._log(actor=actor, action=AuditAction.FLAG_ASSIGNED,
                  entity_id=flag.id,
                  payload={"blo_id": blo_id, "event": "review_started"})
        return WorkflowResult(flag=flag, message="BLO review started")

    # ------------------------------------------------------------------ #
    #  BLO review submission (+ blind double-review escalation)
    # ------------------------------------------------------------------ #
    def submit_review(self, flag_id: int, reviewer_id: str, decision: str,
                      *, notes: str = "", visited_house: bool = False,
                      voter_present: bool = False,
                      review_round: int = 1) -> WorkflowResult:
        """Record a BLO's physical-verification decision.

        Round 1 (first BLO):
          * CONFIRM -> flag CONFIRMED.
          * REJECT  -> if the flag is HIGH confidence, escalate to a second,
                       independent reviewer (needs_second_review=True, state
                       stays BLO_REVIEW). Otherwise flag REJECTED.

        Round 2 (second reviewer):
          * CONFIRM -> flag CONFIRMED AND first reviewer's rejection is
                       overturned -> generate a Negligence Review Dossier for
                       the ERO and trigger the FIR-evidence flag.
          * REJECT  -> flag REJECTED (first reviewer's rejection upheld).
        """
        flag = self._get_flag_locked(flag_id)
        current_state = self._as_state(flag.state)

        # --- Validations (Phase 3) ------------------------------------- #
        # 1. Invalid decision string -> clean WorkflowError (not a raw
        #    ValueError that would surface as an HTTP 500).
        try:
            decision_enum = (decision if isinstance(decision, BLOReviewDecision)
                             else BLOReviewDecision(str(decision).upper()))
        except (ValueError, KeyError) as exc:
            raise WorkflowError(f"Invalid review decision: {decision!r}") from exc

        # 2. Terminal-state guard: a CONFIRMED/REJECTED flag is closed and
        #    cannot be reviewed again (prevents re-review / double-count).
        if current_state in (FlagState.CONFIRMED, FlagState.REJECTED):
            raise WorkflowError(
                f"Flag {flag_id} is already {current_state.value} and cannot be "
                f"reviewed again")

        # 3. State-machine guard: a review requires the flag to be in
        #    BLO_REVIEW. A flag sitting at FLAGGED was never routed/started;
        #    auto-advance a legitimately ASSIGNED flag to BLO_REVIEW, but never
        #    allow a FLAGGED (unrouted) flag to be reviewed.
        if current_state == FlagState.ASSIGNED:
            # Only the assigned BLO may open the review (ASSIGNED -> BLO_REVIEW).
            if flag.assigned_blo_id != reviewer_id:
                raise WorkflowError(
                    f"Reviewer {reviewer_id} is not assigned to flag {flag_id}")
            self._transition(flag, FlagState.BLO_REVIEW)
            flag.state = FlagState.BLO_REVIEW.value
            self.session.flush()
            current_state = FlagState.BLO_REVIEW
        elif current_state != FlagState.BLO_REVIEW:
            raise WorkflowError(
                f"Flag {flag_id} must be routed and in review before a decision "
                f"(current state {current_state.value})")

        if review_round == 1 and flag.assigned_blo_id != reviewer_id:
            raise WorkflowError(
                f"Reviewer {reviewer_id} is not assigned to flag {flag_id}")

        # 4. Blind double-review independence: the second reviewer MUST be a
        #    different person from the first BLO who rejected the flag.
        if review_round == 2:
            first_reviewer = self._first_rejecter(flag_id)
            if first_reviewer is not None and first_reviewer == reviewer_id:
                raise WorkflowError(
                    "Second reviewer must be independent of the first reviewer "
                    f"({reviewer_id})")
        # Idempotency: no duplicate review for the same (flag, reviewer, round).
        existing = (self.session.query(BLOReviewSubmission)
                    .filter(BLOReviewSubmission.flag_id == flag_id,
                            BLOReviewSubmission.reviewer_id == reviewer_id,
                            BLOReviewSubmission.review_round == review_round)
                    .first())
        if existing is not None:
            raise WorkflowError(
                f"Reviewer {reviewer_id} already submitted a round-{review_round} "
                f"review for flag {flag_id}")
        if review_round == 2 and not flag.needs_second_review:
            raise WorkflowError(
                f"Flag {flag_id} is not awaiting a second review")
        if review_round == 2 and flag.second_reviewer_id not in (None, reviewer_id):
            raise WorkflowError(
                f"Reviewer {reviewer_id} is not the designated second reviewer")

        if review_round == 2 and flag.second_reviewer_id is None:
            flag.second_reviewer_id = reviewer_id
            self.session.flush()

        # Record the submission (append-only evidence).
        review = BLOReviewSubmission(
            flag_id=flag_id,
            reviewer_id=reviewer_id,
            review_round=review_round,
            decision=decision_enum,
            notes=notes,
            visited_house=visited_house,
            voter_present=voter_present,
        )
        self.session.add(review)
        self.session.flush()
        self._log(actor=reviewer_id, action=AuditAction.BLO_REVIEW_SUBMITTED,
                  entity_id=flag_id,
                  payload={"round": review_round, "decision": decision_enum.value,
                           "visited_house": visited_house,
                           "voter_present": voter_present})

        # --- Decision handling ----------------------------------------- #
        if decision_enum == BLOReviewDecision.CONFIRM:
            flag.state = FlagState.CONFIRMED.value
            flag.needs_second_review = False
            self.session.flush()
            if review_round == 2:
                # Overturn of a first-round rejection -> negligence + FIR.
                result = self._handle_overturn(flag, first_reviewer=self._first_rejecter(flag_id),
                                               second_reviewer=reviewer_id)
                self._log(actor=reviewer_id, action=AuditAction.FLAG_CONFIRMED,
                          entity_id=flag_id,
                          payload={"overturned_first_rejection": True})
                return result
            self._log(actor=reviewer_id, action=AuditAction.FLAG_CONFIRMED,
                      entity_id=flag_id, payload={"round": review_round})
            return WorkflowResult(flag=flag, message="Flag confirmed by BLO")

        # decision == REJECT
        if review_round == 1 and self._requires_double_review(flag):
            flag.needs_second_review = True
            # Keep state at BLO_REVIEW pending the second reviewer.
            flag.state = FlagState.BLO_REVIEW.value
            self.session.flush()
            self._log(actor=reviewer_id, action=AuditAction.FLAG_ESCALATED,
                      entity_id=flag_id,
                      payload={"reason": "high-confidence rejection escalated",
                               "tier": self._tier_value(flag)})
            return WorkflowResult(
                flag=flag,
                message=("HIGH-confidence rejection escalated to a second "
                         "independent reviewer"),
                escalated=True)
        # Plain rejection (round 1 non-high, or round 2 uphold).
        flag.state = FlagState.REJECTED.value
        flag.needs_second_review = False
        self.session.flush()
        self._log(actor=reviewer_id, action=AuditAction.FLAG_REJECTED,
                  entity_id=flag_id, payload={"round": review_round})
        return WorkflowResult(flag=flag, message="Flag rejected")


    # ------------------------------------------------------------------ #
    #  Escalation / FIR / dossier helpers
    # ------------------------------------------------------------------ #
    def _tier_value(self, flag: DiscrepancyFlag) -> str:
        tier = flag.tier
        return tier.value if isinstance(tier, ConfidenceTier) else str(tier)

    def _requires_double_review(self, flag: DiscrepancyFlag) -> bool:
        if not bool(self.config.get("workflow.double_review.enabled", True)):
            return False
        escalate_tiers = self.config.get(
            "workflow.double_review.escalate_on_reject_tiers", ["HIGH"])
        return self._tier_value(flag) in [str(t).upper() for t in escalate_tiers]

    def _first_rejecter(self, flag_id: int) -> str | None:
        review = (self.session.query(BLOReviewSubmission)
                  .filter(BLOReviewSubmission.flag_id == flag_id,
                          BLOReviewSubmission.review_round == 1)
                  .first())
        return review.reviewer_id if review else None

    def _handle_overturn(self, flag: DiscrepancyFlag, *,
                         first_reviewer: str | None,
                         second_reviewer: str) -> WorkflowResult:
        """A round-1 rejection was overturned by the round-2 confirmation.

        Generate the Negligence Review Dossier (JSON + PDF) for the ERO and set
        the FIR-evidence flag. NO voter record is deleted or altered.
        """
        dossier_path = None
        if bool(self.config.get("workflow.negligence_dossier.generate_on_overturn", True)):
            dossier_path = self.generate_negligence_dossier(
                flag, first_reviewer=first_reviewer, second_reviewer=second_reviewer)
            self._log(actor=second_reviewer, action=AuditAction.DOSSIER_GENERATED,
                      entity_id=flag.id,
                      payload={"dossier": dossier_path, "first_reviewer": first_reviewer})

        # FIR-evidence flag: a genuine anomaly that a BLO wrongly rejected.
        flag.fir_triggered = True
        self.session.flush()
        self._log(actor=second_reviewer, action=AuditAction.FIR_TRIGGERED,
                  entity_id=flag.id,
                  payload={"reason": "confirmed-after-rejection (negligence)",
                       "first_reviewer": first_reviewer})
        return WorkflowResult(
            flag=flag,
            message=("Round-1 rejection overturned; Negligence Review Dossier "
                     "generated and FIR-evidence flagged for the ERO."),
            escalated=True,
            fir_triggered=True,
            dossier_path=dossier_path)


    def generate_negligence_dossier(self, flag: DiscrepancyFlag, *,
                                    first_reviewer: str | None,
                                    second_reviewer: str) -> str:
        """Write a JSON + PDF dossier to ``myvote/data/dossiers/`` and return
        the JSON path. Uses PII-masked data (DPDP) in the persisted dossier."""
        from .security import mask_elector_public

        dossier_dir = Path(self.config.path).parent / "data" / "dossiers" \
            if self.config.path else Path("data") / "dossiers"
        dossier_dir.mkdir(parents=True, exist_ok=True)

        reviews = [{
            "round": r.review_round,
            "reviewer_id": r.reviewer_id,
            "decision": r.decision.value if isinstance(r.decision, BLOReviewDecision) else str(r.decision),
            "visited_house": r.visited_house,
            "voter_present": r.voter_present,
            "notes": r.notes,
            "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
        } for r in sorted(flag.reviews, key=lambda x: x.review_round)]

        dossier = {
            "flag_id": flag.id,
            "category": flag.category.value if isinstance(flag.category, FlagCategory) else str(flag.category),
            "tier": self._tier_value(flag),
            "confidence": flag.confidence,
            "explanation": flag.explanation,
            "legal_basis": flag.legal_basis,
            "subject_elector": mask_elector_public(flag.elector),
            "related_elector": mask_elector_public(flag.related_elector) if flag.related_elector else None,
            "first_reviewer": first_reviewer,
            "second_reviewer": second_reviewer,
            "outcome": "round-1 rejection overturned; negligence suspected",
            "reviews": reviews,
            "generated_at": utcnow().isoformat(),
            "audit_chain_verified": self.audit.verify()[0],
        }

        json_path = dossier_dir / f"negligence_dossier_flag_{flag.id}.json"
        json_path.write_text(json.dumps(dossier, indent=2), encoding="utf-8")
        flag.negligence_dossier_generated = True
        self.session.flush()

        # Best-effort PDF; JSON is always written even if PDF lib is missing.
        try:
            self._write_dossier_pdf(
                dossier, dossier_dir / f"negligence_dossier_flag_{flag.id}.pdf")
        except Exception:
            pass
        return str(json_path)

    def _write_dossier_pdf(self, dossier: dict, pdf_path: Path) -> None:
        """Minimal one-page PDF summary using reportlab (optional dependency)."""
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas

        c = canvas.Canvas(str(pdf_path), pagesize=letter)
        _width, height = letter
        y = height - 60
        c.setFont("Helvetica-Bold", 14)
        c.drawString(60, y, "Negligence Review Dossier (for ERO)")
        y -= 30
        c.setFont("Helvetica", 10)
        lines = [
            f"Flag ID: {dossier['flag_id']}",
            f"Category: {dossier['category']}   Tier: {dossier['tier']}   Confidence: {dossier['confidence']}",
            f"Subject (masked): {dossier['subject_elector']['epic_id']} / {dossier['subject_elector']['name']}",
            f"First reviewer: {dossier['first_reviewer']} (REJECT)",
            f"Second reviewer: {dossier['second_reviewer']} (CONFIRM - overturned)",
            f"Outcome: {dossier['outcome']}",
            f"Audit chain verified: {dossier['audit_chain_verified']}",
            f"Generated at: {dossier['generated_at']}",
            "",
            "Explanation: " + str(dossier.get("explanation", ""))[:400],
            "",
            "NOTE: No voter record has been deleted or altered by this system.",
        ]
        for line in lines:
            c.drawString(60, y, line)
            y -= 16
            if y < 60:
                c.showPage()
                y = height - 60
        c.save()

