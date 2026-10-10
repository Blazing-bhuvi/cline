"""Text normalization and similarity helpers used for field comparison.

Normalization is intentionally conservative for identifiers: we do NOT map
letters to digits for EPIC numbers beyond stripping separators/case, so that
distinct identifiers are never collapsed into a single value.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

_WS_RE = re.compile(r"\s+")
_NON_ALNUM_RE = re.compile(r"[^A-Za-z0-9]+")


def collapse_whitespace(value: str | None) -> str:
    if not value:
        return ""
    return _WS_RE.sub(" ", value.strip())


def normalize_epic(value: str | None) -> str:
    """Normalize an EPIC number: uppercase, drop separators and punctuation."""
    if not value:
        return ""
    s = value.upper().strip()
    # EPIC numbers are alpha-numeric; drop everything else (spaces, hyphens, etc.)
    return _NON_ALNUM_RE.sub("", s)


def normalize_name(value: str | None) -> str:
    """Normalize a name for comparison: lowercase, collapse whitespace."""
    if not value:
        return ""
    return collapse_whitespace(value).lower()


def normalize_gender(value: str | None) -> str:
    if not value:
        return ""
    v = collapse_whitespace(value).lower()
    if v in {"m", "male", "पुरुष", "पु"}:
        return "male"
    if v in {"f", "female", "महिला", "स्त्री"}:
        return "female"
    if v in {"o", "other", "third", "t", "अन्य"}:
        return "other"
    return v


def normalize_dob(value: str | None) -> str:
    """Normalize a date string to YYYY-MM-DD where possible."""
    if not value:
        return ""
    s = collapse_whitespace(value)
    s = s.replace("/", "-").replace(".", "-").replace("\\", "-")
    m = re.match(r"^(\d{1,2})-(\d{1,2})-(\d{4})$", s)
    if m:
        d, mo, y = m.group(1), m.group(2), m.group(3)
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    m2 = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", s)
    if m2:
        y, mo, d = m2.group(1), m2.group(2), m2.group(3)
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    return s


def sequence_similarity(a: str | None, b: str | None) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def name_similarity(a: str | None, b: str | None) -> float:
    """Combine sequence similarity and word-token Jaccard similarity.

    This is a *similarity* score used only to flag mismatches, never as the sole
    basis for identity.
    """
    na = normalize_name(a)
    nb = normalize_name(b)
    if not na or not nb:
        return 0.0
    seq = SequenceMatcher(None, na, nb).ratio()
    tokens_a = {t for t in re.split(r"\s+", na) if len(t) > 1}
    tokens_b = {t for t in re.split(r"\s+", nb) if len(t) > 1}
    if tokens_a and tokens_b:
        jaccard = len(tokens_a & tokens_b) / len(tokens_a | tokens_b)
    else:
        jaccard = 0.0
    return 0.5 * seq + 0.5 * jaccard
