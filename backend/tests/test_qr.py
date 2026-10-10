"""QR detection, decoding, and analysis tests."""
from __future__ import annotations

import json

import cv2
import numpy as np
import qrcode

from app.schemas.schemas import CheckStatus
from app.services.qr_service import _parse_payload, analyze_qr, decode_qr


def _make_qr(payload: str) -> np.ndarray:
    qr = qrcode.QRCode(border=2, box_size=8)
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    arr = np.array(img)
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def test_decode_valid_qr():
    img = _make_qr("ABC1234567")
    detected, decoded, payload = decode_qr(img)
    assert detected and decoded
    assert "ABC1234567" in payload


def test_decode_absent_qr():
    img = np.full((200, 200, 3), 255, dtype=np.uint8)
    detected, decoded, payload = decode_qr(img)
    assert not detected
    assert payload is None


def test_parse_json_payload():
    ptype, fields = _parse_payload(json.dumps({"epic": "ABC1234567", "name": "X"}))
    assert ptype == "json"
    assert fields["epic"] == "ABC1234567"


def test_parse_xml_payload():
    ptype, fields = _parse_payload("<EPIC><epic>ABC1234567</epic></EPIC>")
    assert ptype == "xml"
    assert fields["epic"] == "ABC1234567"


def test_parse_url_payload_not_fetched():
    ptype, fields = _parse_payload("https://example.com/verify")
    assert ptype == "url"
    assert fields == {}


def test_analyze_qr_consistent_with_ocr():
    img = _make_qr(json.dumps({"epic": "ABC1234567", "name": "X"}))
    result = analyze_qr(img, "ABC1234567")
    assert result.detected and result.decoded
    assert result.epic_matches_ocr is True
    assert result.status == CheckStatus.PASS


def test_analyze_qr_mismatch_with_ocr():
    img = _make_qr(json.dumps({"epic": "ABC1234567"}))
    result = analyze_qr(img, "XYZ9999999")
    assert result.epic_matches_ocr is False
    assert result.status == CheckStatus.FAIL


def test_analyze_qr_missing_optional():
    img = np.full((200, 200, 3), 255, dtype=np.uint8)
    result = analyze_qr(img, "ABC1234567")
    assert result.status == CheckStatus.NOT_APPLICABLE
    assert not result.detected
