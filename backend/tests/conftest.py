"""Shared test fixtures and environment setup."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Point the app at an isolated temp DB and artifact dirs BEFORE importing app modules.
_TMP = Path(tempfile.mkdtemp(prefix="voter_id_test_"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["UPLOAD_DIR"] = str(_TMP / "uploads")
os.environ["MODEL_DIR"] = str(_TMP / "models")

import pytest  # noqa: E402

from app.core.config import get_settings  # noqa: E402


@pytest.fixture()
def db_session():
    from app.database.init_db import drop_db, init_db
    from app.database.session import get_session_local

    drop_db()
    init_db()
    session = get_session_local()()
    yield session
    session.close()


@pytest.fixture()
def seeded_db(db_session):
    from scripts.seed_demo_data import seed

    seed(overwrite=True)
    return db_session


@pytest.fixture(scope="session")
def sample_card_path() -> Path:
    from scripts.generate_sample_card import DEFAULT_RECORD, generate_card

    out = _TMP / "specimen_card.png"
    generate_card(DEFAULT_RECORD, out, with_qr=True)
    return out


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c
