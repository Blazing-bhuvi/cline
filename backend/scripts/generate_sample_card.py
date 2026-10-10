"""Generate a clearly fictional specimen voter-ID card image for testing.

Produces a synthetic, clearly-labelled "SPECIMEN" card so the OCR, QR, and
database modules can be exercised end-to-end without any real identity document.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

DEFAULT_RECORD = {
    "epic": "XYZ0000001",
    "name": "Aarav Sharma",
    "fathername": "Rohit Sharma",
    "dob": "12-04-1990",
    "gender": "male",
    "address": "12 MG Road, Bengaluru, Karnataka 560001",
}


def _font(size: int, bold: bool = False):
    candidates = [
        Path("C:/Windows/Fonts/arialbd.ttf") if bold else Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/segoeui.ttf"),
    ]
    for c in candidates:
        if c.exists():
            try:
                return ImageFont.truetype(str(c), size)
            except Exception:  # noqa: BLE001
                continue
    return ImageFont.load_default()


def _make_qr(payload: dict) -> Image.Image:
    try:
        import qrcode  # type: ignore
    except ImportError:
        print("qrcode package not installed; skipping QR on specimen card.", file=sys.stderr)
        return None
    qr = qrcode.QRCode(border=2, box_size=6)
    qr.add_data(json.dumps(payload))
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert("RGB")


def draw_face(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int]) -> None:
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    draw.ellipse([cx - w // 4, cy - h // 3, cx + w // 4, cy + h // 3], fill="#d9b38c", outline="#7a5c40")
    draw.ellipse([cx - w // 4, cy - h // 3, cx + w // 4, cy + h // 4], fill="#2b2b2b")  # hair
    draw.ellipse([cx - w // 8, cy - h // 10, cx - w // 20, cy - h // 20], fill="#1f1f1f")  # eye L
    draw.ellipse([cx + w // 20, cy - h // 10, cx + w // 8, cy - h // 20], fill="#1f1f1f")  # eye R


def generate_card(record: dict, out_path: Path, with_qr: bool = True) -> None:
    W, H = 1024, 646
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)

    # Header
    d.rectangle([0, 0, W, 90], fill="#1a5276")
    d.text((W // 2, 45), "ELECTION COMMISSION OF INDIA", font=_font(30, bold=True), fill="white", anchor="mm")
    d.text((W // 2, 120), "ELECTOR PHOTO IDENTITY CARD", font=_font(24, bold=True), fill="#1a5276", anchor="mm")

    # Portrait
    d.rectangle([40, 150, 260, 430], outline="#1a5276", width=3)
    draw_face(d, (50, 160, 250, 420))

    # Fields
    x = 290
    y = 160
    lines = [
        ("EPIC No", record["epic"]),
        ("Name", record["name"]),
        ("Father's Name", record["fathername"]),
        ("Date of Birth", record["dob"]),
        ("Sex", record["gender"]),
        ("Address", record["address"]),
    ]
    for label, value in lines:
        d.text((x, y), f"{label}:", font=_font(22, bold=True), fill="#1a5276")
        d.text((x + 220, y), value, font=_font(22), fill="black")
        y += 46

    # QR code
    if with_qr:
        qr = _make_qr(record)
        if qr is not None:
            qr = qr.resize((170, 170))
            img.paste(qr, (820, 430))

    # Watermark / specimen notice
    d.text((W // 2, H - 60), "SPECIMEN - NOT A REAL DOCUMENT", font=_font(22, bold=True), fill="#b03a2e", anchor="mm")
    d.text((W // 2, H - 28), "For authorized identity-verification testing only", font=_font(16), fill="#7f8c8d", anchor="mm")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    print(f"Wrote specimen card to {out_path}")


def generate_back_card(record: dict, out_path: Path) -> None:
    """Generate a synthetic back-of-card image (no portrait, no name field)."""
    W, H = 1024, 646
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)

    d.rectangle([0, 0, W, 90], fill="#1a5276")
    d.text((W // 2, 45), "ELECTION COMMISSION OF INDIA", font=_font(30, bold=True), fill="white", anchor="mm")
    d.text((W // 2, 120), "VOTER ID CARD - BACK", font=_font(24, bold=True), fill="#1a5276", anchor="mm")

    lines = [
        ("EPIC No", record["epic"]),
        ("Address", record["address"]),
        ("Assembly Constituency", "SPECIMEN-AC-001"),
        ("Polling Station", "SPECIMEN-PS-001"),
    ]
    y = 170
    for label, value in lines:
        d.text((60, y), f"{label}:", font=_font(22, bold=True), fill="#1a5276")
        d.text((360, y), value, font=_font(22), fill="black")
        y += 52

    d.text((60, y + 20), "This is a specimen card and is not valid for identification.", font=_font(18), fill="#7f8c8d")
    d.text((W // 2, H - 40), "SPECIMEN - NOT A REAL DOCUMENT", font=_font(22, bold=True), fill="#b03a2e", anchor="mm")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    print(f"Wrote specimen back card to {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a specimen voter-ID card.")
    parser.add_argument("--out", default="sample_data/specimen_card.png", help="Output path.")
    parser.add_argument("--epic", default=DEFAULT_RECORD["epic"], help="EPIC number to render.")
    parser.add_argument("--no-qr", action="store_true", help="Omit the QR code.")
    parser.add_argument("--back", action="store_true", help="Generate the back side instead of the front.")
    args = parser.parse_args()

    record = dict(DEFAULT_RECORD)
    record["epic"] = args.epic.upper()
    if args.back:
        generate_back_card(record, Path(args.out))
    else:
        generate_card(record, Path(args.out), with_qr=not args.no_qr)
