"""OCR extraction service backed by RapidOCR (onnxruntime, runs locally).

Provides a real OCR pipeline: no cloud calls, no hardcoded success.
"""
from __future__ import annotations

import re
import threading
from typing import Any

import numpy as np

from app.core.config import get_settings
from app.utils.text_utils import normalize_dob, normalize_epic, normalize_gender, normalize_name

_engine = None
_engine_failed = False
_engine_lock = threading.Lock()

# Label keywords (uppercase) that may prefix a field value on an EPIC card.
FIELD_LABELS: dict[str, list[str]] = {
    "name": [
        "ELECTOR'S NAME", "ELECTORS NAME", "NAME OF ELECTOR", "ELECTOR NAME",
        "NAME OF THE ELECTOR", "NAME", "नाम",
    ],
    "relative_name": [
        "FATHER'S NAME", "FATHERS NAME", "MOTHER'S NAME", "MOTHERS NAME",
        "HUSBAND'S NAME", "HUSBANDS NAME", "RELATION NAME", "FATHER NAME",
        "RELATION'S NAME", "पिता", "पति",
    ],
    "gender": ["SEX", "GENDER", "लिंग"],
    "dob": ["DATE OF BIRTH", "DOB", "D.O.B", "जन्म तिथि", "जन्मतिथि"],
    "age": ["AGE", "आयु"],
    "address": ["ADDRESS", "पता"],
    "epic": ["EPIC NO", "EPIC NUMBER", "EPIC NO.", "EPIC", "ईपीआईसी"],
}

# EPIC number: 3 letters followed by 7 digits (allow optional separators/spaces).
EPIC_RE = re.compile(r"\b([A-Z]{3})\s*[-]?\s*(\d{7})\b", re.IGNORECASE)


class OCRError(RuntimeError):
    pass


def get_ocr_engine():
    global _engine, _engine_failed
    if _engine is None and not _engine_failed:
        with _engine_lock:
            if _engine is None and not _engine_failed:
                try:
                    from rapidocr_onnxruntime import RapidOCR  # type: ignore

                    _engine = RapidOCR()
                except Exception as exc:  # pragma: no cover - environment dependent
                    _engine_failed = True
                    raise OCRError(f"OCR engine unavailable: {exc}") from exc
    if _engine is None:
        raise OCRError("OCR engine unavailable.")
    return _engine


def run_ocr(image: np.ndarray) -> list[tuple[str, Any, float]]:
    """Run OCR and return a list of (text, box, score)."""
    engine = get_ocr_engine()
    try:
        out = engine(image)
    except TypeError:  # pragma: no cover - older API variants
        out = engine(image)[0]
    except Exception as exc:
        raise OCRError(f"OCR inference failed: {exc}") from exc

    if isinstance(out, tuple):
        items = out[0]
    else:
        items = out

    lines: list[tuple[str, Any, float]] = []
    if not items:
        return lines
    for item in items:
        try:
            if isinstance(item, (list, tuple)) and len(item) >= 3:
                box, text, score = item[0], item[1], item[2]
            elif hasattr(item, "text"):
                box = getattr(item, "box", None)
                text = item.text
                score = getattr(item, "score", 1.0)
            else:  # pragma: no cover
                continue
            lines.append((str(text), box, float(score)))
        except Exception:  # pragma: no cover
            continue
    return lines

def _norm_label(text: str) -> str:
    return (
        text.replace("\u2019", "'")
        .replace("\u2018", "'")
        .replace("`", "'")
        .upper()
        .strip()
    )


def _match_label(text: str) -> tuple[str, int] | None:
    """Return (field, label_length_in_chars) if the line starts with a known label."""
    upper = _norm_label(text)
    for field, labels in FIELD_LABELS.items():
        for label in labels:
            lab = _norm_label(label)
            prefix = lab + ":"
            if upper.startswith(prefix):
                return field, len(label) + 1
            prefix = lab + " "
            if upper.startswith(prefix):
                return field, len(label)
            if upper == lab:
                return field, len(label)
    return None


def _extract_epic(texts: list[str]) -> tuple[str | None, float | None]:
    for text in texts:
        m = EPIC_RE.search(text.replace(" ", "").upper())
        if m:
            return m.group(0), 1.0
    return None, None


