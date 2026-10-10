# Indian Voter ID Authentication & Face Verification — Local Prototype

A **locally runnable prototype** that verifies an Indian Voter ID (EPIC) document
image and compares a live camera capture with the portrait on the card.

> **Important:** This is a **demonstration prototype** for authorized testing. It
> is **not** an official Election Commission of India (ECI) verification service.
> It performs **no** authoritative issuer validation, uses a **synthetic** local
> database, and its authenticity checks are **heuristic**.

---

## 1. Architecture

```
React (Vite + TS + Tailwind)  →  FastAPI (Python 3.13)
   Image upload / camera       →  Preprocessing → OCR (RapidOCR/onnxruntime)
                                  → Card/tamper checks → QR (OpenCV)
                                  → SQLite cross-verification (SQLAlchemy)
                                  → Decision engine (PASS/REJECTED/INCONCLUSIVE)
                                  → Face detection (OpenCV Haar) + embedding (ONNX/SFace)
```

The **backend is the authoritative source** for every verification decision. The
frontend never submits a PASS result or verification flags.

```
backend/
  app/
    main.py                 FastAPI app + CORS + error handling
    api/                    REST routes
    core/config.py          pydantic-settings configuration
    database/               SQLAlchemy engine + init
    models/orm.py           synthetic voter record table
    schemas/                Pydantic request/response schemas
    services/               preprocessing, OCR, QR, DB, face, decision, sessions
    utils/                  text normalization, image decode/quality
  scripts/                  seed data, download models, generate specimen card
  tests/                    unit + integration tests
frontend/                   React app (6 screens)
```

---

## 2. Prerequisites

- **Python 3.11–3.13** (tested on 3.13). Create a virtualenv.
- **Node.js 18+** (tested on Node 24) and `npm`.
- Windows, macOS, or Linux.

> If `npm` is blocked by PowerShell execution policy, use `npm.cmd` or run
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

## 3. Backend setup

```powershell
# from the project root
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

Optional face embedding model (needed for real face *matching*; detection works
offline via the bundled Haar cascade):

```powershell
cd backend
..\.venv\Scripts\python.exe scripts\download_models.py
```

This downloads the OpenCV Zoo **SFace** model (128-d embeddings, cosine
similarity) into `data/models/`. If the model is absent, face comparison returns
`INCONCLUSIVE` with a clear reason rather than fabricating a result.

Initialize the **synthetic** database:

```powershell
cd backend
..\.venv\Scripts\python.exe scripts\seed_demo_data.py
```

Run the API:

```powershell
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Health check: <http://127.0.0.1:8000/api/health>

---

## 4. Frontend setup

```powershell
cd frontend
npm.cmd install
## 6. Demonstration procedure

### Successful (PASS) flow
1. Seed the database and generate a specimen card (front + back):
   ```powershell
   cd backend
   ..\.venv\Scripts\python.exe scripts\seed_demo_data.py
   ..\.venv\Scripts\python.exe scripts\generate_sample_card.py --out ..\sample_data\specimen_card.png
   ..\.venv\Scripts\python.exe scripts\generate_sample_card.py --back --out ..\sample_data\specimen_card_back.png
   ```
2. Start the backend and frontend (see above).
3. Click **Start Verification**, upload `sample_data/specimen_card.png` (front) and
   `sample_data/specimen_card_back.png` (back).
4. The analysis screen shows OCR fields, QR status, a database **PASS**, and
   **Front/back correspondence: PASS**.
5. Continue to **Camera Verification**, capture a clear, centered face, and use it.
6. The final report shows **PASS** (face comparison requires the downloaded SFace
   model; without it the report shows **INCONCLUSIVE** for the face dimension).

### Rejected flow
- Generate a card whose EPIC is not in the database:
  ```powershell
  ..\.venv\Scripts\python.exe scripts\generate_sample_card.py --epic ZZZ9999999 --out ..\sample_data\mismatch_card.png
  ```
  Upload it — the database cross-verification returns **FAIL** and the report shows
  **REJECTED** (identifier not found in the demonstration dataset).
- Or upload `specimen_card.png` as the front and `mismatch_card.png` as the back —
  the **Front/back correspondence** check returns **FAIL** (identifiers differ) and
  the report shows **REJECTED**.

### Inconclusive flow
- Upload a blurry/partial card → OCR unreadable → **INCONCLUSIVE**.
- Deny camera permission or capture a poor-quality face → actionable retry
  instructions → **INCONCLUSIVE** until a good capture is provided.

---

## 7. Decision policy

| Outcome | Meaning |
|---------|---------|
| **PASS** | All mandatory demo checks passed: readable card, consistent database record, no mandatory integrity failure, and a face match. |
| **REJECTED** | A definitive failure: confirmed database mismatch, QR identifier conflict, or a face mismatch after adequate-quality captures. |
| **INCONCLUSIVE / MANUAL REVIEW** | Evidence insufficient: unreadable OCR, unverifiable security features, untrusted/unavailable DB, or face similarity in the uncertain range. |

A blurry image, low OCR confidence, an unavailable camera, or an unreachable
database does **not** by itself reject a person.

---

## 8. Limitations (read carefully)

- **Not an ECI service.** No issuer signature, official endpoint, or public
  verification response is used or fabricated.
- **Synthetic database.** Cross-verification uses a locally seeded fictional
  dataset, not an electoral roll. A missing record does not prove a card is fake.
- **Heuristic authenticity.** OCR/template/manipulation checks cannot prove a card
  is genuine; a matching face does not prove the document is genuine.
- **QR is not proof.** QR codes can be copied, altered, or generated.
- **No liveness.** This prototype does not establish that the camera image is a
  physically present live person; a photograph shown to the camera may be accepted.
- **Face matching is imperfect.** False matches and false rejections are possible.
  Default similarity thresholds (match >= 0.45, review >= 0.30) are starting
  points that should be calibrated on appropriate data.
- **Thresholds are documented, not universal.** Raw similarity is not a
  probability of identity.

---

## 9. Privacy & security notes

- Images are processed locally and deleted when a session ends or is cleared.
- No raw identity-document images, full OCR payloads, or biometric embeddings are
  logged.
- Sessions use short-lived random tokens and expire after a configurable TTL.
- Uploads enforce size/type/dimension limits and server-side filenames.
- CORS is restricted to the frontend origin.

This prototype is **not** a certification of compliance with all applicable Indian
data-protection, election, or biometric-processing requirements.

npm.cmd run dev
```

Open <http://localhost:5173>. Vite proxies `/api` to the backend on port 8000.

---

## 5. Running the tests

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest -q
```

- Unit tests use mocks / deterministic inputs (fast).
- `@pytest.mark.integration` tests run the **real** OCR / QR pipeline against a
  generated specimen card.
