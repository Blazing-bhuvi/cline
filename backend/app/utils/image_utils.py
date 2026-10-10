"""Image decoding, validation, and basic quality metrics using OpenCV."""
from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

import cv2
import numpy as np


class ImageDecodeError(ValueError):
    """Raised when an image cannot be decoded or is invalid."""


def decode_image(data: bytes) -> np.ndarray:
    """Decode raw image bytes to a BGR ndarray. Raises ImageDecodeError on failure."""
    if not data:
        raise ImageDecodeError("Empty image data.")
    buf = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if img is None or img.size == 0:
        raise ImageDecodeError("Could not decode image (corrupted or unsupported format).")
    return img


def image_dimensions(img: np.ndarray) -> tuple[int, int]:
    h, w = img.shape[:2]
    return w, h


def validate_dimensions(img: np.ndarray, min_width: int = 200, min_height: int = 200) -> None:
    w, h = image_dimensions(img)
    if w < min_width or h < min_height:
        raise ImageDecodeError(
            f"Image too small: {w}x{h}. Minimum {min_width}x{min_height} required."
        )


def sharpness_score(img: np.ndarray) -> float:
    """Variance of Laplacian; higher means sharper."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def brightness_score(img: np.ndarray) -> float:
    """Mean pixel intensity in 0..255."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return float(np.mean(gray))


def contrast_score(img: np.ndarray) -> float:
    """Standard deviation of pixel intensities."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return float(np.std(gray))


def sharpness_to_quality(sharpness: float) -> float:
    """Map Laplacian variance to a 0..1 quality score (calibrated heuristic)."""
    # ~50 is decent for a sharp document photo; >200 is excellent.
    return float(np.clip(sharpness / 150.0, 0.0, 1.0))


def generate_filename(prefix: str, ext: str) -> str:
    """Generate a non-guessable server-side filename."""
    return f"{prefix}_{uuid.uuid4().hex}.{ext}"


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_image(img: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(path), img)
    if not ok:
        raise ImageDecodeError(f"Failed to write image to {path.name}.")
