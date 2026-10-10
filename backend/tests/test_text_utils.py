"""Unit tests for text normalization and similarity helpers."""
from app.utils.text_utils import (
    name_similarity,
    normalize_dob,
    normalize_epic,
    normalize_gender,
    normalize_name,
)


def test_normalize_epic_strips_separators_and_uppercases():
    assert normalize_epic("  abc-1234567 ") == "ABC1234567"
    assert normalize_epic("ABC 123 4567") == "ABC1234567"


def test_normalize_epic_does_not_collapse_distinct_values():
    # Distinct digits must stay distinct (no aggressive O->0 mapping).
    assert normalize_epic("ABC1234567") != normalize_epic("ABC1234568")


def test_normalize_name():
    assert normalize_name("  Aarav   Sharma ") == "aarav sharma"


def test_normalize_gender():
    assert normalize_gender("Male") == "male"
    assert normalize_gender("F") == "female"


def test_normalize_dob():
    assert normalize_dob("12-04-1990") == "1990-04-12"
    assert normalize_dob("1990-04-12") == "1990-04-12"


def test_name_similarity_exact_is_high():
    assert name_similarity("Aarav Sharma", "Aarav Sharma") > 0.9


def test_name_similarity_unrelated_is_low():
    assert name_similarity("Aarav Sharma", "Priya Patel") < 0.5
