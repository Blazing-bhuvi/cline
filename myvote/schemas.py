"""Pydantic v2 request/response schemas for the MyVote-D API.

Follows upstream's convention of a dedicated ``schemas`` module with
str-Enums. All public-facing views are PII-masked before serialisation.
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class FlagCategoryOut(str, Enum):
    DUPLICATE = "DUPLICATE"
    TRANSLITERATION = "TRANSLITERATION"
    UNDERAGE = "UNDERAGE"
    FORM7_ABUSE = "FORM7_ABUSE"
    FAKE_DELETION = "FAKE_DELETION"


class FlagStateOut(str, Enum):
    FLAGGED = "FLAGGED"
    ASSIGNED = "ASSIGNED"
    BLO_REVIEW = "BLO_REVIEW"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"


class TierOut(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class HealthResponse(BaseModel):
    status: str
    subsystem: str = "myvote"
    audit_chain_ok: bool
    elector_count: int
    open_flags: int


class FlagSummary(BaseModel):
    id: int
    category: FlagCategoryOut
    state: FlagStateOut
    tier: TierOut
    confidence: float
    # PII-masked public view of the subject elector.
    subject: dict[str, Any]
    explanation: str = ""


class AssignRequest(BaseModel):
    blo_id: str = Field(..., description="Booth Level Officer identifier")


class ReviewRequest(BaseModel):
    reviewer_id: str
    decision: str = Field(..., description="CONFIRM or REJECT")
    notes: str = ""
    visited_house: bool = False
    voter_present: bool = False
    review_round: int = 1


class ReviewResponse(BaseModel):
    flag_id: int
    state: FlagStateOut
    message: str
    escalated: bool = False
    fir_triggered: bool = False
    dossier_path: str | None = None


class AuditIntegrityResponse(BaseModel):
    ok: bool
    entries: int
    errors: list[str] = []
