"""In-memory verification session store with TTL expiry and file cleanup.

Sessions are scoped to this process. Document/face files are stored under a
per-session directory and removed when the session is deleted or expires.
"""
from __future__ import annotations

import secrets
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.schemas.schemas import (
    DocumentAnalysisResult,
    FaceMatchResult,
    FaceQualityResult,
    VerificationResult,
)


@dataclass
class DocumentImage:
    side: str
    filename: str
    path: Path
    width: int
    height: int
    size_bytes: int
    content_type: str


@dataclass
class FaceCapture:
    path: Path
    quality: FaceQualityResult | None = None


@dataclass
class VerificationSession:
    session_id: str
    token: str
    created_at: float
    expires_at: float
    consent: bool
    side_required: str
    images: dict[str, DocumentImage] = field(default_factory=dict)
    portrait_path: Path | None = None
    analysis: DocumentAnalysisResult | None = None
    face_capture: FaceCapture | None = None
    face_match: FaceMatchResult | None = None
    result: VerificationResult | None = None
    stage: str = "upload"
    cancelled: bool = False


class SessionManager:
    def __init__(self, ttl_seconds: int, upload_dir: str | Path) -> None:
        self.ttl = ttl_seconds
        self.upload_dir = Path(upload_dir)
        self._sessions: dict[str, VerificationSession] = {}
        self._lock = threading.Lock()

    def session_dir(self, session_id: str) -> Path:
        return self.upload_dir / session_id

    def create(self, consent: bool, side_required: str) -> VerificationSession:
        session_id = uuid.uuid4().hex
        token = secrets.token_urlsafe(32)
        now = time.time()
        session = VerificationSession(
            session_id=session_id,
            token=token,
            created_at=now,
            expires_at=now + self.ttl,
            consent=consent,
            side_required=side_required,
        )
        self.session_dir(session_id).mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._sessions[session_id] = session
        return session

    def get(self, session_id: str, token: str | None = None) -> VerificationSession | None:
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            return None
        if token is not None and not secrets.compare_digest(session.token, token):
            return None
        if time.time() > session.expires_at:
            self.delete(session_id)
            return None
        return session

    def touch(self, session: VerificationSession) -> None:
        session.expires_at = time.time() + self.ttl

    def delete(self, session_id: str) -> None:
        with self._lock:
            session = self._sessions.pop(session_id, None)
        if session is not None:
            shutil.rmtree(self.session_dir(session_id), ignore_errors=True)

    def cleanup_expired(self) -> int:
        now = time.time()
        expired = [sid for sid, s in self._sessions.items() if now > s.expires_at]
        for sid in expired:
            self.delete(sid)
        return len(expired)

    def count(self) -> int:
        with self._lock:
            return len(self._sessions)


_manager: SessionManager | None = None


def get_session_manager() -> SessionManager:
    global _manager
    if _manager is None:
        from app.core.config import get_settings

        settings = get_settings()
        _manager = SessionManager(settings.session_ttl_seconds, settings.upload_dir)
    return _manager


def reset_session_manager() -> None:
    """Reset the singleton (used in tests)."""
    global _manager
    if _manager is not None:
        for sid in list(_manager._sessions.keys()):
            _manager.delete(sid)
    _manager = None
