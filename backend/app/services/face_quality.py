"""Live-capture face quality assessment with actionable feedback."""
from __future__ import annotations

import cv2
import numpy as np

from app.core.config import get_settings
from app.schemas.schemas import CheckStatus, FaceQualityResult
from app.services.face_detector import FaceDetector, get_face_detector


def _face_region_metrics(img: np.ndarray, box: tuple[int, int, int, int]) -> dict:
    x, y, w, h = box
    face = img[y : y + h, x : x + w]
    if face.size == 0:
        return {"sharpness": 0.0, "brightness": 0.0}
    gray = cv2.cvtColor(face, cv2.COLOR_BGR2GRAY)
    sharp = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    bright = float(np.mean(gray))
    return {"sharpness": sharp, "brightness": bright}


def _eyes_detected(gray_face: np.ndarray) -> bool:
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_eye.xml")
    if cascade.empty():
        return True  # cannot check -> assume not obstructed
    eyes = cascade.detectMultiScale(gray_face, scaleFactor=1.1, minNeighbors=3, minSize=(10, 10))
    return len(eyes) >= 1


def assess_face_quality(
    img: np.ndarray, detector: FaceDetector | None = None
) -> FaceQualityResult:
    settings = get_settings()
    detector = detector or get_face_detector()
    faces = detector.detect(img)

    if not faces:
        return FaceQualityResult(
            status=CheckStatus.FAIL,
            face_detected=False,
            face_count=0,
            instructions=["No face detected. Position your face inside the guide."],
            reason="no face detected",
        )

    face_count = len(faces)
    if face_count > 1:
        return FaceQualityResult(
            status=CheckStatus.FAIL,
            face_detected=True,
            face_count=face_count,
            instructions=["Only one person should be visible."],
            reason=f"multiple faces detected ({face_count})",
        )

    box = faces[0]["box"]
    x, y, w, h = box
    ih, iw = img.shape[:2]
    img_area = float(iw * ih)
    face_area = float(w * h)
    size_ratio = face_area / img_area
    size_ok = size_ratio >= settings.face_min_size_ratio and w >= 60

    cx, cy = x + w / 2.0, y + h / 2.0
    centered = abs(cx - iw / 2.0) <= 0.25 * iw and abs(cy - ih / 2.0) <= 0.25 * ih

    metrics = _face_region_metrics(img, box)
    sharp = metrics["sharpness"]
    bright = metrics["brightness"]
    sharp_ok = sharp >= 40.0
    exposure_ok = 60.0 <= bright <= 220.0

    gray_face = cv2.cvtColor(img[y : y + h, x : x + w], cv2.COLOR_BGR2GRAY)
    eyes_ok = _eyes_detected(gray_face)
    obstructed = None if eyes_ok else True

    instructions: list[str] = []
    if not size_ok:
        instructions.append("Move closer to the camera.")
    if not centered:
        instructions.append("Center your face inside the guide.")
    if not sharp_ok:
        instructions.append("Hold still while taking the picture.")
    if not exposure_ok:
        instructions.append("Improve the lighting on your face.")
    if obstructed:
        instructions.append("Remove the obstruction from your face.")

    all_ok = size_ok and centered and sharp_ok and exposure_ok and not obstructed
    status = CheckStatus.PASS if all_ok else CheckStatus.INCONCLUSIVE
    reason = (
        "face quality acceptable"
        if all_ok
        else "face present but quality insufficient; see instructions"
    )

    score = 0.0
    score += 1.0 if size_ok else 0.0
    score += 1.0 if centered else 0.0
    score += 1.0 if sharp_ok else 0.0
    score += 1.0 if exposure_ok else 0.0
    score += 1.0 if not obstructed else 0.0
    score /= 5.0

    return FaceQualityResult(
        status=status,
        face_detected=True,
        face_count=face_count,
        size_ok=size_ok,
        centered=centered,
        sharp=sharp_ok,
        exposure_ok=exposure_ok,
        obstructed=obstructed,
        instructions=instructions,
        score=round(score, 2),
        reason=reason,
    )
