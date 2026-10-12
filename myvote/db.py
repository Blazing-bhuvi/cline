"""Database engine & session management (SQLAlchemy 2.0 style) for MyVote-D.

Uses its OWN ``Base`` (separate from upstream's ``app.database.session.Base``)
so the two subsystems never share a metadata registry. The SQLite URL from
``myvote/config.yaml`` is anchored to the ``myvote`` package dir, so the DB
lives at ``myvote/data/electoral.db`` and cannot collide with upstream's
``data/voter.db``.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import PROJECT_ROOT, get_config


class Base(DeclarativeBase):
    """Declarative base shared by all MyVote-D ORM models."""


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _resolve_sqlite_path(url: str) -> str:
    """Rewrite a relative sqlite URL to be anchored at the myvote package dir."""
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        return url
    rel = url[len(prefix):]
    candidate = Path(rel)
    if candidate.is_absolute():
        return url
    abs_path = (PROJECT_ROOT / rel).resolve()
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    return f"{prefix}{abs_path.as_posix()}"


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        url = get_config().get("database.url", "sqlite:///./data/electoral.db")
        echo = bool(get_config().get("database.echo", False))
        # Allow tests / callers to override via env var (in-memory for pytest).
        override = os.environ.get("MYVOTE_DB_URL")
        if override:
            url = override
        elif url.startswith("sqlite:"):
            url = _resolve_sqlite_path(url)
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        _engine = create_engine(url, echo=echo, future=True, connect_args=connect_args)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), autoflush=False,
                                     autocommit=False, expire_on_commit=False,
                                     class_=Session, future=True)
    return _SessionLocal


def get_session() -> Iterator[Session]:
    """FastAPI-style dependency that yields a session and always closes it."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def init_db() -> None:
    """Create all MyVote-D tables. Import models so they register on ``Base``."""
    from . import models  # noqa: F401  (ensures models are imported/registered)
    Base.metadata.create_all(bind=get_engine())


def reset_engine_for_tests(url: str = "sqlite+pysqlite:///:memory:") -> None:
    """Test helper: tear down the cached engine/session and re-create them
    against a fresh (default in-memory) database with all tables."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
    os.environ["MYVOTE_DB_URL"] = url
    engine = get_engine()
    from . import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
