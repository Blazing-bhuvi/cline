"""Standalone FastAPI app for MyVote-D (optional; can also be mounted upstream).

Run standalone::

    uvicorn myvote.main:app --host 127.0.0.1 --port 8001

Or mount into upstream's app via ``myvote.api.mount(app)``.

On startup (when the DB is empty) this seeds synthetic data and runs an initial
detection pass. It NEVER deletes voter records.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .audit import AuditChain
from .config import get_config
from .db import get_engine, get_session_factory, init_db
from .eronet import MockERONET
from .flags import run_detection_pass
from .models import Elector


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    session = get_session_factory()()
    try:
        AuditChain(session).bootstrap_genesis()
        if session.query(Elector).count() == 0:
            MockERONET().seed(session)
            session.commit()
        run_detection_pass(session)
        session.commit()
    finally:
        session.close()
    yield


def create_app() -> FastAPI:
    cfg = get_config()
    app = FastAPI(
        title="MyVote-D — Electoral Roll Discrepancy Detection & BLO Verification",
        version="1.0.0",
        description=("Decision-support prototype. Flags roll anomalies and routes "
                     "them to a BLO for physical verification. NEVER auto-deletes "
                     "voter records. Synthetic data only."),
        lifespan=lifespan,
    )
    from .api import router
    from .pages import pages_router
    app.include_router(router)
    app.include_router(pages_router)
    return app


app = create_app()
