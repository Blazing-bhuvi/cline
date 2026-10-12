"""AuditChain tests: append-only + SHA-256 hash-chain integrity + tamper detect."""
from __future__ import annotations

import pytest

from myvote.audit import AuditChain, canonical_json, sha256_hex
from myvote.models import AuditLogEntry


def test_genesis_and_append(session):
    chain = AuditChain(session)
    g = chain.bootstrap_genesis()
    assert g.sequence == 1
    assert g.prev_hash == chain.genesis
    e = chain.append(actor="system", action="FLAG_CREATED",
                     entity_type="discrepancy_flag", entity_id="1",
                     payload={"tier": "HIGH"})
    assert e.sequence == 2
    assert e.prev_hash == g.entry_hash
    assert len(e.entry_hash) == 64


def test_verify_ok_on_clean_chain(session):
    chain = AuditChain(session)
    chain.bootstrap_genesis()
    for i in range(5):
        chain.append(actor="blo", action="FLAG_ASSIGNED",
                     entity_type="discrepancy_flag", entity_id=str(i),
                     payload={"i": i})
    ok, errors = chain.verify()
    assert ok, errors


def test_tamper_is_detected(session):
    chain = AuditChain(session)
    chain.bootstrap_genesis()
    for i in range(4):
        chain.append(actor="blo", action="FLAG_ASSIGNED",
                     entity_type="discrepancy_flag", entity_id=str(i))
    session.commit()
    # Tamper: mutate an actor WITHOUT recomputing the hash.
    victim = session.query(AuditLogEntry).filter(
        AuditLogEntry.sequence == 2).one()
    victim.actor = "attacker"
    session.commit()
    ok, errors = chain.verify()
    assert not ok
    assert any("hash mismatch" in e for e in errors)


def test_deletion_is_detected(session):
    chain = AuditChain(session)
    chain.bootstrap_genesis()
    for i in range(4):
        chain.append(actor="blo", action="FLAG_ASSIGNED",
                     entity_type="discrepancy_flag", entity_id=str(i))
    session.commit()
    # Delete a middle entry -> sequence gap + hash break.
    victim = session.query(AuditLogEntry).filter(
        AuditLogEntry.sequence == 3).one()
    session.delete(victim)
    session.commit()
    ok, errors = chain.verify()
    assert not ok
    assert any("sequence gap" in e for e in errors)


def test_canonical_json_is_stable():
    assert canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'
    assert canonical_json({"a": 2, "b": 1}) == '{"a":2,"b":1}'


def test_sha256_hex_length():
    assert len(sha256_hex("x")) == 64


def test_no_append_only_violation_no_update_api(session):
    # Guard rail: AuditChain exposes append/verify only — no update/delete.
    chain = AuditChain(session)
    assert not hasattr(chain, "update")
    assert not hasattr(chain, "delete")
    assert not hasattr(chain, "remove")
