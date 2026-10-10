"""Database initialization helpers."""
from __future__ import annotations

from pathlib import Path

from app.core.config import get_settings
from app.database.session import Base, get_engine


def _ensure_sqlite_dir() -> None:
    settings = get_settings()
    url = settings.database_url
    if url.startswith("sqlite"):
        raw = url.replace("sqlite:///", "", 1)
        if raw and raw != ":memory:":
            # Handle Windows drive letters: sqlite:///C:/path -> C:/path
            db_path = Path(raw)
            if not db_path.is_absolute():
                # relative path resolved against cwd (kept for explicit user config)
                db_path = Path.cwd() / db_path
            db_path.parent.mkdir(parents=True, exist_ok=True)


def init_db() -> None:
    """Create all tables (idempotent). Import models so they register on Base."""
    _ensure_sqlite_dir()
    from app.models import orm  # noqa: F401  (registers tables)

    Base.metadata.create_all(bind=get_engine())


def drop_db() -> None:
    """Drop all tables (test helper)."""
    from app.models import orm  # noqa: F401

    Base.metadata.drop_all(bind=get_engine())
