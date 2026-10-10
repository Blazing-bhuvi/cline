"""Document image preprocessing.

Retains the original image untouched and returns a processed copy optimized
for OCR, along with metadata describing what was done.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np


@dataclass
class PreprocessMeta:
    original_size: tuple[int, int] = (0, 0)
    processed_size: tuple[int, int] = (0, 0)
    orientation_corrected: bool = False
    skew_angle: float = 0.0
    card_boundary_found: bool = False
    resized: bool = False
    notes: list[str] = field(default_factory=list)


def order_points(pts: np.ndarray) -> np.ndarray:
    """Order four points as [top-left, top-right, bottom-right, bottom-left]."""
    pts = pts.reshape(4, 2).astype(np.float32)
    rect = np.zeros((4, 2), dtype=np.float32)
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect


def _estimate_skew_angle(gray: np.ndarray) -> float:
    if gray.size < 100:
        return 0.0
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    coords = np.column_stack(np.where(thresh > 0))
    if coords.shape[0] < 50:
        return 0.0
    # Use all text pixels; angle is relative to the dominant text block orientation.
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = 90 + angle
    return float(angle)


def deskew(gray: np.ndarray, max_angle: float = 45.0) -> tuple[np.ndarray, bool, float]:
    angle = _estimate_skew_angle(gray)
    if abs(angle) < 0.5 or abs(angle) > max_angle:
        return gray, False, angle
    h, w = gray.shape[:2]
    center = (w // 2, h // 2)
    m = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(
        gray, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
    )
    return rotated, True, angle


def detect_card_quad(img: np.ndarray) -> np.ndarray | None:
    """Detect the largest quadrilateral (likely the card boundary)."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(gray, 50, 150)
    edges = cv2.dilate(edges, None, iterations=1)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    area_img = float(img.shape[0] * img.shape[1])
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:10]
    for c in contours:
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        if len(approx) == 4 and cv2.contourArea(c) > area_img * 0.3:
            return approx.reshape(4, 2)
    return None


def perspective_correct(img: np.ndarray, quad: np.ndarray) -> np.ndarray:
    """Warp a detected quadrilateral to a top-down view."""
    rect = order_points(quad)
    (tl, tr, br, bl) = rect
    width_a = np.linalg.norm(br - bl)
    width_b = np.linalg.norm(tr - tl)
    max_w = int(max(width_a, width_b))
    height_a = np.linalg.norm(tr - br)
    height_b = np.linalg.norm(tl - bl)
    max_h = int(max(height_a, height_b))
    dst = np.array(
        [[0, 0], [max_w - 1, 0], [max_w - 1, max_h - 1], [0, max_h - 1]],
        dtype=np.float32,
    )
    m = cv2.getPerspectiveTransform(rect, dst)
    return cv2.warpPerspective(img, m, (max_w, max_h))


def resize_max_dim(img: np.ndarray, max_dim: int = 1600) -> tuple[np.ndarray, bool]:
    h, w = img.shape[:2]
    scale = max_dim / float(max(h, w))
    if scale >= 1.0:
        return img, False
    new_w, new_h = int(w * scale), int(h * scale)
    return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA), True


def enhance_contrast(gray: np.ndarray) -> np.ndarray:
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(gray)


def preprocess_document(
    img: np.ndarray,
    target_max_dim: int = 1600,
    do_perspective: bool = True,
) -> tuple[np.ndarray, np.ndarray, PreprocessMeta]:
    """Preprocess a document image for OCR.

    Returns (processed_bgr, processed_gray, meta). The input `img` is never modified.
    """
    meta = PreprocessMeta(original_size=(img.shape[1], img.shape[0]))

    work = img.copy()
    work, resized = resize_max_dim(work, target_max_dim)
    meta.resized = resized

    if do_perspective:
        quad = detect_card_quad(work)
        if quad is not None:
            work = perspective_correct(work, quad)
            meta.card_boundary_found = True
            meta.notes.append("card boundary detected and perspective-corrected")
        else:
            meta.notes.append("card boundary not detected; kept original geometry")

    gray = cv2.cvtColor(work, cv2.COLOR_BGR2GRAY)
    gray = cv2.bilateralFilter(gray, d=5, sigmaColor=40, sigmaSpace=40)
    gray, corrected, angle = deskew(gray)
    meta.orientation_corrected = corrected
    meta.skew_angle = angle
    if corrected:
        meta.notes.append("image deskewed")

    gray = enhance_contrast(gray)
    processed_bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    meta.processed_size = (processed_bgr.shape[1], processed_bgr.shape[0])
    return processed_bgr, gray, meta
