"""Workflow tests: state machine, routing, double-review escalation, FIR,
and Phase 3 hardening (validation, idempotency, no-delete invariant)."""
from __future__ import annotations

import pytest

from myvote.audit import AuditChain
from myvote.config import get_config
from myvote.enums import BLOReviewDecision, FlagCategory, ConfidenceTier, FlagState
from myvote.flags import run_detection_pass
from myvote.models import DiscrepancyFlag, Elector, BLOReviewSubmission
from myvote.workflow import VerificationWorkflow, WorkflowError


def _make_high_flag(session, tier=ConfidenceTier.HIGH.value, state=FlagState.ASSIGNED.value):
    e = Elector(epic_id=f"E{session.query(Elector).count()+1}", name="Test Person",
                dob=__import__("myvote.eronet", fromlist=["QUALIFYING_DATE"]).QUALIFYING_DATE.replace(year=1990),
                gender="M", relative_name="Rel", relation_type="father",
                house_number="1", locality="L", district="D", constituency="AC-001",
                part_number=1, serial_number=1, address_line="1, L, D")
    session.add(e)
    session.flush()
    flag = DiscrepancyFlag(elector_id=e.id, category=FlagCategory.DUPLICATE.value,
                           state=state, tier=tier, confidence=0.9,
                           assigned_blo_id="BLO-1",
                           explanation="test", legal_basis="test")
    session.add(flag)
    session.commit()
    return flag


def test_illegal_transition_rejected(session):
    flag = _make_high_flag(session, state=FlagState.FLAGGED.value)
    wf = VerificationWorkflow(session)
    # FLAGGED -> BLO_REVIEW is illegal (must go through ASSIGNED first).
    with pytest.raises(WorkflowError):
        wf.start_review(flag.id, "BLO-1", actor="BLO-1")


def test_assign_then_review(session):
    flag = _make_high_flag(session, state=FlagState.FLAGGED.value)
    wf = VerificationWorkflow(session)
    wf.assign(flag.id, "BLO-1")
    session.commit()
    res = wf.start_review(flag.id, "BLO-1", actor="BLO-1")
    session.commit()
    assert str(res.flag.state) == FlagState.BLO_REVIEW.value


def test_wrong_blo_cannot_review(session):
    flag = _make_high_flag(session, state=FlagState.BLO_REVIEW.value)
    wf = VerificationWorkflow(session)
    with pytest.raises(WorkflowError):
        wf.submit_review(flag.id, "BLO-99", "CONFIRM", review_round=1)


def test_high_flag_reject_escalates(session):
    flag = _make_high_flag(session, tier=ConfidenceTier.HIGH.value,
                           state=FlagState.BLO_REVIEW.value)
    wf = VerificationWorkflow(session)
    res = wf.submit_review(flag.id, "BLO-1", "REJECT", review_round=1)
    session.commit()
    assert res.escalated
    assert flag.needs_second_review
    assert str(flag.state) == FlagState.BLO_REVIEW.value  # still open, awaiting 2nd


def test_low_flag_reject_does_not_escalate(session):
    flag = _make_high_flag(session, tier=ConfidenceTier.LOW.value,
                           state=FlagState.BLO_REVIEW.value)
    wf = VerificationWorkflow(session)
    res = wf.submit_review(flag.id, "BLO-1", "REJECT", review_round=1)
    session.commit()
    assert not res.escalated
    assert str(flag.state) == FlagState.REJECTED.value


def test_second_reviewer_cannot_review_round2_without_escalation(session):
    flag = _make_high_flag(session, tier=ConfidenceTier.LOW.value,
                           state=FlagState.REJECTED.value)
    wf = VerificationWorkflow(session)
    with pytest.raises(WorkflowError):
        wf.submit_review(flag.id, "BLO-2", "CONFIRM", review_round=2)


def test_overturn_generates_dossier_and_fir(session, tmp_path):
    flag = _make_high_flag(session, tier=ConfidenceTier.HIGH.value,
                           state=FlagState.BLO_REVIEW.value)
    # Point the dossier dir at tmp_path by faking config.path.
    cfg = get_config()
    wf = VerificationWorkflow(session, cfg)
    # First BLO rejects a HIGH flag -> escalation.
    wf.submit_review(flag.id, "BLO-1", "REJECT", review_round=1)
    session.commit()
    # Second reviewer confirms -> overturn -> dossier + FIR.
    res = wf.submit_review(flag.id, "BLO-2", "CONFIRM", review_round=2)
    session.commit()
    assert res.fir_triggered
    assert res.dossier_path is not None
    assert flag.fir_triggered
    assert str(flag.state) == FlagState.CONFIRMED.value


def test_idempotent_no_duplicate_round1_review(session):
    flag = _make_high_flag(session, tier=ConfidenceTier.LOW.value,
                           state=FlagState.BLO_REVIEW.value)
    wf = VerificationWorkflow(session)
    wf.submit_review(flag.id, "BLO-1", "REJECT", review_round=1)
    session.commit()
    with pytest.raises(WorkflowError):
        wf.submit_review(flag.id, "BLO-1", "CONFIRM", review_round=1)


