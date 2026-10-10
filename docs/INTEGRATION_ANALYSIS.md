# Integration Analysis — MyVote Discrepancy Detection → Upstream `cline`

> Branch: `feature/myvote-integration` (created from `main` @ `1fb0c6a`)
> Author: AI coding partner · Status: **Phase 1 (analysis)**

This document analyses the upstream repository and proposes a strategy for
integrating the local **Electoral Roll Discrepancy Detection & BLO Verification
System** (referred to below as **MyVote-D**) without disturbing upstream.

---

## 1. Upstream architecture summary

**Project:** *Indian Voter ID Authentication & Face Verification — Local
Prototype* (a demonstration prototype, explicitly **not** an ECI service).

**Shape:** monorepo with a Python backend and a TypeScript frontend.

```
cline/
├── backend/                     # FastAPI (Python)
│   ├── app/
│   │   ├── main.py              # create_app(), CORS, global 500 handler, lifespan
│   │   ├── api/routes.py        # APIRouter(prefix="/api") — verification workflow
│   │   ├── api/deps.py          # resolve_session() token dependency
│   │   ├── core/config.py       # pydantic-settings BaseSettings + get_settings()
│   │   ├── database/{session,init_db}.py   # SQLAlchemy engine + Base + get_db()
│   │   ├── models/orm.py        # VoterRecord (synthetic demo table)
│   │   ├── schemas/schemas.py   # Pydantic v2 request/response + enums
│   │   ├── services/            # ocr, qr, face_*, card_assessment, decision_engine,
│   │   │                        #   verification_service, session_manager, voter_database
│   │   └── utils/               # image_utils, text_utils
│   ├── scripts/                 # seed_demo_data, generate_sample_card, download_models
│   └── tests/                   # pytest (unit + integration markers)
├── frontend/                    # React 18 + Vite + TS + Tailwind (6 screens)
├── sample_data/                 # generated specimen cards (PNG)
├── .env.example, .gitignore, README.md
```

**Language / framework:** Python 3.11–3.13 (README tested on 3.13), **FastAPI**,
**SQLAlchemy 2.0** (`DeclarativeBase`, `Mapped`/`mapped_column`), **Pydantic v2**
+ **pydantic-settings**, **SQLite**. Frontend: React + Vite + Tailwind.

**Dependency/build system:**
- Backend: `backend/requirements.txt` (pip), `backend/pytest.ini` (pytest markers
  `unit` / `integration`, `testpaths = tests`).
- Frontend: `frontend/package.json` (npm), Vite dev server on `:5173` proxying
  `/api` → backend `:8000`.
- No CI: there is **no** `.github/`, no workflow YAML, no Makefile, no linter
  config committed. Tests are run manually per the README.

**Entry points:**
- Backend app: `backend/app/main.py` → `app = create_app()`; health at
  `GET /api/health`. Run via
  `uvicorn app.main:app --host 127.0.0.1 --port 8000`.
- Frontend: `frontend/` (`npm run dev`).

**Conventions observed:**
- `from __future__ import annotations` at top of every module; heavy typing.
- Config via **pydantic-settings** singleton `get_settings()` (`@lru_cache`),
  env-driven, `.env` support. Project root computed via `Path(__file__).parents[...]`.
- DB via module-level engine/session singletons + `get_db()` FastAPI dependency;
  `init_db()`/`drop_db()` helpers import models for side-effect registration.
- ORM: single `Base` in `app/database/session.py`; UTC via a local `_utcnow()`
  returning **timezone-aware** `datetime.now(timezone.utc)`.
- Services are **plain functions** (not classes) taking explicit args; a
  `decision_engine` centralises the PASS/REJECTED/INCONCLUSIVE policy + `DISCLOSURES`.
- Sessions: in-memory `SessionManager` with TTL, random tokens, `threading.Lock`.
- Tests: `conftest.py` sets `DATABASE_URL`/`UPLOAD_DIR`/`MODEL_DIR` to a temp dir
  **before** importing app modules; fixtures `db_session`, `seeded_db`,
  `sample_card_path`, `client` (`fastapi.testclient.TestClient`).
- Security posture: never leak stack traces (global 500 handler), CORS restricted,
  synthetic data only, upload size/type limits.

---

## 2. Where MyVote-D could plug in

MyVote-D (**Electoral Roll Discrepancy Detection & BLO Verification System**)
is an **adjacent, complementary domain**: upstream verifies that *a presented
card matches a person*; MyVote-D detects *anomalies on the roll itself*
(duplicates, underage, Form-7 abuse) and routes them to a **Booth Level Officer
(BLO)** for physical verification. They share: FastAPI + SQLAlchemy + SQLite,
Pydantic v2, synthetic-only data ethos, and a strong privacy/audit stance.

