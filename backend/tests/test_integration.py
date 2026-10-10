"""API integration tests (real OCR/QR/DB for document stage; mocked face CV)."""
from __future__ import annotations

import io

import cv2
import numpy as np

from app.schemas.schemas import (
    CheckStatus,
    DatabaseMatchResult,
    FaceMatchResult,
    FaceQualityResult,
    MatchResult,
    OverallStatus,
)
from app.services import verification_service


def _png_bytes(arr: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", arr)
    return buf.tobytes()


def _small_img(w=200, h=200):
    return np.full((h, w, 3), 128, dtype=np.uint8)


def _start(client, consent=True):
    return client.post("/api/verification/start", json={"consent": consent, "side_required": "front"})


def _upload(client, token, session_id, data: bytes, side="front"):
    return client.post(
        f"/api/verification/{session_id}/document",
        files={"file": ("card.png", io.BytesIO(data), "image/png")},
        data={"side": side},
        headers={"X-Session-Token": token},
    )


def _headers(token):
    return {"X-Session-Token": token}


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["demo_mode"] is True


def test_start_requires_consent(client):
    r = _start(client, consent=False)
    assert r.status_code == 400


def test_session_token_required(client):
    r = client.get("/api/verification/does-not-exist/result")
    assert r.status_code == 401


def test_full_success_flow(client, seeded_db, sample_card_path, monkeypatch):
    monkeypatch.setattr(
        verification_service,
        "assess_face_quality",
        lambda img: FaceQualityResult(status=CheckStatus.PASS, face_detected=True),
    )
    monkeypatch.setattr(
        verification_service,
        "match_faces",
        lambda matcher, a, b: FaceMatchResult(
            status=CheckStatus.PASS, match_result=MatchResult.MATCH, similarity=0.9
        ),
    )

    r = _start(client)
    assert r.status_code == 201
    session_id = r.json()["session_id"]
    token = r.json()["token"]

    up = _upload(client, token, session_id, sample_card_path.read_bytes())
    assert up.status_code == 200

    an = client.post(f"/api/verification/{session_id}/analyze", headers=_headers(token))
    assert an.status_code == 200
    body = an.json()
    assert body["preliminary_pass"] is True
    assert body["database"]["status"] == "PASS"
    assert body["qr"]["status"] == "PASS"

    face = client.post(
        f"/api/verification/{session_id}/face",
        files={"file": ("face.png", io.BytesIO(_png_bytes(_small_img())), "image/png")},
        headers=_headers(token),
    )
    assert face.status_code == 200
    assert face.json()["accepted"] is True

    res = client.get(f"/api/verification/{session_id}/result", headers=_headers(token))
    assert res.status_code == 200
    assert res.json()["overall_status"] == OverallStatus.PASS.value

def test_document_rejection_flow(client, seeded_db, monkeypatch, tmp_path):
    from scripts.generate_sample_card import DEFAULT_RECORD, generate_card

    record = dict(DEFAULT_RECORD)
    record["epic"] = "ZZZ9999999"
    card = tmp_path / "mismatch_card.png"
    generate_card(record, card, with_qr=True)

    r = _start(client)
    session_id = r.json()["session_id"]
    token = r.json()["token"]

    _upload(client, token, session_id, card.read_bytes())
    an = client.post(f"/api/verification/{session_id}/analyze", headers=_headers(token))
    assert an.status_code == 200
    assert an.json()["preliminary_pass"] is False
    assert an.json()["database"]["status"] == "FAIL"

    res = client.get(f"/api/verification/{session_id}/result", headers=_headers(token))
    assert res.json()["overall_status"] == OverallStatus.REJECTED.value


def test_face_mismatch_flow(client, seeded_db, sample_card_path, monkeypatch):
    monkeypatch.setattr(
        verification_service,
        "assess_face_quality",
        lambda img: FaceQualityResult(status=CheckStatus.PASS, face_detected=True),
    )
    monkeypatch.setattr(
        verification_service,
        "match_faces",
        lambda matcher, a, b: FaceMatchResult(
            status=CheckStatus.FAIL, match_result=MatchResult.MISMATCH, similarity=0.1
        ),
    )

    r = _start(client)
    session_id = r.json()["session_id"]
    token = r.json()["token"]

    _upload(client, token, session_id, sample_card_path.read_bytes())
    client.post(f"/api/verification/{session_id}/analyze", headers=_headers(token))

    face = client.post(
        f"/api/verification/{session_id}/face",
        files={"file": ("face.png", io.BytesIO(_png_bytes(_small_img())), "image/png")},
        headers=_headers(token),
    )
    assert face.json()["accepted"] is True

    res = client.get(f"/api/verification/{session_id}/result", headers=_headers(token))
    assert res.json()["overall_status"] == OverallStatus.REJECTED.value


def test_camera_quality_retry_flow(client, seeded_db, sample_card_path, monkeypatch):
    calls = {"n": 0}

    def fake_quality(img):
        calls["n"] += 1
        if calls["n"] == 1:
            return FaceQualityResult(status=CheckStatus.INCONCLUSIVE, face_detected=True)
        return FaceQualityResult(status=CheckStatus.PASS, face_detected=True)

    monkeypatch.setattr(verification_service, "assess_face_quality", fake_quality)
    monkeypatch.setattr(
        verification_service,
        "match_faces",
        lambda matcher, a, b: FaceMatchResult(
            status=CheckStatus.PASS, match_result=MatchResult.MATCH, similarity=0.9
        ),
    )

    r = _start(client)
    session_id = r.json()["session_id"]
    token = r.json()["token"]

    _upload(client, token, session_id, sample_card_path.read_bytes())
    client.post(f"/api/verification/{session_id}/analyze", headers=_headers(token))

    face = client.post(
        f"/api/verification/{session_id}/face",
        files={"file": ("face.png", io.BytesIO(_png_bytes(_small_img())), "image/png")},
        headers=_headers(token),
    )
    assert face.json()["accepted"] is False

    retry = client.post(f"/api/verification/{session_id}/retry", headers=_headers(token))
    assert retry.json()["ok"] is True
    assert retry.json()["retriable_stage"] == "face"

    face2 = client.post(
        f"/api/verification/{session_id}/face",
        files={"file": ("face.png", io.BytesIO(_png_bytes(_small_img())), "image/png")},
        headers=_headers(token),
    )
    assert face2.json()["accepted"] is True


def test_database_outage_flow(client, seeded_db, sample_card_path, monkeypatch):
    def down(db, ocr_fields, name_threshold=0.85):
        return DatabaseMatchResult(status=CheckStatus.UNVERIFIABLE, reason="database unavailable")

    monkeypatch.setattr(verification_service.voter_database, "cross_verify", down)

    r = _start(client)
    session_id = r.json()["session_id"]
    token = r.json()["token"]

    _upload(client, token, session_id, sample_card_path.read_bytes())
    an = client.post(f"/api/verification/{session_id}/analyze", headers=_headers(token))
    assert an.json()["database"]["status"] == "UNVERIFIABLE"

    res = client.get(f"/api/verification/{session_id}/result", headers=_headers(token))
    assert res.json()["overall_status"] == OverallStatus.INCONCLUSIVE.value


def test_session_cleanup(client, seeded_db, sample_card_path, monkeypatch):
    monkeypatch.setattr(
        verification_service,
        "assess_face_quality",
        lambda img: FaceQualityResult(status=CheckStatus.PASS, face_detected=True),
    )
    monkeypatch.setattr(
        verification_service,
        "match_faces",
        lambda matcher, a, b: FaceMatchResult(
            status=CheckStatus.PASS, match_result=MatchResult.MATCH, similarity=0.9
        ),
    )

    r = _start(client)
    session_id = r.json()["session_id"]
    token = r.json()["token"]
    _upload(client, token, session_id, sample_card_path.read_bytes())
    client.post(f"/api/verification/{session_id}/analyze", headers=_headers(token))

    d = client.delete(f"/api/verification/{session_id}", headers=_headers(token))
    assert d.status_code == 200

    res = client.get(f"/api/verification/{session_id}/result", headers=_headers(token))
    assert res.status_code == 404


def test_front_back_matching(client, seeded_db, sample_card_path, tmp_path):
    from scripts.generate_sample_card import DEFAULT_RECORD, generate_back_card

    back_card = tmp_path / "back.png"
    generate_back_card(DEFAULT_RECORD, back_card)

    r = _start(client)
    session_id = r.json()["session_id"]
    token = r.json()["token"]

    _upload(client, token, session_id, sample_card_path.read_bytes(), side="front")
    _upload(client, token, session_id, back_card.read_bytes(), side="back")
    an = client.post(f"/api/verification/{session_id}/analyze", headers=_headers(token))

    body = an.json()
    assert body["sides"]["status"] == "PASS"
    assert body["sides"]["epic_matches"] is True
    assert body["preliminary_pass"] is True


def test_front_back_mismatch(client, seeded_db, sample_card_path, tmp_path):
    from scripts.generate_sample_card import DEFAULT_RECORD, generate_card

    record = dict(DEFAULT_RECORD)
    record["epic"] = "ZZZ9999999"
    wrong_back = tmp_path / "wrong_back.png"
    generate_card(record, wrong_back, with_qr=False)

    r = _start(client)
    session_id = r.json()["session_id"]
    token = r.json()["token"]

    _upload(client, token, session_id, sample_card_path.read_bytes(), side="front")
    _upload(client, token, session_id, wrong_back.read_bytes(), side="back")
    an = client.post(f"/api/verification/{session_id}/analyze", headers=_headers(token))

    body = an.json()
    assert body["sides"]["status"] == "FAIL"
    assert body["preliminary_pass"] is False

    res = client.get(f"/api/verification/{session_id}/result", headers=_headers(token))
    assert res.json()["overall_status"] == "REJECTED"
