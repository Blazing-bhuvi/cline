"""Database cross-verification tests."""
from __future__ import annotations

import pytest

from app.models.orm import VoterRecord
from app.schemas.schemas import CheckStatus
from app.services.voter_database import cross_verify, lookup_by_epic


def _ocr(epic=None, name=None, gender=None, dob=None, relative_name=None):
    def f(field):
        values = {
            "epic": epic,
            "name": name,
            "gender": gender,
            "date_of_birth": dob,
            "relative_name": relative_name,
        }
        return {"value": values.get(field)}

    return {k: f(k) for k in ("epic", "name", "gender", "date_of_birth", "relative_name")}


def test_exact_identifier_and_name_match(seeded_db):
    result = cross_verify(seeded_db, _ocr(epic="XYZ0000001", name="Aarav Sharma"))
    assert result.record_found
    assert result.epic_matched
    assert result.name_matched is True
    assert result.status == CheckStatus.PASS


def test_no_matching_record(seeded_db):
    result = cross_verify(seeded_db, _ocr(epic="ZZZ9999999", name="Nobody"))
    assert not result.record_found
    assert result.status == CheckStatus.FAIL


def test_mismatched_name(seeded_db):
    result = cross_verify(seeded_db, _ocr(epic="XYZ0000001", name="Completely Different Name"))
    assert result.record_found
    assert result.name_matched is False
    assert result.status == CheckStatus.FAIL


def test_missing_optional_fields_still_pass(seeded_db):
    result = cross_verify(seeded_db, _ocr(epic="XYZ0000001", name="Aarav Sharma"))
    assert result.status == CheckStatus.PASS


def test_missing_epic_unverifiable(seeded_db):
    result = cross_verify(seeded_db, _ocr(epic=None, name="Aarav Sharma"))
    assert result.status == CheckStatus.UNVERIFIABLE


def test_lookup_by_epic(seeded_db):
    rec = lookup_by_epic(seeded_db, "xyz-0000001")
    assert rec is not None
    assert rec.name == "Aarav Sharma"


def test_database_unavailable(seeded_db, monkeypatch):
    def boom(db, epic):
        raise RuntimeError("db down")

    monkeypatch.setattr("app.services.voter_database.lookup_by_epic", boom)
    result = cross_verify(seeded_db, _ocr(epic="XYZ0000001", name="Aarav Sharma"))
    assert result.status == CheckStatus.UNVERIFIABLE


def test_duplicate_identifiers_are_prevented(seeded_db):
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        seeded_db.add(VoterRecord(epic_number="XYZ0000001", name="Duplicate", source="synthetic_demo"))
        seeded_db.commit()
    seeded_db.rollback()
