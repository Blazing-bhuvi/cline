"""QR code detection and decoding using OpenCV.

Decoded content is treated as untrusted input. A URL payload is never fetched.
Successful decoding is NOT treated as proof of authenticity.
"""
from __future__ import annotations

import json
import re
from typing import Any

import cv2
import numpy as np

from app.schemas.schemas import CheckStatus, QRResult
from app.utils.text_utils import normalize_epic

_EPIC_SEARCH_RE = re.compile(r"([A-Z]{3})\s*[-]?\s*(\d{7})", re.IGNORECASE)
_URL_RE = re.compile(r"^https?://", re.IGNORECASE)

# Known XML tag names that may carry fields in an EPIC QR payload.
_TAG_MAP = {
    "epic": ["epic", "epicno", "epic_number", "cardno", "epicnumber"],
    "name": ["name", "electorname", "electorsname", "nm"],
    "relative_name": ["rname", "relativename", "fathername", "fhname", "parentname"],
    "gender": ["gender", "sex"],
    "dob": ["dob", "dateofbirth", "birthdate"],
    "address": ["address", "addr", "house"],
}


def decode_qr(image: np.ndarray) -> tuple[bool, bool, str | None]:
    """Return (detected, decoded, payload)."""
    try:
        detector = cv2.QRCodeDetector()
        data, points, _ = detector.detectAndDecode(image)
    except Exception:
        return False, False, None
    detected = points is not None and len(points) > 0
    decoded = bool(data and data.strip())
    return detected, decoded, (data.strip() if decoded else None)


def _parse_payload(payload: str) -> tuple[str, dict[str, Any]]:
    """Return (payload_type, fields)."""
    fields: dict[str, Any] = {}
    stripped = payload.strip()

    if stripped.startswith("{"):
        try:
            data = json.loads(stripped)
            if isinstance(data, dict):
                for k, v in data.items():
                    fields[str(k).lower()] = v
                return "json", fields
        except json.JSONDecodeError:
            pass

    if "<" in stripped and ">" in stripped:
        # Best-effort XML parsing via stdlib ElementTree (no external dep).
        try:
            import xml.etree.ElementTree as ET

            root = ET.fromstring(stripped)
            for el in root.iter():
                tag = el.tag
                if "}" in tag:
                    tag = tag.rsplit("}", 1)[1]
                text = (el.text or "").strip()
                if tag and text:
                    fields[tag.lower()] = text
            if fields:
                return "xml", fields
            return "xml_unparsed", fields
        except Exception:
            return "xml_unparsed", fields

    if _URL_RE.match(stripped):
        return "url", fields

    m = _EPIC_SEARCH_RE.search(stripped.replace(" ", "").upper())
    if m:
        return "epic_plain", {"epic": m.group(0)}

    return "unknown", fields


def _lookup_field(fields: dict[str, Any], key: str) -> str | None:
    for alias in _TAG_MAP.get(key, [key]):
        for fk, fv in fields.items():
            if fk == alias:
                if isinstance(fv, str):
                    return fv
    return None


def analyze_qr(image: np.ndarray, ocr_epic: str | None) -> QRResult:
    detected, decoded, payload = decode_qr(image)

    if not detected:
        return QRResult(
            status=CheckStatus.NOT_APPLICABLE,
            detected=False,
            decoded=False,
            reason="QR code not detected (optional unless the card format requires it).",
        )

    if not decoded or not payload:
        return QRResult(
            status=CheckStatus.UNVERIFIABLE,
            detected=True,
            decoded=False,
            reason="QR code detected but could not be decoded (unreadable or damaged).",
        )

    ptype, fields = _parse_payload(payload)

    if ptype == "url":
        return QRResult(
            status=CheckStatus.UNVERIFIABLE,
            detected=True,
            decoded=True,
            payload=payload,
            payload_type="url",
            fields={},
            reason="QR payload is a URL; not fetched and authenticity unverifiable.",
        )

    qr_epic_raw = _lookup_field(fields, "epic")
    qr_epic = normalize_epic(qr_epic_raw) if qr_epic_raw else None

    epic_matches: bool | None = None
    reason = ""

    if qr_epic and ocr_epic:
        epic_matches = qr_epic == normalize_epic(ocr_epic)
        reason = (
            "QR identifier matches OCR." if epic_matches else "QR identifier does not match OCR."
        )
    elif qr_epic and not ocr_epic:
        reason = "QR contains an identifier but OCR could not read one; unable to cross-check."
    elif not qr_epic:
        reason = "QR decoded but no recognized identifier found in payload."

    if epic_matches is False:
        status = CheckStatus.FAIL
    elif epic_matches is True:
        status = CheckStatus.PASS
    else:
        status = CheckStatus.UNVERIFIABLE

    # Record that authenticity of a decodable QR is never provable locally.
    reason += " (Decoding success does not establish authenticity.)"

    return QRResult(
        status=status,
        detected=True,
        decoded=True,
        payload=payload,
        payload_type=ptype,
        fields=fields,
        epic_matches_ocr=epic_matches,
        reason=reason,
    )
