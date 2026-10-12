"""Bridge between the detection engine and the persistence/workflow layers.

Turns :class:`myvote.detection.Detection` candidates into persisted
:class:`myvote.models.DiscrepancyFlag` rows, and logs each creation to the
hash-chained audit trail. This module NEVER deletes or mutates an Elector.
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy.orm import Session

from .audit import AuditChain
from .config import Config, get_config
from .detection import Detection, detect_all
from .enums import AuditAction, FlagCategory, FlagState
from .models import DiscrepancyFlag, FormSubmission, Elector
from .timeutil import utcnow


def create_flags_from_detections(session: Session, detections: list[Detection],
                                 config: Config | None = None) -> list[DiscrepancyFlag]:
    """Persist detections as DiscrepancyFlag rows (FLAGGED state). Idempotent
    against re-running: skips if an equivalent open flag already exists."""
    config = config or get_config()
    audit = AuditChain(session, config)
    created: list[DiscrepancyFlag] = []

    for det in detections:
        if det.category == FlagCategory.FORM7_ABUSE:
            # One flag per targeted elector in the bulk-abuse pattern.
            form_id = _link_form_for_target(session, det)
            for target_id in det.extra.get("target_elector_ids", [det.elector_a_id]):
                if _existing_flag(session, det.category, target_id,
                                  det.elector_a_id):
                    continue
                flag = DiscrepancyFlag(
                    elector_id=target_id,
                    related_elector_id=None,
                    form_submission_id=form_id,
                    category=det.category.value,
                    state=FlagState.FLAGGED.value,
                    dsd_score=det.dsd,
                    psd_score=det.psd,
                    confidence=det.confidence,
                    tier=det.tier.value,
                    explanation=det.explanation,
                    legal_basis=det.legal_basis,
                )
                session.add(flag)
                session.flush()
                audit.append(actor="system", action=AuditAction.FLAG_CREATED,
                             entity_type="discrepancy_flag", entity_id=str(flag.id),
                             payload={"category": det.category.value,
                                      "tier": det.tier.value,
                                      "confidence": det.confidence})
                created.append(flag)
        else:
            if _existing_flag(session, det.category, det.elector_a_id,
                              det.elector_b_id):
                continue
            flag = DiscrepancyFlag(
                elector_id=det.elector_a_id,
                related_elector_id=det.elector_b_id,
                category=det.category.value,
                state=FlagState.FLAGGED.value,
                dsd_score=det.dsd,
                psd_score=det.psd,
                confidence=det.confidence,
                tier=det.tier.value,
                explanation=det.explanation,
                legal_basis=det.legal_basis,
            )
            session.add(flag)
            session.flush()
            audit.append(actor="system", action=AuditAction.FLAG_CREATED,
                         entity_type="discrepancy_flag", entity_id=str(flag.id),
                         payload={"category": det.category.value,
                                  "tier": det.tier.value,
                                  "confidence": det.confidence})
            created.append(flag)

    session.commit()
    return created


def _existing_flag(session: Session, category: FlagCategory, elector_a_id: int,
                   elector_b_id: int) -> bool:
    q = (session.query(DiscrepancyFlag)
         .filter(DiscrepancyFlag.category == category.value,
                 DiscrepancyFlag.elector_id == elector_a_id))
    if category == FlagCategory.FORM7_ABUSE:
        return q.first() is not None
    return (q.filter(DiscrepancyFlag.related_elector_id == elector_b_id)
            .first() is not None)


def _link_form_for_target(session: Session, det: Detection) -> int | None:
    """Find a Form 7 submission by the abusive objector for provenance."""
    objector = det.extra.get("objector_epic")
    if not objector:
        return None
    form = (session.query(FormSubmission)
            .filter(FormSubmission.objector_epic == objector)
            .first())
    return form.id if form else None


def run_detection_pass(session: Session, config: Config | None = None) -> dict:
    """Convenience: run detection + persist flags. Returns a summary."""
    config = config or get_config()
    detections = detect_all(session, config)
    flags = create_flags_from_detections(session, detections, config)
    by_tier: dict[str, int] = defaultdict(int)
    by_cat: dict[str, int] = defaultdict(int)
    for f in flags:
        by_tier[str(f.tier)] += 1
        by_cat[str(f.category)] += 1
    return {
        "detections": len(detections),
        "flags_created": len(flags),
        "by_tier": dict(by_tier),
        "by_category": dict(by_cat),
    }
