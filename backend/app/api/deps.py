"""API dependencies and shared helpers."""
from __future__ import annotations

from fastapi import Header, HTTPException

from app.services.session_manager import VerificationSession, get_session_manager


def resolve_session(session_id: str, x_session_token: str | None = Header(default=None)) -> VerificationSession:
    """Resolve a session by ID + token, enforcing session ownership."""
    if not x_session_token:
        raise HTTPException(status_code=401, detail="Missing session token.")
    session = get_session_manager().get(session_id, x_session_token)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found or token invalid.")
    return session