def extract_fields(lines: list[tuple[str, Any, float]]) -> dict[str, Any]:
    """Extract structured fields from OCR lines.

    Returns a dict of field -> {'value','confidence','normalized','raw'}.
    Missing fields have value=None and are reported as unreadable.
    """
    settings = get_settings()
    min_conf = settings.ocr_min_confidence

    field_values: dict[str, dict[str, Any]] = {}
    texts: list[str] = []
    line_index: list[dict[str, Any]] = []

    for text, box, score in lines:
        t = text.strip()
        if not t:
            continue
        texts.append(t)
        line_index.append({"text": t, "box": box, "score": score, "used": False})

    epic, epic_conf = _extract_epic(texts)
    if epic:
        field_values["epic"] = {
            "value": epic,
            "confidence": epic_conf,
            "normalized": normalize_epic(epic),
            "raw": epic,
        }

    label_start: dict[str, int | None] = {f: None for f in FIELD_LABELS}
    for idx, rec in enumerate(line_index):
        m = _match_label(rec["text"])
        if m and label_start[m[0]] is None:
            label_start[m[0]] = idx

    def value_for(field: str) -> tuple[str | None, float | None]:
        start = label_start.get(field)
        if start is None:
            return None, None
        parts: list[str] = []
        scores: list[float] = []
        idx = start
        rec = line_index[idx]
        _, label_len = _match_label(rec["text"]) or (field, 0)
        remainder = rec["text"][label_len:].strip(": \t")
        if remainder:
            parts.append(remainder)
            scores.append(rec["score"])
        idx += 1
        while idx < len(line_index) and len(parts) < 4:
            nxt = line_index[idx]
            if _match_label(nxt["text"]) is not None:
                break
            if EPIC_RE.search(nxt["text"].replace(" ", "").upper()):
                break
            if not parts:
                parts.append(nxt["text"])
                scores.append(nxt["score"])
            elif field == "address":
                parts.append(nxt["text"])
                scores.append(nxt["score"])
            else:
                break
            idx += 1
        if not parts:
            return None, None
        value = " ".join(p.strip() for p in parts if p.strip())
        conf = float(np.mean(scores)) if scores else None
        return value, conf

    for field in ("name", "relative_name", "gender", "dob", "age", "address"):
        value, conf = value_for(field)
        if value is not None:
            field_values[field] = {
                "value": value,
                "confidence": conf,
                "normalized": _normalize_field(field, value),
                "raw": value,
            }

    result: dict[str, Any] = {}
    for field, data in field_values.items():
        conf = data.get("confidence")
        if conf is not None and conf < min_conf:
            result[field] = {**data, "value": None}
        else:
            result[field] = data

    for field in ("epic", "name", "relative_name", "gender", "dob", "age", "address"):
        if field not in result:
            result[field] = {
                "value": None,
                "confidence": None,
                "normalized": None,
                "raw": None,
            }
    return result


def _normalize_field(field: str, value: str) -> str | None:
    if field == "epic":
        return normalize_epic(value)
    if field in ("name", "relative_name"):
        return normalize_name(value)
    if field == "gender":
        return normalize_gender(value)
    if field == "dob":
        return normalize_dob(value)
    return value.strip()


def assess_readability(
    fields: dict[str, Any], min_conf: float
) -> tuple[list[str], list[str], float]:
    """Return (unreadable_fields, warnings, overall_quality_score)."""
    unreadable: list[str] = []
    warnings: list[str] = []
    confs: list[float] = []
    required = ("epic", "name")
    optional = ("relative_name", "gender", "dob", "age", "address")

    for f in required:
        if fields.get(f, {}).get("value") is None:
            unreadable.append(f)
    for f in optional:
        if fields.get(f, {}).get("value") is None:
            warnings.append(f)

    for data in fields.values():
        c = data.get("confidence")
        if c is not None:
            confs.append(c)

    quality = float(np.mean(confs)) if confs else 0.0
    if not unreadable and quality < min_conf:
        warnings.append("low overall OCR confidence")
    return unreadable, warnings, quality
