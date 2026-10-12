"""Append-only, SHA-256 hash-chained audit log for MyVote-D.

Every state change in the system is recorded here. Each entry stores
``entry_hash = SHA-256(canonical_json(payload) + prev_hash)``. The first entry
chains from a genesis hash defined in ``config.yaml`` (64 hex zeros).

Integrity check: recompute each entry's hash from its stored payload + the
previous entry's hash. If any row was inserted, edited, reordered, or removed,
the chain breaks and :meth:`AuditChain.verify` reports the exact sequence number.

This module NEVER updates or deletes an existing entry (append-only by design).
"""
from __future__ import annotations

import hashlib
import json
from typing import Iterable

from sqlalchemy.orm import Session

from .config import Config, get_config
from .models import AuditLogEntry
from .timeutil import utcnow


def canonical_json(obj) -> str:
    """Deterministic JSON (sorted keys, no whitespace) for stable hashing."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


class AuditChain:
    """Hash-chained, append-only audit log backed by the ``audit_log`` table."""

    def __init__(self, session: Session, config: Config | None = None):
        self.session = session
        self.config = config or get_config()
        self.genesis = str(self.config.get("audit.genesis_hash", "0" * 64))

    # ------------------------------------------------------------------ #
    def _last_entry(self) -> AuditLogEntry | None:
        return (self.session.query(AuditLogEntry)
                .order_by(AuditLogEntry.sequence.desc())
                .first())

    def _next_sequence(self) -> int:
        last = self._last_entry()
        return 1 if last is None else last.sequence + 1

    def append(self, *, actor: str, action: str, entity_type: str,
               entity_id: str, payload: dict | None = None) -> AuditLogEntry:
        """Append a new entry, chaining from the previous entry's hash.

        This is the ONLY write path. There is deliberately no update/delete.
        """
        prev = self._last_entry()
        prev_hash = self.genesis if prev is None else prev.entry_hash
        seq = 1 if prev is None else prev.sequence + 1

        body = {
            "sequence": seq,
            "actor": str(actor),
            "action": str(action),
            "entity_type": str(entity_type),
            "entity_id": str(entity_id),
            "payload": payload or {},
        }
        payload_json = canonical_json(body)
        entry_hash = sha256_hex(payload_json + prev_hash)

        entry = AuditLogEntry(
            sequence=seq,
            timestamp=utcnow(),
            actor=body["actor"],
            action=body["action"],
            entity_type=body["entity_type"],
            entity_id=body["entity_id"],
            payload=payload_json,
            prev_hash=prev_hash,
            entry_hash=entry_hash,
        )
        self.session.add(entry)
        self.session.flush()
        return entry

    def bootstrap_genesis(self, actor: str = "system") -> AuditLogEntry:
        """Create the genesis entry if the chain is empty."""
        if self._last_entry() is not None:
            return self._last_entry()
        return self.append(actor=actor, action="GENESIS",
                           entity_type="system", entity_id="0",
                           payload={"note": "audit chain initialised"})

    # ------------------------------------------------------------------ #
    def verify(self) -> tuple[bool, list[str]]:
        """Recompute the whole chain. Returns (ok, errors)."""
        entries = (self.session.query(AuditLogEntry)
                   .order_by(AuditLogEntry.sequence.asc())
                   .all())
        errors: list[str] = []
        prev_hash = self.genesis
        expected_seq = 1
        for e in entries:
            if e.sequence != expected_seq:
                errors.append(
                    f"sequence gap: expected {expected_seq}, found {e.sequence}")
            body = {
                "sequence": e.sequence,
                "actor": e.actor,
                "action": e.action,
                "entity_type": e.entity_type,
                "entity_id": e.entity_id,
                "payload": json.loads(e.payload)["payload"] if e.payload else {},
            }
            recomputed = sha256_hex(canonical_json(body) + prev_hash)
            if recomputed != e.entry_hash:
                errors.append(
                    f"hash mismatch at sequence {e.sequence}: "
                    f"stored {e.entry_hash[:12]}… recomputed {recomputed[:12]}…")
            if e.prev_hash != prev_hash:
                errors.append(
                    f"prev_hash mismatch at sequence {e.sequence}")
            prev_hash = e.entry_hash
            expected_seq += 1
        return (len(errors) == 0, errors)

    def entries(self) -> Iterable[AuditLogEntry]:
        return (self.session.query(AuditLogEntry)
                .order_by(AuditLogEntry.sequence.asc())
                .all())
