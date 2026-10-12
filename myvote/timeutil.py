"""Shared time helpers.

We store NAIVE UTC datetimes in SQLite for portability, but obtain them in a
future-proof way that avoids the deprecated ``datetime.utcnow()``.
"""
from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Return the current UTC time as a naive datetime (for SQLite storage)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