def test_no_voter_record_deleted_by_workflow(seeded):
    session, truth = seeded
    before = session.query(Elector).count()
    run_detection_pass(session)
    flags = session.query(DiscrepancyFlag).all()
    assert flags, "detection should have produced flags"
    wf = VerificationWorkflow(session)
    # Assign + confirm a flag and ensure the elector still exists.
    f = flags[0]
    wf.assign(f.id, "BLO-1")
    session.commit()
    wf.start_review(f.id, "BLO-1", actor="BLO-1")
    wf.submit_review(f.id, "BLO-1", "CONFIRM", review_round=1)
    session.commit()
    after = session.query(Elector).count()
    assert before == after, "workflow must NEVER delete an elector"


def test_audit_log_records_every_transition(seeded):
    session, truth = seeded
    AuditChain(session).bootstrap_genesis()
    flag = _make_high_flag(session, state=FlagState.FLAGGED.value)
    wf = VerificationWorkflow(session)
    wf.assign(flag.id, "BLO-1")
    session.commit()
    ok, errors = AuditChain(session).verify()
    assert ok, errors
    actions = {e.action for e in AuditChain(session).entries()}
    assert "FLAG_ASSIGNED" in actions


# --------------------------------------------------------------------------- #
#  Phase 3 hardening tests (one per fix)
# --------------------------------------------------------------------------- #
def test_terminal_confirmed_flag_cannot_be_reviewed_again(session):
    # Gap: a CONFIRMED flag could be reviewed again. Fix: terminal-state guard.
    flag = _make_high_flag(session, tier=ConfidenceTier.LOW.value,
                           state=FlagState.BLO_REVIEW.value)
    wf = VerificationWorkflow(session)
    wf.submit_review(flag.id, "BLO-1", "CONFIRM", review_round=1)
    session.commit()
    assert str(flag.state) == FlagState.CONFIRMED.value
    with pytest.raises(WorkflowError):
        wf.submit_review(flag.id, "BLO-1", "REJECT", review_round=1)


def test_terminal_rejected_flag_cannot_be_reviewed_again(session):
    flag = _make_high_flag(session, tier=ConfidenceTier.LOW.value,
                           state=FlagState.BLO_REVIEW.value)
    wf = VerificationWorkflow(session)
    wf.submit_review(flag.id, "BLO-1", "REJECT", review_round=1)
    session.commit()
    assert str(flag.state) == FlagState.REJECTED.value
    with pytest.raises(WorkflowError):
        wf.submit_review(flag.id, "BLO-1", "CONFIRM", review_round=1)


def test_flagged_unrouted_flag_cannot_be_reviewed(session):
    # Gap: a FLAGGED (never routed) flag could jump straight to a decision.
    # Fix: must be ASSIGNED/BLO_REVIEW first.
    flag = _make_high_flag(session, state=FlagState.FLAGGED.value)
    wf = VerificationWorkflow(session)
    with pytest.raises(WorkflowError):
        wf.submit_review(flag.id, "BLO-1", "CONFIRM", review_round=1)


def test_assigned_flag_auto_advances_to_review(session):
    # A legitimately ASSIGNED flag reviewed by its own BLO auto-advances
    # ASSIGNED -> BLO_REVIEW -> CONFIRMED.
    flag = _make_high_flag(session, tier=ConfidenceTier.LOW.value,
                           state=FlagState.ASSIGNED.value)
    wf = VerificationWorkflow(session)
    res = wf.submit_review(flag.id, "BLO-1", "CONFIRM", review_round=1)
    session.commit()
    assert str(res.flag.state) == FlagState.CONFIRMED.value


def test_assigned_flag_wrong_blo_cannot_open_review(session):
    flag = _make_high_flag(session, state=FlagState.ASSIGNED.value)
    wf = VerificationWorkflow(session)
    with pytest.raises(WorkflowError):
        wf.submit_review(flag.id, "WRONG-BLO", "CONFIRM", review_round=1)


def test_second_reviewer_must_differ_from_first(session):
    # Gap: the second reviewer could be the same person as the first BLO,
    # defeating the "independent" double-review. Fix: reject.
    flag = _make_high_flag(session, tier=ConfidenceTier.HIGH.value,
                           state=FlagState.BLO_REVIEW.value)
    wf = VerificationWorkflow(session)
    wf.submit_review(flag.id, "BLO-1", "REJECT", review_round=1)
    session.commit()
    with pytest.raises(WorkflowError):
        wf.submit_review(flag.id, "BLO-1", "CONFIRM", review_round=2)


def test_invalid_decision_raises_workflow_error_not_valueerror(session):
    # Gap: an invalid decision string raised a raw ValueError (-> HTTP 500).
    # Fix: a clean WorkflowError (-> HTTP 400).
    flag = _make_high_flag(session, tier=ConfidenceTier.LOW.value,
                           state=FlagState.BLO_REVIEW.value)
    wf = VerificationWorkflow(session)
    with pytest.raises(WorkflowError):
        wf.submit_review(flag.id, "BLO-1", "MAYBE", review_round=1)


def test_concurrent_double_confirm_only_one_wins(session):
    # Race guard: two independent workflow instances reviewing the same flag;
    # the second must be rejected by the terminal-state / idempotency guard.
    flag = _make_high_flag(session, tier=ConfidenceTier.LOW.value,
                           state=FlagState.BLO_REVIEW.value)
    wf1 = VerificationWorkflow(session)
    wf2 = VerificationWorkflow(session)
    r1 = wf1.submit_review(flag.id, "BLO-1", "CONFIRM", review_round=1)
    session.commit()
    assert str(r1.flag.state) == FlagState.CONFIRMED.value
    with pytest.raises(WorkflowError):
        wf2.submit_review(flag.id, "BLO-1", "REJECT", review_round=1)

