"""Security for MyVote-D: TOTP auth, session timeouts, and DPDP PII masking.

Three concerns:
  1. Mock BLO authentication using TOTP (pyotp). In a real deployment the secret
     would be provisioned per-BLO out-of-band; here we generate/provision mock
     secrets so the flow is demonstrable end-to-end.
  2. Session enforcement: 15-minute ABSOLUTE timeout and 5-minute IDLE timeout.
  3. PII masking for public-facing dashboards (DPDP-inspired). Raw PII is only
     ever shown on the authenticated BLO review view.
"""
from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from datetime import timedelta

import pyotp

from .config import Config, get_config
from .timeutil import utcnow


# --------------------------------------------------------------------------- #
#  TOTP (mock BLO authentication)
# --------------------------------------------------------------------------- #
class TOTPAuthenticator:
    """Provision and verify TOTP codes for BLO reviewers (mock secrets)."""

    def __init__(self, config: Config | None = None):
        self.config = config or get_config()
        self.issuer = str(self.config.get("auth.totp.issuer", "BLO-Verification"))
        self.digits = int(self.config.get("auth.totp.digits", 6))
        self.interval = int(self.config.get("auth.totp.interval_seconds", 30))
        # In-memory mock provisioning store: blo_id -> base32 secret.
        self._secrets: dict[str, str] = {}

    def provision(self, blo_id: str) -> str:
        """Create (or return) a mock TOTP secret for a BLO. NOT a real secret."""
        secret = pyotp.random_base32()
        self._secrets[blo_id] = secret
        return secret

    def current_code(self, blo_id: str) -> str:
        """Return the current valid code (test/demo helper — never log this)."""
        if blo_id not in self._secrets:
            raise KeyError(f"BLO {blo_id} is not provisioned")
        totp = pyotp.TOTP(self._secrets[blo_id], digits=self.digits,
                          interval=self.interval)
        return totp.now()

    def verify(self, blo_id: str, code: str, *, valid_window: int = 1) -> bool:
        """Verify a TOTP code with a small clock-skew window."""
        secret = self._secrets.get(blo_id)
        if not secret or not code:
            return False
        totp = pyotp.TOTP(secret, digits=self.digits, interval=self.interval)
        return bool(totp.verify(code, valid_window=valid_window))


# --------------------------------------------------------------------------- #
#  BLO session with absolute + idle timeouts
# --------------------------------------------------------------------------- #
@dataclass
class BLOSession:
    session_id: str
    blo_id: str
    created_at: float           # epoch seconds
    last_active_at: float       # epoch seconds
    absolute_timeout: int       # seconds
    idle_timeout: int           # seconds

    def is_expired(self, now: float | None = None) -> bool:
        now = now if now is not None else time.time()
        if now - self.created_at > self.absolute_timeout:
            return True
        if now - self.last_active_at > self.idle_timeout:
            return True
        return False

    def touch(self, now: float | None = None) -> None:
        self.last_active_at = now if now is not None else time.time()


class BLOSessionManager:
    """In-memory session store enforcing absolute + idle timeouts."""

    def __init__(self, config: Config | None = None):
        self.config = config or get_config()
        self.absolute_timeout = int(
            self.config.get("auth.session.absolute_timeout_minutes", 15)) * 60
        self.idle_timeout = int(
            self.config.get("auth.session.idle_timeout_minutes", 5)) * 60
        self._sessions: dict[str, BLOSession] = {}

    def create(self, blo_id: str) -> BLOSession:
        now = time.time()
        session = BLOSession(
            session_id=secrets.token_urlsafe(24),
            blo_id=blo_id,
            created_at=now,
            last_active_at=now,
            absolute_timeout=self.absolute_timeout,
            idle_timeout=self.idle_timeout,
        )
        self._sessions[session.session_id] = session
        return session

    def get_valid(self, session_id: str) -> BLOSession | None:
        """Return the session if present AND not expired; else drop + None."""
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if session.is_expired():
            self._sessions.pop(session_id, None)
            return None
        session.touch()
        return session

    def end(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def cleanup(self) -> int:
        now = time.time()
        expired = [sid for sid, s in self._sessions.items() if s.is_expired(now)]
        for sid in expired:
            self._sessions.pop(sid, None)
        return len(expired)


# --------------------------------------------------------------------------- #
#  DPDP-inspired PII masking (public-facing dashboards)
# --------------------------------------------------------------------------- #
class PIIMasker:
    """Mask PII for public views. Raw values are only for the authenticated
    BLO review view (never call these on that view)."""

    def __init__(self, config: Config | None = None):
        self.config = config or get_config()
        self.enabled = bool(self.config.get("pii_masking.enabled", True))
        self.reveal = int(self.config.get("pii_masking.reveal_last_n_digits", 2))
        self.min_mask = int(self.config.get("pii_masking.min_mask_length", 4))

    def _mask(self, value: str, reveal_prefix: int = 1) -> str:
        value = str(value or "")
        if not value:
            return value
        if len(value) <= self.min_mask:
            return value[0] + "*" * (len(value) - 1)
        stars = "*" * (len(value) - reveal_prefix)
        return value[:reveal_prefix] + stars

    def mask_epic(self, epic: str) -> str:
        """ABC1234567 -> A********67  (reveal first char + last N digits)."""
        if not self.enabled or not self.config.get("pii_masking.mask_epic_id", True):
            return epic
        epic = str(epic or "")
        if len(epic) <= self.reveal + 1:
            return self._mask(epic)
        head = epic[:1]
        tail = epic[-self.reveal:] if self.reveal else ""
        stars = "*" * (len(epic) - 1 - self.reveal)
        return f"{head}{stars}{tail}"

    def mask_name(self, name: str) -> str:
        """'Rajesh Kumar' -> 'R***** K****' (first letter of each token)."""
        if not self.enabled or not self.config.get("pii_masking.mask_name", True):
            return name
        tokens = str(name or "").split()
        masked = []
        for tok in tokens:
            masked.append(tok[0] + "*" * max(0, len(tok) - 1))
        return " ".join(masked)

    def mask_dob_to_age_band(self, dob) -> str:
        """Reveal only a coarse age band, never the exact DOB."""
        if not self.enabled or not self.config.get("pii_masking.mask_dob", True):
            return dob.isoformat() if dob else ""
        from .detection import age_on
        age = age_on(dob)
        low = (age // 10) * 10
        return f"{low}-{low + 9} yrs"

    def mask_address(self, house_number: str, locality: str) -> str:
        """Reveal house number + locality code only (not full address)."""
        if not self.enabled or not self.config.get("pii_masking.mask_address", True):
            return f"{house_number}, {locality}"
        loc = str(locality or "")
        code = loc[:3].upper() if loc else "?"
        return f"H#{house_number}, {code}…"


# Module-level convenience singleton + functions (used by routers/templates).
_masker: PIIMasker | None = None


def get_masker() -> PIIMasker:
    global _masker
    if _masker is None:
        _masker = PIIMasker()
    return _masker


def mask_elector_public(elector) -> dict:
    """Return a PII-masked, JSON-safe public view of an elector."""
    m = get_masker()
    return {
        "id": elector.id,
        "epic_id": m.mask_epic(elector.epic_id),
        "name": m.mask_name(elector.name),
        "age_band": m.mask_dob_to_age_band(elector.dob),
        "area": m.mask_address(elector.house_number, elector.locality),
        "constituency": elector.constituency,  # non-PII geographic label
    }