Natural integration points:
- **Separate route namespace** — expose MyVote-D under `/myvote/api/*` so it never
  collides with upstream `/api/*`.
- **Shared DB, separate tables** — MyVote-D's tables (`electors`,
  `form_submissions`, `discrepancy_flags`, `blo_review_submissions`,
  `audit_log`) do not clash with upstream's `voter_records`. A **separate SQLite
  file** (`myvote/data/electoral.db`) keeps blast radius minimal and avoids
  migration coupling.
- **Optional cross-link (future, out of scope now):** upstream's `voter_database`
  cross-verification could later consult MyVote-D flags to warn "this EPIC has an
  open discrepancy". Not required for this integration.

---

## 3. Conflicts to expect

| Area | Upstream | MyVote-D (local) | Resolution |
|------|----------|------------------|------------|
| **Package name `app`** | `backend/app/...` | local `app/...` | Keep MyVote-D under a distinct top-level **`myvote/`** package to avoid import collisions. |
| **Config mechanism** | pydantic-settings + `.env` | PyYAML `config.yaml` | Keep MyVote-D's YAML loader **isolated** inside `myvote/`. Do **not** force it onto upstream. |
| **Extra deps** | fastapi/sqlalchemy/pydantic/opencv/rapidocr/onnxruntime | adds **pyotp, PyYAML, reportlab, Jinja2** | Ship `myvote/requirements.txt`; **never** upgrade/downgrade upstream's pins. |
| **`fastapi` pin** | `fastapi>=0.115` | local pinned `fastapi==0.111.0` | MyVote-D does not need an exact pin; treat upstream's `>=0.115` as authoritative for a combined install. |
| **Ports** | backend `:8000`, frontend `:5173` | MyVote-D defaults to `:8000` | Mount MyVote-D as routes **inside** the backend process (same `:8000`, `/myvote` prefix) OR run standalone on a different port. Default: **mount in-process**. |
| **SQLite file** | `data/voter.db` | `data/electoral.db` | Different filenames → no clash. |
| **UTC timestamps** | timezone-aware `datetime.now(timezone.utc)` | MyVote-D uses naive UTC (`utcnow()`) | Cosmetic; keep MyVote-D's own convention internally. Note in report. |
| **Python version** | 3.11–3.13 | 3.11 (spec) | Compatible. Local dev box is 3.14 (SQLAlchemy 2.0.30 incompatible) — an environment caveat only. |
| **License** | none declared in repo | n/a | No license file found upstream; do not add restrictive headers. Flag as "verify with maintainer". |

**No folder-name, port, or config conflicts are *blocking*** because MyVote-D is
self-contained. The only real coupling is the process/port, solved by mounting.

---

## 4. Proposed integration strategy

**Chosen strategy: (a) self-contained subdirectory + thin adapter.**

1. Place all MyVote-D code under a new top-level **`myvote/`** package with its
   **own** `requirements.txt`, `pytest.ini`, tests, and its own SQLite data dir
   (`myvote/data/`). It keeps its YAML config and its own helpers — fully
   isolated from `backend/app`.
2. Provide a **thin adapter** `myvote/adapter.py` that builds a FastAPI
   `APIRouter` (prefix `/myvote/api`) and an optional `mount(app)` helper. Upstream
   is **not** required to import it; a single **optional, guarded** line could
   mount it. **Preferred: leave upstream files untouched** and document the exact
   one-liner in the report so the maintainer can opt in.
3. Preserve **all** MyVote-D features: DSD/PSD detection engine, BLO routing
   workflow (FLAGGED→ASSIGNED→BLO_REVIEW→CONFIRMED/REJECTED), BLO TOTP auth with
   15-min absolute / 5-min idle sessions, the SHA-256 hash-chained `AuditChain`,
   DPDP PII masking, and FIR-evidence flagging on a clearly-rejected genuine flag.
4. **No upstream dependency is upgraded or downgraded.** Isolated requirements are
   used for MyVote-D.
5. Both test suites run independently and must pass:
   - upstream: `cd backend && pytest`
   - MyVote-D: `cd myvote && pytest`

This maximises safety (upstream untouched), keeps the two codebases independently
runnable/testable, and leaves a clean seam for a future, tighter merge.

---

## 5. Integration checklist

- [ ] Create `myvote/` package (models, detection, workflow, audit, security,
      eronet adapter, api router, templates/static for the dashboard).
- [ ] `myvote/requirements.txt`, `myvote/pytest.ini`, `myvote/README.md`.
- [ ] Adapter exposing `/myvote/api/*` + optional guarded mount helper.
- [ ] Extend `.gitignore` for `myvote/data/` and any generated dossiers.
- [ ] Run **both** suites; record results in `docs/INTEGRATION_REPORT.md`.
- [ ] Phase 3: review/harden the BLO verification workflow end-to-end + tests.

