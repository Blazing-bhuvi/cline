"""Face quality and face matching tests (unit, deterministic)."""
from __future__ import annotations

import numpy as np

from app.schemas.schemas import CheckStatus, FaceMatchResult, MatchResult
from app.services.face_matcher import cosine_similarity, match_faces
from app.services.face_quality import assess_face_quality


class StubDetector:
    def __init__(self, boxes):
        self.boxes = boxes

    def detect(self, img, min_size=40):
        return [{"box": b, "confidence": 1.0} for b in self.boxes]


def _img(w=400, h=400):
    return np.zeros((h, w, 3), dtype=np.uint8)


def test_quality_no_face():
    r = assess_face_quality(_img(), StubDetector([]))
    assert r.status == CheckStatus.FAIL
    assert r.face_count == 0


def test_quality_multiple_faces():
    r = assess_face_quality(_img(), StubDetector([(0, 0, 100, 100), (200, 200, 100, 100)]))
    assert r.status == CheckStatus.FAIL
    assert r.face_count == 2


def test_quality_good_face(monkeypatch):
    monkeypatch.setattr(
        "app.services.face_quality._face_region_metrics",
        lambda img, box: {"sharpness": 200.0, "brightness": 128.0},
    )
    monkeypatch.setattr("app.services.face_quality._eyes_detected", lambda gray: True)
    r = assess_face_quality(_img(), StubDetector([(100, 100, 200, 200)]))
    assert r.status == CheckStatus.PASS
    assert r.instructions == []


def test_quality_blurry_face(monkeypatch):
    monkeypatch.setattr(
        "app.services.face_quality._face_region_metrics",
        lambda img, box: {"sharpness": 5.0, "brightness": 128.0},
    )
    monkeypatch.setattr("app.services.face_quality._eyes_detected", lambda gray: True)
    r = assess_face_quality(_img(), StubDetector([(100, 100, 200, 200)]))
    assert r.status == CheckStatus.INCONCLUSIVE
    assert any("still" in i.lower() for i in r.instructions)


class FakeMatcher:
    def __init__(self, vec_a, vec_b, available=True):
        self.vecs = [vec_a, vec_b]
        self.available = available
        self._i = 0

    def is_available(self):
        return self.available

    @property
    def unavailable_reason(self):
        return "unavailable" if not self.available else ""

    def embed(self, img):
        v = self.vecs[self._i % 2]
        self._i += 1
        return np.asarray(v, dtype=np.float32)


def _face():
    return np.zeros((112, 112, 3), dtype=np.uint8)


def test_cosine_similarity():
    assert cosine_similarity(np.array([1.0, 0, 0]), np.array([1.0, 0, 0])) > 0.99
    assert cosine_similarity(np.array([1.0, 0, 0]), np.array([0.0, 1, 0])) < 0.01


def test_match_faces_match():
    m = FakeMatcher([1.0, 0, 0], [1.0, 0, 0])
    r = match_faces(m, _face(), _face())
    assert r.match_result == MatchResult.MATCH
    assert r.status == CheckStatus.PASS


def test_match_faces_mismatch():
    m = FakeMatcher([1.0, 0, 0], [0.0, 1, 0])
    r = match_faces(m, _face(), _face())
    assert r.match_result == MatchResult.MISMATCH
    assert r.status == CheckStatus.FAIL


def test_match_faces_uncertain_range():
    # similarity ~0.4 falls in [0.30, 0.45) -> INCONCLUSIVE
    m = FakeMatcher([1.0, 0], [0.4, 0.9165])
    r = match_faces(m, _face(), _face())
    assert r.match_result == MatchResult.INCONCLUSIVE
    assert r.status == CheckStatus.INCONCLUSIVE


def test_match_faces_unavailable_model():
    m = FakeMatcher([1.0, 0], [1.0, 0], available=False)
    r = match_faces(m, _face(), _face())
    assert r.status == CheckStatus.INCONCLUSIVE
    assert r.match_result is None


def test_match_faces_missing_face():
    m = FakeMatcher([1.0, 0], [1.0, 0])
    r = match_faces(m, None, _face())
    assert r.status == CheckStatus.INCONCLUSIVE
    assert r.id_face_available is False
