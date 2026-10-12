"""Enumerations for the electoral roll discrepancy system.

All values are stored as plain strings in the database so the prototype stays
portable across SQLite versions. Using str-Enums keeps JSON serialisation
trivial.
"""
from __future__ import annotations

import enum


class ConfidenceTier(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class FlagState(str, enum.Enum):
    FLAGGED = "FLAGGED"
    ASSIGNED = "ASSIGNED"
    BLO_REVIEW = "BLO_REVIEW"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"


class FlagCategory(str, enum.Enum):
    DUPLICATE = "DUPLICATE"                    # probable duplicate entry (DSD+PSD)
    TRANSLITERATION = "TRANSLITERATION"        # name variant, needs human check
    UNDERAGE = "UNDERAGE"                      # age < 18 at enrolment
    FORM7_ABUSE = "FORM7_ABUSE"                # bulk/abusive Form 7 deletion pattern
    FAKE_DELETION = "FAKE_DELETION"            # suspicious Form 7 deletion request


class FormType(str, enum.Enum):
    FORM_6 = "FORM_6"   # new inclusion
    FORM_7 = "FORM_7"   # deletion of an existing entry
    FORM_8 = "FORM_8"   # correction / objection to a particular entry


class BLOReviewDecision(str, enum.Enum):
    CONFIRM = "CONFIRM"    # BLO confirms the discrepancy is genuine
    REJECT = "REJECT"      # BLO rejects the flag (no discrepancy found)


class AuditAction(str, enum.Enum):
    FLAG_CREATED = "FLAG_CREATED"
    FLAG_ASSIGNED = "FLAG_ASSIGNED"
    BLO_REVIEW_SUBMITTED = "BLO_REVIEW_SUBMITTED"
    FLAG_ESCALATED = "FLAG_ESCALATED"
    FLAG_CONFIRMED = "FLAG_CONFIRMED"
    FLAG_REJECTED = "FLAG_REJECTED"
    FIR_TRIGGERED = "FIR_TRIGGERED"
    DOSSIER_GENERATED = "DOSSIER_GENERATED"
    SESSION_STARTED = "SESSION_STARTED"
    SESSION_ENDED = "SESSION_ENDED"
    GENESIS = "GENESIS"
