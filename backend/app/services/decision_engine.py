"""Centralized verification decision engine.

Combines document analysis, database cross-verification, and face comparison
into a PASS / REJECTED / INCONCLUSIVE outcome with a full checklist and reasons.
"""
from __future__ import annotations

from app.schemas.schemas import (
    CheckItem,
    CheckStatus,
    DocumentAnalysisResult,
    FaceMatchResult,
    FaceQualityResult,
    LivenessResult,
    MatchResult,
    OverallStatus,
    VerificationResult,
)

DISCLOSURES = [
    "Demonstration mode: no authoritative Election Commission of India verification is performed.",
    "Database cross-verification uses a locally seeded synthetic dataset, not an official electoral roll.",
    "Card authenticity checks are heuristic and cannot prove a card is genuine.",
    "QR decoding does not establish authenticity; QR codes can be copied or generated.",
    "Liveness detection is not implemented; a photograph shown to the camera may be accepted by the face matcher.",
    "Face matching can produce false matches and false rejections.",
]


def _item(key: str, label: str, status: CheckStatus, reason: str = "", details: dict | None = None) -> CheckItem:
    return CheckItem(key=key, label=label, status=status, reason=reason, details=details or {})


def _find_check(analysis: DocumentAnalysisResult, name: str):
    for c in analysis.card_assessment.checks:
        if c.name == name:
            return c
    return None


def _ocr_readability(analysis: DocumentAnalysisResult) -> tuple[CheckStatus, str]:
    fields = analysis.ocr.fields
    epic = fields.get("epic", {}).get("value")
    name = fields.get("name", {}).get("value")
    if epic and name:
        return CheckStatus.PASS, "required fields (EPIC, name) were read successfully"
    missing = [f for f in ("epic", "name") if not fields.get(f, {}).get("value")]
    return CheckStatus.INCONCLUSIVE, f"required fields not reliably read: {', '.join(missing)}"


def build_checklist(
    analysis: DocumentAnalysisResult,
    face_quality: FaceQualityResult | None,
    face_match: FaceMatchResult | None,
    liveness: LivenessResult | None,
) -> list[CheckItem]:
    items: list[CheckItem] = []

    iq = _find_check(analysis, "image_quality")
    items.append(
        _item(
            "image_validity",
            "Image validity",
            iq.status if iq else CheckStatus.PENDING,
            iq.reason if iq else "",
            iq.details if iq else {},
        )
    )

    ocr_status, ocr_reason = _ocr_readability(analysis)
    items.append(
        _item(
            "ocr_readability",
            "OCR readability",
            ocr_status,
            ocr_reason,
            {"unreadable": analysis.ocr.unreadable_fields},
        )
    )

    fmt = _find_check(analysis, "format_consistency")
    items.append(
        _item("card_format", "Card format", fmt.status if fmt else CheckStatus.PENDING, fmt.reason if fmt else "")
    )

    tamper = _find_check(analysis, "tampering_heuristics")
    items.append(
        _item("tampering", "Tampering assessment", tamper.status if tamper else CheckStatus.PENDING, tamper.reason if tamper else "")
    )

    qr = analysis.qr
    items.append(
        _item(
            "qr_status",
            "QR analysis",
            qr.status if qr else CheckStatus.NOT_APPLICABLE,
            qr.reason if qr else "QR analysis not run",
            {"detected": qr.detected if qr else False, "decoded": qr.decoded if qr else False},
        )
    )

    db = analysis.database
    items.append(
        _item(
            "database_match",
            "Database cross-verification",
            db.status if db else CheckStatus.PENDING,
            db.reason if db else "database check not run",
            {"record_found": db.record_found if db else False},
        )
    )

    sides = analysis.sides
    items.append(
        _item(
            "document_sides",
            "Front/back correspondence",
            sides.status if sides else CheckStatus.NOT_APPLICABLE,
            sides.reason if sides else "no back image uploaded",
            {
                "back_present": sides.back_present if sides else False,
                "epic_matches": sides.epic_matches if sides else None,
            },
        )
    )

    portrait = analysis.ocr.portrait_extracted
    items.append(
        _item(
            "face_photo_availability",
            "ID portrait availability",
            CheckStatus.PASS if portrait else CheckStatus.UNVERIFIABLE,
            "ID portrait extracted" if portrait else "ID portrait not reliably extracted",
        )
    )

    if face_quality is not None:
        items.append(
            _item(
                "live_face_quality",
                "Live face quality",
                face_quality.status,
                face_quality.reason,
                {"score": face_quality.score, "instructions": face_quality.instructions},
            )
        )
    else:
        items.append(_item("live_face_quality", "Live face quality", CheckStatus.PENDING, "not captured yet"))

    if face_match is not None:
        items.append(
            _item(
                "face_similarity",
                "Face similarity",
                face_match.status,
                face_match.reason,
                {"similarity": face_match.similarity, "match_result": face_match.match_result},
            )
        )
    else:
        items.append(_item("face_similarity", "Face similarity", CheckStatus.PENDING, "not compared yet"))

    items.append(
        _item(
            "liveness",
            "Liveness / presentation attack",
            liveness.status if liveness else CheckStatus.NOT_APPLICABLE,
            (liveness.reason if liveness else "not implemented"),
        )
    )
    return items

