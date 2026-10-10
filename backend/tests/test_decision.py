"""Decision-engine tests covering PASS / REJECTED / INCONCLUSIVE outcomes."""
from __future__ import annotations

from app.schemas.schemas import (
    CardAssessment,
    CardCheck,
    CheckStatus,
    DocumentAnalysisResult,
    FaceMatchResult,
    FaceQualityResult,
    LivenessResult,
    MatchResult,
    OCRResult,
    OverallStatus,
    QRResult,
)
from app.services.decision_engine import build_checklist, decide


def _analysis(
    db_status=CheckStatus.PASS,
    ocr_ok=True,
    img_quality=CheckStatus.PASS,
    qr_status=CheckStatus.PASS,
):
    fields = {
        "epic": {"value": "ABC1234567", "confidence": 0.9},
        "name": {"value": "Aarav Sharma", "confidence": 0.9},
    }
    if not ocr_ok:
        fields = {"epic": {"value": None}, "name": {"value": None}}
    assessment = CardAssessment(
        checks=[
            CardCheck(name="image_quality", status=img_quality, reason="q"),
            CardCheck(name="tampering_heuristics", status=CheckStatus.UNVERIFIABLE, reason="t"),
        ],
        overall=CheckStatus.PASS if img_quality == CheckStatus.PASS else CheckStatus.UNVERIFIABLE,
    )
    return DocumentAnalysisResult(
        image_quality=img_quality,
        ocr=OCRResult(fields=fields),
        card_assessment=assessment,
        qr=QRResult(status=qr_status, detected=True, decoded=True),
        database=__import__("app.schemas.schemas", fromlist=["DatabaseMatchResult"]).DatabaseMatchResult(
            status=db_status, record_found=db_status == CheckStatus.PASS
        ),
    )


def _face_match(result):
    status = {
        MatchResult.MATCH: CheckStatus.PASS,
        MatchResult.MISMATCH: CheckStatus.FAIL,
        MatchResult.INCONCLUSIVE: CheckStatus.INCONCLUSIVE,
    }[result]
    return FaceMatchResult(status=status, match_result=result, similarity=0.9 if result == MatchResult.MATCH else 0.1)


def _quality(status=CheckStatus.PASS):
    return FaceQualityResult(status=status, face_detected=True)


def _liveness():
    return LivenessResult(status=CheckStatus.NOT_APPLICABLE, implemented=False)


def test_all_mandatory_pass():
    result = decide("s1", _analysis(), _quality(), _face_match(MatchResult.MATCH), _liveness())
    assert result.overall_status == OverallStatus.PASS


def test_database_failure_rejects():
    result = decide("s1", _analysis(db_status=CheckStatus.FAIL), _quality(), _face_match(MatchResult.MATCH), _liveness())
    assert result.overall_status == OverallStatus.REJECTED


def test_face_mismatch_rejects():
    result = decide("s1", _analysis(), _quality(), _face_match(MatchResult.MISMATCH), _liveness())
    assert result.overall_status == OverallStatus.REJECTED


def test_qr_conflict_rejects():
    result = decide("s1", _analysis(qr_status=CheckStatus.FAIL), _quality(), _face_match(MatchResult.MATCH), _liveness())
    assert result.overall_status == OverallStatus.REJECTED


def test_missing_face_inconclusive():
    result = decide("s1", _analysis(), None, None, _liveness())
    assert result.overall_status == OverallStatus.INCONCLUSIVE


def test_blurry_image_inconclusive_not_rejected():
    result = decide("s1", _analysis(img_quality=CheckStatus.FAIL), _quality(), _face_match(MatchResult.MATCH), _liveness())
    assert result.overall_status == OverallStatus.INCONCLUSIVE


def test_unreadable_ocr_inconclusive():
    result = decide("s1", _analysis(ocr_ok=False), _quality(), _face_match(MatchResult.MATCH), _liveness())
    assert result.overall_status == OverallStatus.INCONCLUSIVE


def test_optional_check_unavailable_still_passes():
    result = decide("s1", _analysis(qr_status=CheckStatus.NOT_APPLICABLE), _quality(), _face_match(MatchResult.MATCH), _liveness())
    assert result.overall_status == OverallStatus.PASS


def test_checklist_keys_present():
    checklist = build_checklist(_analysis(), _quality(), _face_match(MatchResult.MATCH), _liveness())
    keys = {c.key for c in checklist}
    for expected in (
        "image_validity",
        "ocr_readability",
        "card_format",
        "tampering",
        "qr_status",
        "database_match",
        "face_photo_availability",
        "live_face_quality",
        "face_similarity",
        "liveness",
    ):
        assert expected in keys
