"""Database cross-verification against the locally seeded demonstration dataset."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.orm import VoterRecord
from app.schemas.schemas import CheckStatus, DatabaseMatchResult, FieldMatch
from app.utils.text_utils import (
    name_similarity,
    normalize_dob,
    normalize_epic,
    normalize_gender,
    normalize_name,
)


def lookup_by_epic(db: Session, epic: str) -> VoterRecord | None:
    normalized = normalize_epic(epic)
    if not normalized:
        return None
    stmt = select(VoterRecord).where(VoterRecord.epic_number == normalized)
    return db.execute(stmt).scalars().first()


def cross_verify(
    db: Session,
    ocr_fields: dict,
    name_threshold: float = 0.85,
) -> DatabaseMatchResult:
    """Cross-verify OCR fields against the demonstration database.

    A *missing* record is reported as a mismatch *within the demo dataset*, but
    explicitly does NOT prove the physical card is fake.
    """
    epic_raw = ocr_fields.get("epic", {}).get("value")
    epic = normalize_epic(epic_raw)

    if not epic:
        return DatabaseMatchResult(
            status=CheckStatus.UNVERIFIABLE,
            reason="EPIC number not readable; unable to query the database.",
        )

    try:
        record = lookup_by_epic(db, epic)
    except Exception as exc:  # pragma: no cover - DB failure path
        return DatabaseMatchResult(
            status=CheckStatus.UNVERIFIABLE,
            reason=f"database unavailable: {type(exc).__name__}",
        )

    if record is None:
        return DatabaseMatchResult(
            status=CheckStatus.FAIL,
            record_found=False,
            epic_matched=False,
            reason=(
                "No record matches the EPIC number in the demonstration database. "
                "This does not prove the physical card is fake."
            ),
        )

    field_matches: list[FieldMatch] = []
    name_ocr = ocr_fields.get("name", {}).get("value")
    name_sim = name_similarity(name_ocr, record.name) if name_ocr else None
    name_matched = name_sim is not None and name_sim >= name_threshold

    field_matches.append(
        FieldMatch(
            field="epic",
            ocr_value=epic,
            db_value=record.epic_number,
            matched=True,
            similarity=1.0,
            reason="exact match after normalization",
        )
    )
    field_matches.append(
        FieldMatch(
            field="name",
            ocr_value=normalize_name(name_ocr),
            db_value=normalize_name(record.name),
            matched=name_matched,
            similarity=name_sim,
            reason=_name_reason(name_sim, name_threshold),
        )
    )

    # Optional field comparisons (informational only)
    for field, key, normalizer in (
        ("gender", "gender", normalize_gender),
        ("date_of_birth", "date_of_birth", normalize_dob),
        ("relative_name", "relative_name", normalize_name),
    ):
        ocr_val = ocr_fields.get(field, {}).get("value")
        db_val = getattr(record, key, None)
        if ocr_val is not None and db_val is not None:
            norm_o, norm_d = normalizer(ocr_val), normalizer(db_val)
            matched = norm_o == norm_d
            field_matches.append(
                FieldMatch(
                    field=field,
                    ocr_value=norm_o,
                    db_value=norm_d,
                    matched=matched,
                    similarity=1.0 if matched else 0.0,
                    reason="exact match after normalization" if matched else "values differ",
                )
            )

    if name_matched is True:
        status = CheckStatus.PASS
        reason = "Record found and name matches within threshold."
    elif name_matched is False:
        status = CheckStatus.FAIL
        reason = "Record found but name does not match."
    else:
        status = CheckStatus.INCONCLUSIVE
        reason = "Record found but name could not be compared."

    return DatabaseMatchResult(
        status=status,
        record_found=True,
        record_id=record.id,
        epic_matched=True,
        name_matched=name_matched,
        field_matches=field_matches,
        source=record.source,
        reason=reason,
    )


def _name_reason(sim: float | None, threshold: float) -> str:
    if sim is None:
        return "OCR name unavailable for comparison"
    if sim >= threshold:
        return f"similarity {sim:.2f} >= threshold {threshold:.2f}"
    return f"similarity {sim:.2f} < threshold {threshold:.2f}"