def decide(
    session_id: str,
    analysis: DocumentAnalysisResult,
    face_quality: FaceQualityResult | None,
    face_match: FaceMatchResult | None,
    liveness: LivenessResult | None,
) -> VerificationResult:
    checklist = build_checklist(analysis, face_quality, face_match, liveness)

    # Definitive failures that map to REJECTED (demo mode).
    definitive_reasons: list[str] = []
    if analysis.database is not None and analysis.database.status == CheckStatus.FAIL:
        definitive_reasons.append(analysis.database.reason)
    if analysis.qr is not None and analysis.qr.status == CheckStatus.FAIL:
        definitive_reasons.append(analysis.qr.reason)
    if analysis.sides is not None and analysis.sides.status == CheckStatus.FAIL:
        definitive_reasons.append(analysis.sides.reason)
    if face_match is not None and face_match.match_result == MatchResult.MISMATCH:
        definitive_reasons.append(face_match.reason)

    # Mandatory checks that must PASS for an overall PASS.
    mandatory_pass = True
    if analysis.database is None or analysis.database.status != CheckStatus.PASS:
        mandatory_pass = False
    if face_match is None or face_match.match_result != MatchResult.MATCH:
        mandatory_pass = False
    if face_quality is None or face_quality.status != CheckStatus.PASS:
        mandatory_pass = False
    ocr_status, _ = _ocr_readability(analysis)
    if ocr_status != CheckStatus.PASS:
        mandatory_pass = False
    iq = _find_check(analysis, "image_quality")
    if iq is None or iq.status != CheckStatus.PASS:
        mandatory_pass = False

    if definitive_reasons:
        overall = OverallStatus.REJECTED
        summary = "Verification rejected: one or more definitive failures."
    elif mandatory_pass:
        overall = OverallStatus.PASS
        summary = "All mandatory checks passed for the configured demonstration mode."
    else:
        overall = OverallStatus.INCONCLUSIVE
        summary = "Insufficient or unverifiable evidence; manual review recommended."

    reasons: list[str] = list(unique(definitive_reasons))
    if overall != OverallStatus.REJECTED:
        for item in checklist:
            if item.status in (CheckStatus.UNVERIFIABLE, CheckStatus.INCONCLUSIVE, CheckStatus.PENDING):
                reasons.append(f"{item.label}: {item.reason}")

    return VerificationResult(
        session_id=session_id,
        overall_status=overall,
        summary=summary,
        reasons=reasons,
        checklist=checklist,
        document_analysis=analysis,
        face_match=face_match,
        liveness=liveness,
        disclosures=DISCLOSURES,
    )


def unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out
