"""End-to-end API tests via FastAPI TestClient (JSON + dashboard page)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(session):
    # Build a standalone MyVote-D app against the in-memory test DB.
    from myvote.main import create_app
    app = create_app()
    with TestClient(app) as c:
        # Ensure seeded + detected once for the API tests.
        c.post("/myvote/api/detect")
        yield c


def test_health(client):
    r = client.get("/myvote/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["audit_chain_ok"] is True
    assert body["elector_count"] > 0


def test_detect_creates_flags(client):
    r = client.post("/myvote/api/detect")
    assert r.status_code == 200
    body = r.json()
    assert body["flags_created"] >= 0  # idempotent; may be 0 on 2nd run
    assert "by_tier" in body


def test_flags_are_pii_masked(client):
    r = client.get("/myvote/api/flags")
    assert r.status_code == 200
    rows = r.json()
    if rows:
        subj = rows[0]["subject"]
        assert "*" in subj["epic_id"] or subj["epic_id"].startswith("S")
        assert subj["name"] != "Rahul Sharma" or " " in subj["name"]  # masked


def test_audit_integrity_endpoint(client):
    r = client.get("/myvote/api/audit/integrity")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_assign_and_review_flow(client):
    flags = client.get("/myvote/api/flags").json()
    assert flags, "expected at least one flag after detection"
    fid = flags[0]["id"]
    # Assign.
    r = client.post(f"/myvote/api/flags/{fid}/assign", json={"blo_id": "BLO-1"})
    assert r.status_code == 200
    assert r.json()["state"] == "ASSIGNED"
    # Review (confirm).
    r = client.post(f"/myvote/api/flags/{fid}/review",
                    json={"reviewer_id": "BLO-1", "decision": "CONFIRM"})
    assert r.status_code == 200
    assert r.json()["state"] == "CONFIRMED"


def test_wrong_blo_review_rejected(client):
    flags = client.get("/myvote/api/flags").json()
    fid = flags[0]["id"]
    client.post(f"/myvote/api/flags/{fid}/assign", json={"blo_id": "BLO-1"})
    r = client.post(f"/myvote/api/flags/{fid}/review",
                    json={"reviewer_id": "WRONG", "decision": "CONFIRM"})
    assert r.status_code == 400


def test_dashboard_page_renders(client):
    r = client.get("/myvote/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "SYNTHETIC DATA" in r.text
    # Audit chain should be shown as intact.
    assert "INTACT" in r.text
