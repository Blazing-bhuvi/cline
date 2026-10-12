"""SQLAlchemy ORM models for MyVote-D (electoral roll discrepancy system).

Tables
------
Elector                - a voter entry on the (synthetic) roll
FormSubmission         - a Form 6 / 7 / 8 filing by an objector
DiscrepancyFlag        - a detected anomaly routed to a BLO
BLOReviewSubmission    - a BLO's verification decision (supports double-review)
AuditLogEntry          - append-only, SHA-256 hash-chained audit record

These tables live in MyVote-D's own SQLite database (``myvote/data/electoral.db``)
and are registered on MyVote-D's own ``Base`` (``myvote.db.Base``) — completely
separate from upstream's ``voter_records`` table and Base.

PII note: raw PII lives ONLY in the database and in the authenticated BLO
review view. Public dashboards must go through ``myvote.security.mask_*``.
"""
from __future__ import annotations

import json
from datetime import date, datetime

from sqlalchemy import (Boolean, Date, DateTime, Float, ForeignKey, Integer,
                        String, Text)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from .enums import (BLOReviewDecision, ConfidenceTier, FlagCategory,
                    FlagState, FormType)
from .timeutil import utcnow


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )


class Elector(Base, TimestampMixin):
    __tablename__ = "electors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    epic_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    dob: Mapped[date] = mapped_column(Date)
    gender: Mapped[str] = mapped_column(String(16))
    relative_name: Mapped[str] = mapped_column(String(200))
    relation_type: Mapped[str] = mapped_column(String(32))  # father/husband/mother
    address_line: Mapped[str] = mapped_column(String(300))
    house_number: Mapped[str] = mapped_column(String(32))
    locality: Mapped[str] = mapped_column(String(120))
    district: Mapped[str] = mapped_column(String(120))
    constituency: Mapped[str] = mapped_column(String(120), index=True)
    part_number: Mapped[int] = mapped_column(Integer)
    serial_number: Mapped[int] = mapped_column(Integer)

    # Mock 128-d face embedding stored as JSON list of floats (synthetic).
    photo_vector_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    @property
    def photo_vector(self) -> list[float] | None:
        if not self.photo_vector_json:
            return None
        return json.loads(self.photo_vector_json)

    @photo_vector.setter
    def photo_vector(self, value: list[float] | None) -> None:
        self.photo_vector_json = json.dumps(value) if value is not None else None

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Elector id={self.id} epic={self.epic_id} name={self.name!r}>"


class FormSubmission(Base, TimestampMixin):
    """A Form 6 (inclusion) / Form 7 (deletion) / Form 8 (correction) filing."""
    __tablename__ = "form_submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    form_type: Mapped[FormType] = mapped_column(
        String(16), default=FormType.FORM_6.value
    )
    objector_name: Mapped[str] = mapped_column(String(200))
    objector_epic: Mapped[str] = mapped_column(String(32), index=True)
    target_elector_id: Mapped[int | None] = mapped_column(
        ForeignKey("electors.id"), nullable=True
    )
    reason: Mapped[str] = mapped_column(Text, default="")
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    target_elector: Mapped[Elector | None] = relationship()

    def __repr__(self) -> str:  # pragma: no cover
        return (f"<FormSubmission id={self.id} type={self.form_type} "
                f"objector={self.objector_epic} target={self.target_elector_id}>")


class DiscrepancyFlag(Base, TimestampMixin):
    """A detected anomaly routed to a BLO for physical verification.

    The flag NEVER mutates an Elector. It only records the detection, its
    confidence, a plain-language legal explanation, and workflow state.
    """
    __tablename__ = "discrepancy_flags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # The subject elector (the entry being questioned).
    elector_id: Mapped[int] = mapped_column(ForeignKey("electors.id"), index=True)
    # For duplicate-style flags, the "other" elector it may clash with.
    related_elector_id: Mapped[int | None] = mapped_column(
        ForeignKey("electors.id"), nullable=True
    )
    # Optional link to the triggering Form submission (e.g. Form 7 abuse).
    form_submission_id: Mapped[int | None] = mapped_column(
        ForeignKey("form_submissions.id"), nullable=True
    )

    category: Mapped[FlagCategory] = mapped_column(String(32), index=True)
    state: Mapped[FlagState] = mapped_column(
        String(16), default=FlagState.FLAGGED.value, index=True
    )

    # Detection scores in [0,1].
    dsd_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    psd_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    tier: Mapped[ConfidenceTier] = mapped_column(
        String(8), default=ConfidenceTier.LOW.value, index=True
    )

    # Plain-language explanation of the legal basis (shown to BLO / ERO).
    explanation: Mapped[str] = mapped_column(Text, default="")
    legal_basis: Mapped[str] = mapped_column(String(300), default="")

    # Routing / escalation bookkeeping.
    assigned_blo_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    needs_second_review: Mapped[bool] = mapped_column(Boolean, default=False)
    second_reviewer_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # FIR / negligence bookkeeping (Phase 3).
    fir_triggered: Mapped[bool] = mapped_column(Boolean, default=False)
    negligence_dossier_generated: Mapped[bool] = mapped_column(Boolean, default=False)

    elector: Mapped[Elector] = relationship(foreign_keys=[elector_id])
    related_elector: Mapped[Elector | None] = relationship(
        foreign_keys=[related_elector_id]
    )
    form_submission: Mapped[FormSubmission | None] = relationship(
        foreign_keys=[form_submission_id]
    )
    reviews: Mapped[list["BLOReviewSubmission"]] = relationship(
        back_populates="flag", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (f"<DiscrepancyFlag id={self.id} cat={self.category} "
                f"tier={self.tier} state={self.state}>")


class BLOReviewSubmission(Base, TimestampMixin):
    """A BLO's (or second reviewer's) physical-verification decision.

    Multiple rows may exist for one flag to support blind double-review.
    """
    __tablename__ = "blo_review_submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    flag_id: Mapped[int] = mapped_column(ForeignKey("discrepancy_flags.id"), index=True)
    reviewer_id: Mapped[str] = mapped_column(String(64), index=True)
    # 1 = first BLO review, 2 = escalation / second reviewer.
    review_round: Mapped[int] = mapped_column(Integer, default=1)
    decision: Mapped[BLOReviewDecision] = mapped_column(String(16))
    notes: Mapped[str] = mapped_column(Text, default="")
    # Physical-verification evidence fields (synthetic / mock).
    visited_house: Mapped[bool] = mapped_column(Boolean, default=False)
    voter_present: Mapped[bool] = mapped_column(Boolean, default=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    flag: Mapped[DiscrepancyFlag] = relationship(back_populates="reviews")

    def __repr__(self) -> str:  # pragma: no cover
        return (f"<BLOReviewSubmission id={self.id} flag={self.flag_id} "
                f"round={self.review_round} decision={self.decision}>")


class AuditLogEntry(Base):
    """Append-only, SHA-256 hash-chained audit record.

    Each row stores ``entry_hash`` = SHA-256(canonical(payload) + prev_hash).
    Tampering with any row breaks the chain, detectable via ``AuditChain``.
    """
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sequence: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(64))
    payload: Mapped[str] = mapped_column(Text, default="")   # canonical JSON
    prev_hash: Mapped[str] = mapped_column(String(64))
    entry_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    def __repr__(self) -> str:  # pragma: no cover
        return (f"<AuditLogEntry seq={self.sequence} action={self.action} "
                f"actor={self.actor} hash={self.entry_hash[:10]}...>")

