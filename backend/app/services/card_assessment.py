"""Card authenticity / tampering assessment (heuristic, honest about limits).

None of these checks prove authenticity. They record *evidence* and mark
unverifiable claims as UNVERIFIABLE rather than inventing certainty.
"""
from __future__ import annotations

import cv2
import numpy as np

from app.schemas.schemas import CardAssessment, CardCheck, CheckStatus
from app.utils.image_utils import brightness_score, contrast_score, sharpness_score


def _quality_status(sharpness: float, brightness: float, contrast: float) -> tuple[CheckStatus, str]:
    if sharpness < 30:
        return CheckStatus.FAIL, f"image too blurry (sharpness {sharpness:.1f})"
    if brightness < 40 or brightness > 225:
        return CheckStatus.INCONCLUSIVE, f"poor exposure (brightness {brightness:.1f})"
    if sharpness < 80:
        return CheckStatus.INCONCLUSIVE, f"moderate sharpness ({sharpness:.1f})"
    return CheckStatus.PASS, "image quality sufficient for analysis"


def _layout_status(img: np.ndarray, ocr_fields: dict) -> tuple[CheckStatus, str, bool]:
    h, w = img.shape[:2]
    ratio = w / float(h) if h else 0.0
    ratio_plausible = 1.0 < ratio < 2.2
    text_present = any(ocr_fields.get(f, {}).get("value") for f in ("epic", "name"))
    matched = ratio_plausible and text_present
    if ratio_plausible and text_present:
        return CheckStatus.PASS, "aspect ratio and text layout resemble a card", True
    if text_present:
        return CheckStatus.UNVERIFIABLE, "text present but card geometry uncertain", False
    return CheckStatus.UNVERIFIABLE, "could not confirm card layout from image", False


def _tamper_status(img: np.ndarray) -> tuple[CheckStatus, str]:
    """Lightweight inconsistent-region heuristic. Never treated as definitive."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]
    scores = []
    step_y, step_x = max(h // 3, 1), max(w // 3, 1)
    for y in range(0, h - step_y + 1, step_y):
        for x in range(0, w - step_x + 1, step_x):
            patch = gray[y : y + step_y, x : x + step_x]
            if patch.size < 100:
                continue
            scores.append(float(cv2.Laplacian(patch, cv2.CV_64F).var()))
    if not scores:
        return CheckStatus.UNVERIFIABLE, "tampering assessment unavailable"
    arr = np.array(scores)
    mean = float(arr.mean())
    if mean > 0 and float(arr.std()) > 4 * mean + 50:
        return CheckStatus.INCONCLUSIVE, "possible inconsistent regions detected (heuristic)"
    return CheckStatus.UNVERIFIABLE, "no gross anomaly detected (heuristics cannot rule out forgery)"


def _overall(statuses: list[CheckStatus]) -> CheckStatus:
    if CheckStatus.FAIL in statuses:
        return CheckStatus.FAIL
    if any(s in (CheckStatus.UNVERIFIABLE, CheckStatus.INCONCLUSIVE) for s in statuses):
        return CheckStatus.UNVERIFIABLE
    if all(s in (CheckStatus.PASS, CheckStatus.NOT_APPLICABLE) for s in statuses):
        return CheckStatus.PASS
    return CheckStatus.UNVERIFIABLE


def _quality_score(sharp: float) -> float:
    return float(np.clip(sharp / 150.0, 0.0, 1.0))

def assess_card(img: np.ndarray, ocr_fields: dict, portrait_available: bool) -> CardAssessment:
    sharp = sharpness_score(img)
    bright = brightness_score(img)
    contrast = contrast_score(img)

    checks: list[CardCheck] = []

    q_status, q_reason = _quality_status(sharp, bright, contrast)
    checks.append(
        CardCheck(
            name="image_quality",
            status=q_status,
            reason=q_reason,
            details={"sharpness": sharp, "brightness": bright, "contrast": contrast},
        )
    )

    epic = ocr_fields.get("epic", {}).get("value")
    name = ocr_fields.get("name", {}).get("value")
    if epic and name:
        field_status, field_reason = CheckStatus.PASS, "expected fields (EPIC, name) present"
    elif epic or name:
        field_status, field_reason = CheckStatus.INCONCLUSIVE, "some expected fields missing"
    else:
        field_status, field_reason = CheckStatus.INCONCLUSIVE, "expected fields not readable"
    checks.append(
        CardCheck(
            name="field_presence",
            status=field_status,
            reason=field_reason,
            details={"epic": bool(epic), "name": bool(name)},
        )
    )

    l_status, l_reason, matched = _layout_status(img, ocr_fields)
    checks.append(
        CardCheck(
            name="card_layout",
            status=l_status,
            reason=l_reason,
            details={"format_matched": matched},
        )
    )

    t_status, t_reason = _tamper_status(img)
    checks.append(CardCheck(name="tampering_heuristics", status=t_status, reason=t_reason))

    if portrait_available:
        p_status, p_reason = CheckStatus.PASS, "portrait region detected"
    else:
        p_status, p_reason = CheckStatus.UNVERIFIABLE, "portrait region not reliably detected"
    checks.append(CardCheck(name="portrait_presence", status=p_status, reason=p_reason))

    fmt_checks = [c for c in checks if c.name in ("field_presence", "card_layout")]
    fmt_ok = all(c.status == CheckStatus.PASS for c in fmt_checks)
    checks.append(
        CardCheck(
            name="format_consistency",
            status=CheckStatus.PASS if fmt_ok else CheckStatus.UNVERIFIABLE,
            reason=(
                "format consistent with a supported EPIC-style layout"
                if fmt_ok
                else "format not fully consistent with supported layout"
            ),
        )
    )

    overall = _overall([c.status for c in checks])
    summary = _summarize(overall, checks)
    return CardAssessment(
        format_matched=matched,
        quality_score=_quality_score(sharp),
        checks=checks,
        overall=overall,
        summary=summary,
    )


def _summarize(overall: CheckStatus, checks: list[CardCheck]) -> str:
    failures = [c.name for c in checks if c.status == CheckStatus.FAIL]
    if failures:
        return f"Definitive issues: {', '.join(failures)}."
    if overall == CheckStatus.PASS:
        return "No mandatory authenticity issues detected by available checks."
    return "Card authenticity could not be fully established from available evidence."
