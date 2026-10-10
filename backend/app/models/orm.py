"""ORM models for the synthetic demonstration voter database."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class VoterRecord(Base):
    """A single synthetic voter record used for demonstration cross-verification.

    This table is explicitly a *locally seeded demonstration dataset*. It is NOT
    connected to any authoritative or current electoral database.
    """

    __tablename__ = "voter_records"
    __table_args__ = (
        Index("ix_voter_records_name", "name"),
        Index("ix_voter_records_relative_name", "relative_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    epic_number: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    relative_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    gender: Mapped[str | None] = mapped_column(String(20), nullable=True)
    date_of_birth: Mapped[str | None] = mapped_column(String(20), nullable=True)
    age: Mapped[str | None] = mapped_column(String(10), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="synthetic_demo", nullable=False)
    verification_status: Mapped[str] = mapped_column(String(20), default="demo", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow, nullable=False
    )
