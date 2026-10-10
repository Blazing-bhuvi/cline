"""Download optional face models used for higher-accuracy detection/matching.

The prototype works out of the box for OCR, QR, and database checks. Face
*comparison* requires an ONNX embedding model. This script downloads the OpenCV
Zoo SFace model (128-d embeddings, cosine similarity) which is the documented
default. Face detection already works offline via the bundled Haar cascade.

Run:
    python scripts/download_models.py

Files are placed in <project>/data/models.
"""
from __future__ import annotations

import sys
from pathlib import Path
from urllib.request import Request, urlopen

# Allow running this script directly from backend/scripts or elsewhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402

MODELS = {
    "face_recognition_sface_2021dec.onnx": (
        "https://github.com/opencv/opencv_zoo/raw/main/models/"
        "face_recognition_sface/face_recognition_sface_2021dec.onnx"
    ),
    "face_detection_yunet_2023mar.onnx": (
        "https://github.com/opencv/opencv_zoo/raw/main/models/"
        "face_detection_yunet/face_detection_yunet_2023mar.onnx"
    ),
}


def download(url: str, dest: Path) -> None:
    print(f"Downloading {dest.name} ...")
    req = Request(url, headers={"User-Agent": "voter-id-verifier/0.1"})
    with urlopen(req, timeout=120) as resp:
        data = resp.read()
    dest.write_bytes(data)
    print(f"Saved {dest} ({len(data) // (1024 * 1024)} MB)")


def main() -> int:
    settings = get_settings()
    model_dir = Path(settings.model_dir)
    model_dir.mkdir(parents=True, exist_ok=True)
    for filename, url in MODELS.items():
        dest = model_dir / filename
        if dest.exists():
            print(f"Already present: {dest}")
            continue
        try:
            download(url, dest)
        except Exception as exc:  # noqa: BLE001
            print(f"Failed to download {filename}: {exc}")
            print("You can download it manually and place it in:", model_dir)
            return 1
    print("Done. Face model(s) available in:", model_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
