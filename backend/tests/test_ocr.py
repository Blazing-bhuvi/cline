"""OCR field-extraction tests (unit) plus a real-OCR integration test."""
from __future__ import annotations

import pytest

from app.services.ocr_service import assess_readability, extract_fields, _match_label


def _line(text, score=0.9):
    return (text, [[0, 0], [10, 0], [10, 10], [0, 10]], score)


def test_match_label_normalizes_curly_apostrophe():
    field, _ = _match_label("Father\u2019s Name:")
    assert field == "relative_name"


def test_extract_epic_from_lines():
    lines = [
        _line("ELECTION COMMISSION OF INDIA"),
        _line("EPIC No: ABC1234567"),
        _line("Name: Aarav Sharma"),
        _line("Father's Name: Rohit Sharma"),
        _line("Sex: Male"),
    ]
    fields = extract_fields(lines)
    assert fields["epic"]["value"] == "ABC1234567"
    assert fields["name"]["value"] == "Aarav Sharma"
    assert fields["relative_name"]["value"] == "Rohit Sharma"
    assert fields["gender"]["normalized"] == "male"


def test_missing_fields_are_none():
    lines = [_line("Name: Aarav Sharma")]
    fields = extract_fields(lines)
    assert fields["epic"]["value"] is None
    assert fields["dob"]["value"] is None


def test_low_confidence_fields_marked_unreadable():
    # Label-based fields carry the OCR line confidence; EPIC regex match is high
    # confidence by construction, so use the name field to test the threshold.
    lines = [_line("EPIC No: ABC1234567", score=0.2), _line("Name: Aarav Sharma", score=0.2)]
    fields = extract_fields(lines)
    assert fields["epic"]["value"] == "ABC1234567"
    assert fields["name"]["value"] is None


def test_assess_readability():
    fields = {
        "epic": {"value": "ABC1234567", "confidence": 0.9},
        "name": {"value": "Aarav Sharma", "confidence": 0.9},
        "gender": {"value": "male", "confidence": 0.8},
    }
    unreadable, warnings, quality = assess_readability(fields, 0.55)
    assert unreadable == []
    assert quality > 0.5


def test_assess_readability_missing_required():
    fields = {"epic": {"value": None, "confidence": None}}
    unreadable, _, _ = assess_readability(fields, 0.55)
    assert "epic" in unreadable


@pytest.mark.integration
def test_real_ocr_reads_generated_card(sample_card_path):
    from app.services import ocr_service, preprocessing
    from app.utils import image_utils

    img = image_utils.decode_image(sample_card_path.read_bytes())
    processed, _, _ = preprocessing.preprocess_document(img)
    lines = ocr_service.run_ocr(processed)
    fields = ocr_service.extract_fields(lines)
    assert fields["epic"]["value"] == "XYZ0000001"
    assert fields["name"]["value"] == "Aarav Sharma"
