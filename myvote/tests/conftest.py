"""Shared fixtures for the MyVote-D test-suite.

Points MyVote-D at an isolated temp-file SQLite DB via ``MYVOTE_DB_URL`` BEFORE
importing any ``myvote`` module that builds the engine. A temp FILE (not
``:memory:``) is used so the FastAPI TestClient's worker thread shares the same
database as the test's session (SQLite ``:memory:`` databases are per-connection).
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Make the repo root importable so `import myvote` works when running pytest
# from either the repo root or the myvote/ directory.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# One temp-file DB shared by every test (the `session` fixture drops/recreates
# tables around each test for isolation).
_TMP_DB = Path(tempfile.gettempdir()) / f"myvote_test_{os.getpid()}.db"
os.environ["MYVOTE_DB_URL"] = f"sqlite+pysqlite:///{_TMP_DB.as_posix()}"

import pytest  # noqa: E402

from myvote.db import Base, get_engine, get_session_factory  # noqa: E402


@pytest.fixture()
def session():
    """Fresh DB with all MyVote-D tables; torn down after the test."""
    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    factory = get_session_factory()
    sess = factory()
    try:
        yield sess
    finally:
        sess.close()


@pytest.fixture()
def seeded(session):
    """Seed synthetic data and return (session, ground_truth)."""
    from myvote.eronet import MockERONET
    truth = MockERONET(seed=42).seed(session)
    return session, truth

