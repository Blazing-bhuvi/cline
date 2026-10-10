"""High-level orchestration tying together preprocessing, OCR, card assessment,
QR analysis, database cross-verification, and face matching.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.schemas.schemas import (
    CheckStatus,
    DocumentAnalysisResult,
    DocumentSides,
    FaceMatchResult,
    FaceQualityResult,
    LivenessResult,
    OCRResult,
    VerificationResult,
)
from app.services import card_assessment, ocr_service, preprocessing, qr_service, voter_database
from app.services.decision_engine import decide, DISCLOSURES
from app.services.face_detector import get_face_detector
from app.services.face_matcher import get_face_matcher, match_faces
from app.services.face_quality import assess_face_quality
from app.utils import image_utils
from app.utils.text_utils import normalize_epic


def _load_image(path: Path) -> "cv2.typing.MatLike":
    data = path.read_bytes()
    return image_utils.decode_image(data)


def liveness_result() -> LivenessResult:
    return LivenessResult(
        status=CheckStatus.NOT_APPLICABLE,
        implemented=False,
        reason="Liveness detection is not implemented in this prototype.",
    )


def _ocr_image(settings, img_bgr):
    """Run OCR on a preprocessed image; return (fields, lines, unreadable, warnings, quality, ok)."""
    try:
        lines = ocr_service.run_ocr(img_bgr)
        fields = ocr_service.extract_fields(lines)
        unreadable, warnings, quality = ocr_service.assess_readability(
            fields, settings.ocr_min_confidence
        )
        return fields, lines, unreadable, warnings, quality, True
    except ocr_service.OCRError as exc:  # pragma: no cover
        return {}, [], ["epic", "name"], [str(exc)], 0.0, False


def _assess_sides(front_img, back_img, back_ocr, front_fields) -> DocumentSides:
    """Detect whether the back image corresponds to the front (or is itself a front)."""
    if back_img is None or back_ocr is None:
        return DocumentSides(status=CheckStatus.NOT_APPLICABLE, reason="no back image uploaded")

    back_fields, back_lines, _, _, _, _ = back_ocr
    front_epic = normalize_epic(front_fields.get("epic", {}).get("value")) or None
    back_epic = normalize_epic(back_fields.get("epic", {}).get("value")) or None

    # Signals that the "back" image is actually a front image.
    back_text = " ".join(t for t, _, _ in back_lines).upper()
    has_front_title = "ELECTOR PHOTO IDENTITY CARD" in back_text
    has_name = bool(back_fields.get("name", {}).get("value"))
    detector = get_face_detector()
    has_portrait = detector.detect_largest(back_img, min_size=60) is not None
    back_looks_like_front = has_front_title and (has_name or has_portrait)

    sides = DocumentSides(
        back_present=True,
        back_analyzed=True,
        front_epic=front_epic,
        back_epic=back_epic,
        back_looks_like_front=back_looks_like_front,
    )

    if back_epic and front_epic and back_epic != front_epic:
        sides.epic_matches = False
        sides.status = CheckStatus.FAIL
        sides.reason = f"front and back identifiers differ ({front_epic} vs {back_epic})"
    elif back_looks_like_front:
        sides.status = CheckStatus.INCONCLUSIVE
        sides.reason = "the 'back' image appears to be a front image; upload the correct back side"
    elif back_epic and front_epic and back_epic == front_epic:
        sides.epic_matches = True
        sides.status = CheckStatus.PASS
        sides.reason = "front and back correspond (matching identifiers)"
    elif back_epic and not front_epic:
        sides.status = CheckStatus.INCONCLUSIVE
        sides.reason = "front identifier not readable; cannot verify correspondence"
    elif not back_epic:
        sides.status = CheckStatus.INCONCLUSIVE
        sides.reason = "back identifier not readable; cannot verify correspondence"
    else:
        sides.status = CheckStatus.INCONCLUSIVE
        sides.reason = "could not verify front/back correspondence"

    return sides


def analyze_document(db: Session, front_path: Path, back_path: Path | None = None) -> DocumentAnalysisResult:
    """Run OCR, structural, QR, and database checks for the front document image.

    A back image, when provided, is OCR'd concurrently with the front (keeping
    total latency ~one OCR pass) and checked for correspondence.
    """
    settings = get_settings()
    front_img = _load_image(front_path)
    front_processed, _, _ = preprocessing.preprocess_document(front_img)

    back_img = None
    back_processed = None
    if back_path is not None:
        try:
            back_img = _load_image(back_path)
            back_processed, _, _ = preprocessing.preprocess_document(back_img)
        except Exception:
            back_img = None
            back_processed = None

    # OCR front and back concurrently to keep processing fast.
    if back_processed is not None:
        with ThreadPoolExecutor(max_workers=2) as ex:
            front_future = ex.submit(_ocr_image, settings, front_processed)
            back_future = ex.submit(_ocr_image, settings, back_processed)
            front_ocr = front_future.result()
            back_ocr = back_future.result()
    else:
        front_ocr = _ocr_image(settings, front_processed)
        back_ocr = None

    ocr_fields, lines, unreadable, warnings, quality, ocr_ok = front_ocr

    # Portrait extraction (on the original, not the processed copy)
    portrait_path = None
    portrait_extracted = False
    detector = get_face_detector()
    face = detector.detect_largest(front_img, min_size=60)
    if face is not None:
        x, y, w, h = face["box"]
        crop = front_img[y : y + h, x : x + w]
        portrait_path = front_path.parent / "portrait.jpg"
        image_utils.write_image(crop, portrait_path)
        portrait_extracted = True

    ocr_result = OCRResult(
        fields=ocr_fields,
        confidence={k: (v.get("confidence") or 0.0) for k, v in ocr_fields.items()},
        warnings=warnings,
        unreadable_fields=unreadable,
        text_lines=[t for t, _, _ in lines],
        portrait_extracted=portrait_extracted,
        portrait_path=str(portrait_path) if portrait_path else None,
        overall_quality_score=round(quality, 3),
    )

    assessment = card_assessment.assess_card(front_img, ocr_fields, portrait_extracted)

    qr = qr_service.analyze_qr(front_img, ocr_fields.get("epic", {}).get("value"))

    db_result = voter_database.cross_verify(
        db, ocr_fields, name_threshold=settings.name_similarity_threshold
    )

    sides = _assess_sides(front_img, back_img, back_ocr, ocr_fields)

    # Preliminary pass gates the camera stage.
    image_quality_check = next(
        (c for c in assessment.checks if c.name == "image_quality"), None
    )
    image_quality_status = image_quality_check.status if image_quality_check else CheckStatus.UNVERIFIABLE

    preliminary = (
        ocr_ok
        and "epic" not in unreadable
        and "name" not in unreadable
        and image_quality_status != CheckStatus.FAIL
        and db_result.status == CheckStatus.PASS
        and qr.status != CheckStatus.FAIL
        and sides.status != CheckStatus.FAIL
    )
    preliminary_reasons: list[str] = []
    if not ocr_ok or "epic" in unreadable or "name" in unreadable:
        preliminary_reasons.append("required OCR fields could not be read")
    if image_quality_status == CheckStatus.FAIL:
        preliminary_reasons.append("document image quality insufficient")
    if db_result.status == CheckStatus.FAIL:
        preliminary_reasons.append("database cross-verification failed")
    if qr.status == CheckStatus.FAIL:
        preliminary_reasons.append("QR identifier conflict detected")
    if sides.status == CheckStatus.FAIL:
        preliminary_reasons.append(sides.reason)

    return DocumentAnalysisResult(
        image_quality=image_quality_status,
        image_quality_reason=image_quality_check.reason if image_quality_check else "",
        ocr=ocr_result,
        card_assessment=assessment,
        qr=qr,
        database=db_result,
        sides=sides,
        preliminary_pass=preliminary,
        preliminary_reasons=preliminary_reasons,
    )


def process_face_capture(
    session_id: str,
    analysis: DocumentAnalysisResult,
    face_path: Path,
) -> tuple[FaceQualityResult, FaceMatchResult | None, VerificationResult]:
    """Assess a live capture, match against the ID portrait, and decide."""
    img = _load_image(face_path)
    quality = assess_face_quality(img)

    face_match: FaceMatchResult | None = None
    result: VerificationResult

    if quality.status == CheckStatus.PASS:
        detector = get_face_detector()
        live_face_box = detector.detect_largest(img, min_size=60)
        live_face_bgr = None
        if live_face_box is not None:
            x, y, w, h = live_face_box["box"]
            live_face_bgr = img[y : y + h, x : x + w]

        id_face_bgr = None
        if analysis.ocr.portrait_path:
            try:
                id_face_bgr = _load_image(Path(analysis.ocr.portrait_path))
            except Exception:
                id_face_bgr = None

        matcher = get_face_matcher()
        face_match = match_faces(matcher, id_face_bgr, live_face_bgr)

    result = decide(session_id, analysis, quality, face_match, liveness_result())
    return quality, face_match, result
