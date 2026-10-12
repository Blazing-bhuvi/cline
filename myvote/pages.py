"""Server-rendered Jinja2 dashboard pages for MyVote-D (served at ``/myvote``).

Public views are PII-masked. The page router is separate from the JSON API so
it can be mounted independently. Templates live in ``myvote/templates``.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from .audit import AuditChain
from .db import get_session
from .enums import FlagState
from .models import DiscrepancyFlag, Elector
from .security import mask_elector_public

# Render templates manually (env.get_template(...).render(...)) rather than via
# Jinja2Templates.TemplateResponse. On newer Starlette/Jinja2 the TemplateResponse
# bytecode cache hashes the full render context, which fails when the context
# contains nested dicts/lists (our PII-masked rows). Manual rendering is
# version-robust and avoids that failure.
from jinja2 import Environment, FileSystemLoader, select_autoescape  # noqa: E402

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)

pages_router = APIRouter(prefix="/myvote", tags=["myvote-pages"])


@pages_router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    chain = AuditChain(session)
    audit_ok, audit_errors = chain.verify()
    audit_entries = chain.entries()

    flags = (session.query(DiscrepancyFlag)
             .order_by(DiscrepancyFlag.id.desc()).all())

    open_flags = [f for f in flags if str(f.state) not in
                  (FlagState.CONFIRMED.value, FlagState.REJECTED.value)]
    high = [f for f in open_flags if str(f.tier) == "HIGH"]

    # Public, PII-masked rows for the dashboard table.
    rows = [{
        "id": f.id,
        "category": str(f.category),
        "state": str(f.state),
        "tier": str(f.tier),
        "confidence": f.confidence,
        "subject": mask_elector_public(f.elector),
        "explanation": f.explanation,
        "fir_triggered": f.fir_triggered,
    } for f in flags]

    context = {
        "app_name": "MyVote-D — Discrepancy Detection & BLO Verification",
        "status": {
            "elector_count": session.query(Elector).count(),
            "flag_count": len(flags),
            "open_flags": len(open_flags),
            "high_flags": len(high),
            "audit_ok": audit_ok,
            "audit_entries": len(audit_entries),
            "audit_errors": audit_errors[:5],
        },
        "rows": rows,
    }
    html = _jinja_env.get_template("dashboard.html").render(**context)
    return HTMLResponse(content=html)
