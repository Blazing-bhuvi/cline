"""FastAPI router for MyVote-D, mounted under ``/myvote/api``.

Exposes: health, detection pass, flag listing (PII-masked), assign, review
(with double-review escalation + FIR), and audit-chain integrity. A separate
page router (``myvote/pages.py``) serves the server-rendered Jinja2 dashboard.

The subsystem never deletes a voter; every mutation is audit-logged.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .audit import AuditChain
from .db import get_session
from .enums import FlagState
from .flags import run_detection_pass
from .models import DiscrepancyFlag, Elector
from .schemas import (AssignRequest, AuditIntegrityResponse, FlagSummary,
                      HealthResponse, ReviewRequest, ReviewResponse)
from .security import mask_elector_public
from .workflow import VerificationWorkflow, WorkflowError

router = APIRouter(prefix="/myvote/api", tags=["myvote"])


def _flag_summary(flag: DiscrepancyFlag) -> FlagSummary:
    return FlagSummary(
        id=flag.id,
        category=flag.category,
        state=flag.state,
        tier=flag.tier,
        confidence=flag.confidence,
        subject=mask_elector_public(flag.elector),
        explanation=flag.explanation,
    )


@router.get("/health", response_model=HealthResponse)
def health(session: Session = Depends(get_session)) -> HealthResponse:
    audit_ok, _ = AuditChain(session).verify()
    open_flags = (session.query(DiscrepancyFlag)
                  .filter(DiscrepancyFlag.state.notin_(
                      [FlagState.CONFIRMED.value, FlagState.REJECTED.value]))
                  .count())
    return HealthResponse(
        status="ok",
        audit_chain_ok=audit_ok,
        elector_count=session.query(Elector).count(),
        open_flags=open_flags,
    )


@router.get("/audit/integrity", response_model=AuditIntegrityResponse)
def audit_integrity(session: Session = Depends(get_session)) -> AuditIntegrityResponse:
    chain = AuditChain(session)
    ok, errors = chain.verify()
    return AuditIntegrityResponse(ok=ok, entries=len(chain.entries()),
                                  errors=errors)


@router.post("/detect")
def run_detection(session: Session = Depends(get_session)) -> dict:
    """Run a full detection pass and persist new flags (never deletes)."""
    return run_detection_pass(session)


@router.get("/flags", response_model=list[FlagSummary])
def list_flags(state: str | None = None,
               session: Session = Depends(get_session)) -> list[FlagSummary]:
    q = session.query(DiscrepancyFlag)
    if state:
        q = q.filter(DiscrepancyFlag.state == state.upper())
    return [_flag_summary(f) for f in q.order_by(DiscrepancyFlag.id.desc()).all()]


@router.get("/flags/{flag_id}")
def flag_detail(flag_id: int, session: Session = Depends(get_session)) -> dict:
    flag = session.get(DiscrepancyFlag, flag_id)
    if flag is None:
        raise HTTPException(status_code=404, detail="Flag not found")
    return {
        "id": flag.id,
        "category": str(flag.category),
        "state": str(flag.state),
        "tier": str(flag.tier),
        "confidence": flag.confidence,
        "dsd_score": flag.dsd_score,
        "psd_score": flag.psd_score,
        "explanation": flag.explanation,
        "legal_basis": flag.legal_basis,
        "assigned_blo_id": flag.assigned_blo_id,
        "needs_second_review": flag.needs_second_review,
        "fir_triggered": flag.fir_triggered,
        "subject": mask_elector_public(flag.elector),
        "related": mask_elector_public(flag.related_elector) if flag.related_elector else None,
    }


@router.post("/flags/{flag_id}/assign", response_model=ReviewResponse)
def assign_flag(flag_id: int, req: AssignRequest,
                session: Session = Depends(get_session)) -> ReviewResponse:
    try:
        result = VerificationWorkflow(session).assign(flag_id, req.blo_id)
        session.commit()
    except WorkflowError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ReviewResponse(flag_id=flag_id, state=result.flag.state,
                          message=result.message)


@router.post("/flags/{flag_id}/review", response_model=ReviewResponse)
def submit_review(flag_id: int, req: ReviewRequest,
                  session: Session = Depends(get_session)) -> ReviewResponse:
    try:
        wf = VerificationWorkflow(session)
        result = wf.submit_review(
            flag_id, req.reviewer_id, req.decision,
            notes=req.notes, visited_house=req.visited_house,
            voter_present=req.voter_present, review_round=req.review_round)
        session.commit()
    except WorkflowError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ReviewResponse(
        flag_id=flag_id, state=result.flag.state, message=result.message,
        escalated=result.escalated, fir_triggered=result.fir_triggered,
        dossier_path=result.dossier_path)


def mount(app) -> None:
    """Optionally mount MyVote-D's API + dashboard pages into an existing
    FastAPI ``app``. Upstream is NOT required to call this; it is opt-in.

    Usage (in upstream backend/app/main.py, fully optional)::

        try:
            from myvote.api import mount as mount_myvote
            mount_myvote(app)
        except Exception:
            pass  # MyVote-D is an optional subsystem
    """
    from .pages import pages_router  # server-rendered dashboard pages
    app.include_router(router)
    app.include_router(pages_router)

