# Sample data

This directory is intended to hold **synthetic / clearly fictional** specimen
images for testing the OCR, QR, and database cross-verification pipeline.

## Generate a specimen card

Run (from the `backend/` directory, with the virtualenv active):

```powershell
..\.venv\Scripts\python.exe scripts\generate_sample_card.py --out ..\sample_data\specimen_card.png
..\.venv\Scripts\python.exe scripts\generate_sample_card.py --back --out ..\sample_data\specimen_card_back.png
```

The first produces a clearly-labelled **front** "SPECIMEN - NOT A REAL DOCUMENT"
card whose EPIC number (`XYZ0000001`) and name (`Aarav Sharma`) match a seeded
demonstration record. The second produces a **back** with the same EPIC number,
address, and no portrait/name field.

To generate a card whose identifier is *not* in the demonstration database (to
exercise the rejection path), use a different EPIC number:

```powershell
..\.venv\Scripts\python.exe scripts\generate_sample_card.py --epic ZZZ9999999 --out ..\sample_data\mismatch_card.png
```

## Front/back correspondence checks

When both a front and a back image are uploaded, the backend also OCRs the back
(concurrently with the front) and reports:

- **PASS** — front and back identifiers match.
- **FAIL** — front and back identifiers differ (different cards).
- **INCONCLUSIVE** — the back looks like a front image (wrong side) or the
  identifier could not be read.

## Important

- These images are entirely synthetic and contain no real identity information.
- Do NOT place real identity documents or real voter data in this directory.
