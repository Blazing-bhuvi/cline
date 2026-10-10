"""Face embedding and comparison using an ONNX model (onnxruntime).

The prototype targets the OpenCV Zoo SFace model (112x112 RGB, 128-d
embeddings) but accepts any ArcFace/SFace-style ONNX model placed in the
configured model directory. When no model is present, comparison reports
INCONCLUSIVE rather than fabricating a result.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from app.core.config import get_settings
from app.schemas.schemas import CheckStatus, FaceMatchResult, MatchResult


class FaceMatcher:
    def __init__(self, model_path: str | None = None, input_size: tuple[int, int] = (112, 112)):
        self.model_path = model_path
        self.input_size = input_size
        self._session = None
        self._load_error: str | None = None
        if model_path and Path(model_path).exists():
            self._load()

    def _load(self) -> None:
        try:
            import onnxruntime as ort  # type: ignore

            self._session = ort.InferenceSession(
                str(self.model_path), providers=["CPUExecutionProvider"]
            )
            self._load_error = None
        except Exception as exc:  # pragma: no cover
            self._session = None
            self._load_error = str(exc)

    def is_available(self) -> bool:
        return self._session is not None

    @property
    def unavailable_reason(self) -> str:
        if self._session is not None:
            return ""
        if not self.model_path:
            return "no face embedding model configured"
        if not Path(self.model_path).exists():
            return "face embedding model file not found"
        return f"face embedding model failed to load: {self._load_error}"

    def _preprocess(self, face_bgr: np.ndarray) -> np.ndarray:
        resized = cv2.resize(face_bgr, self.input_size, interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        # SFace-style normalization: scale to [0, 1], NCHW, float32.
        blob = rgb.astype(np.float32) / 255.0
        blob = np.transpose(blob, (2, 0, 1))
        return np.expand_dims(blob, axis=0)

    def embed(self, face_bgr: np.ndarray) -> np.ndarray | None:
        if not self.is_available():
            return None
        try:
            inp = self._preprocess(face_bgr)
            input_name = self._session.get_inputs()[0].name
            outputs = self._session.run(None, {input_name: inp})
            vec = np.asarray(outputs[0]).flatten().astype(np.float32)
            norm = float(np.linalg.norm(vec))
            if norm == 0:
                return None
            return vec / norm
        except Exception:
            return None


_matcher: FaceMatcher | None = None


def get_face_matcher() -> FaceMatcher:
    """Return a process-wide FaceMatcher, loading the configured model if present."""
    global _matcher
    if _matcher is None:
        settings = get_settings()
        candidate = Path(settings.model_dir) / settings.face_embedding_model
        model_path = str(candidate) if candidate.exists() else None
        _matcher = FaceMatcher(model_path)
    return _matcher


def reset_face_matcher() -> None:
    global _matcher
    _matcher = None


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    na = a / (np.linalg.norm(a) + 1e-8)
    nb = b / (np.linalg.norm(b) + 1e-8)
    return float(np.dot(na, nb))


def match_faces(
    matcher: FaceMatcher,
    id_face_bgr: np.ndarray | None,
    live_face_bgr: np.ndarray | None,
) -> FaceMatchResult:
    settings = get_settings()
    thr_match = settings.face_similarity_match
    thr_review = settings.face_similarity_review

    if id_face_bgr is None or live_face_bgr is None:
        return FaceMatchResult(
            status=CheckStatus.INCONCLUSIVE,
            id_face_available=id_face_bgr is not None,
            live_face_available=live_face_bgr is not None,
            threshold_match=thr_match,
            threshold_review=thr_review,
            reason="one or both face images unavailable",
        )

    if not matcher.is_available():
        return FaceMatchResult(
            status=CheckStatus.INCONCLUSIVE,
            id_face_available=True,
            live_face_available=True,
            threshold_match=thr_match,
            threshold_review=thr_review,
            reason=f"face comparison unavailable: {matcher.unavailable_reason}",
        )

    emb_id = matcher.embed(id_face_bgr)
    emb_live = matcher.embed(live_face_bgr)
    if emb_id is None or emb_live is None:
        return FaceMatchResult(
            status=CheckStatus.INCONCLUSIVE,
            id_face_available=True,
            live_face_available=True,
            threshold_match=thr_match,
            threshold_review=thr_review,
            reason="could not compute face embeddings from one or both images",
        )

    sim = cosine_similarity(emb_id, emb_live)
    if sim >= thr_match:
        result = MatchResult.MATCH
        status = CheckStatus.PASS
        reason = f"faces match (similarity {sim:.3f} >= {thr_match})"
    elif sim < thr_review:
        result = MatchResult.MISMATCH
        status = CheckStatus.FAIL
        reason = f"faces do not match (similarity {sim:.3f} < {thr_review})"
    else:
        result = MatchResult.INCONCLUSIVE
        status = CheckStatus.INCONCLUSIVE
        reason = (
            f"face similarity {sim:.3f} in uncertain range "
            f"[{thr_review}, {thr_match}); manual review required"
        )

    return FaceMatchResult(
        status=status,
        match_result=result,
        similarity=round(sim, 4),
        threshold_match=thr_match,
        threshold_review=thr_review,
        id_face_available=True,
        live_face_available=True,
        reason=reason,
    )
