"""Face detection using OpenCV (Haar cascade bundled, offline by default).

A more accurate DNN detector can be dropped in when a model file is available,
but Haar keeps the prototype fully functional without downloads.
"""
from __future__ import annotations

import cv2
import numpy as np


class FaceDetector:
    def __init__(self) -> None:
        self._cascade = None

    def _get_cascade(self):
        if self._cascade is None:
            path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            self._cascade = cv2.CascadeClassifier(path)
            if self._cascade.empty():
                raise RuntimeError("OpenCV Haar cascade failed to load.")
        return self._cascade

    def detect(self, img: np.ndarray, min_size: int = 40) -> list[dict]:
        """Detect faces and return a list of {'box': (x,y,w,h), 'confidence': float}."""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)
        cascade = self._get_cascade()
        faces = cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(min_size, min_size)
        )
        results: list[dict] = []
        for (x, y, w, h) in faces:
            results.append({"box": (int(x), int(y), int(w), int(h)), "confidence": 1.0})
        # Sort by area descending (largest face first)
        results.sort(key=lambda r: r["box"][2] * r["box"][3], reverse=True)
        return results

    def detect_largest(self, img: np.ndarray, min_size: int = 40) -> dict | None:
        faces = self.detect(img, min_size=min_size)
        return faces[0] if faces else None


_detector: FaceDetector | None = None


def get_face_detector() -> FaceDetector:
    global _detector
    if _detector is None:
        _detector = FaceDetector()
    return _detector
