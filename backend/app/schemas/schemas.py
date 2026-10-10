"""Pydantic request/response schemas for the verification API."""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class CheckStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNVERIFIABLE = "UNVERIFIABLE"
    INCONCLUSIVE = "INCONCLUSIVE"
    PENDING = "PENDING"


class OverallStatus(str, Enum):
    PASS = "PASS"
    REJECTED = "REJECTED"
    INCONCLUSIVE = "INCONCLUSIVE"
    PENDING = "PENDING"


class MatchResult(str, Enum):
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    INCONCLUSIVE = "INCONCLUSIVE"


class Side(str, Enum):
    FRONT = "front"
    BACK = "back"


class StartRequest(BaseModel):
    consent: bool = Field(..., description="Explicit consent to local processing")
    side_required: Side = Side.FRONT


class SessionCreated(BaseModel):
    session_id: str
    token: str
    expires_at: str | None = None


class UploadedImage(BaseModel):
    side: Side
    filename: str
    width: int
    height: int
    size_bytes: int
    content_type: str


class DocumentUploadResponse(BaseModel):
    session_id: str
    images: list[UploadedImage]
    warnings: list[str] = []


class OCRField(BaseModel):
    value: str | None = None
    confidence: float | None = None
    normalized: str | None = None
    raw: str | None = None


class OCRResult(BaseModel):
    fields: dict[str, Any] = {}
    confidence: dict[str, float] = {}
    warnings: list[str] = []
    unreadable_fields: list[str] = []
    text_lines: list[str] = []
    portrait_extracted: bool = False
    portrait_path: str | None = None
    overall_quality_score: float = 0.0


class CardCheck(BaseModel):
    name: str
    status: CheckStatus
    reason: str = ""
    details: dict[str, Any] = {}


class CardAssessment(BaseModel):
    format_matched: bool = False
    quality_score: float = 0.0
    checks: list[CardCheck] = []
    overall: CheckStatus = CheckStatus.UNVERIFIABLE
    summary: str = ""


class QRResult(BaseModel):
    status: CheckStatus
    detected: bool = False
    decoded: bool = False
    payload: str | None = None
    payload_type: str | None = None
    fields: dict[str, Any] = {}
    epic_matches_ocr: bool | None = None
    reason: str = ""


class FieldMatch(BaseModel):
    field: str
    ocr_value: str | None = None
    db_value: str | None = None
    matched: bool | None = None
    similarity: float | None = None
    reason: str = ""


class DatabaseMatchResult(BaseModel):
    status: CheckStatus
    record_found: bool = False
    record_id: int | None = None
    epic_matched: bool = False
    name_matched: bool | None = None
    field_matches: list[FieldMatch] = []
    source: str | None = None
    reason: str = ""

    side_required: Side = Side.FRONT


class SessionCreated(BaseModel):
    session_id: str
    token: str
    expires_at: str | None = None


class UploadedImage(BaseModel):
    side: Side
    filename: str
    width: int
    height: int
    size_bytes: int
    content_type: str


class FaceQualityResult(BaseModel):
    status: CheckStatus
    face_detected: bool = False
    face_count: int = 0
    size_ok: bool = False
    centered: bool = False
    sharp: bool = False
    exposure_ok: bool = False
    obstructed: bool | None = None
    instructions: list[str] = []
    score: float = 0.0
    reason: str = ""


class FaceMatchResult(BaseModel):
    status: CheckStatus
    match_result: MatchResult | None = None
    similarity: float | None = None
    threshold_match: float | None = None
    threshold_review: float | None = None
    id_face_available: bool = False
    live_face_available: bool = False
    reason: str = ""


class LivenessResult(BaseModel):
    status: CheckStatus
    implemented: bool = False
    reason: str = ""


class DocumentSides(BaseModel):
    back_present: bool = False
    back_analyzed: bool = False
    front_epic: str | None = None
    back_epic: str | None = None
    epic_matches: bool | None = None
    back_looks_like_front: bool | None = None
    status: CheckStatus = CheckStatus.NOT_APPLICABLE
    reason: str = ""


class DocumentAnalysisResult(BaseModel):
    image_quality: CheckStatus = CheckStatus.PENDING
    image_quality_reason: str = ""
    ocr: OCRResult = OCRResult()
    card_assessment: CardAssessment = CardAssessment()
    qr: QRResult | None = None
    database: DatabaseMatchResult | None = None
    sides: DocumentSides | None = None
    preliminary_pass: bool = False
    preliminary_reasons: list[str] = []


class FaceSubmitResponse(BaseModel):
    session_id: str
    face_quality: FaceQualityResult
    accepted: bool


class CheckItem(BaseModel):
    key: str
    label: str
    status: CheckStatus
    reason: str = ""
    details: dict[str, Any] = {}


class VerificationResult(BaseModel):
    session_id: str
    overall_status: OverallStatus
    summary: str = ""
    reasons: list[str] = []
    checklist: list[CheckItem] = []
    document_analysis: DocumentAnalysisResult | None = None
    face_match: FaceMatchResult | None = None
    liveness: LivenessResult | None = None
    disclosures: list[str] = []


class RetryResponse(BaseModel):
    session_id: str
    retriable_stage: str | None = None
    ok: bool
    reason: str = ""


class HealthResponse(BaseModel):
    status: str
    app: str
    environment: str
    dependencies: dict[str, str]
    demo_mode: bool

class DocumentUploadResponse(BaseModel):
    session_id: str
    images: list[UploadedImage]
    warnings: list[str] = []
