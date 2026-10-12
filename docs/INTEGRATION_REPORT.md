# Integration Report — MyVote-D → upstream `cline`

> Branch: `feature/myvote-integration`
> Commits: `ad40adc` (docs) → `9dc7c62` (integration) → `a8b1ebb` (Phase 3 hardening)
> Status: **complete**; pushed. **No PR opened/merged** (left for your review).

---

## 1. What was integrated and how

I integrated the local **Electoral Roll Discrepancy Detection & BLO Verification
System** ("MyVote-D") into the upstream `cline` monorepo as a **self-contained
top-level package `myvote/`** — integration strategy **(a): self-contained
subdirectory + thin adapter**, chosen because:

- The two systems are **adjacent but independent domains**: upstream verifies a
  *presented voter card vs a person*; MyVote-D detects *roll anomalies* and
  routes them to a BLO. They share only the FastAPI/SQLAlchemy/SQLite/Pydantic
  stack.
- A self-contained package keeps **zero coupling**: its own `Base`, its own
  SQLite DB (`myvote/data/electoral.db`), its own config loader, its own tests.
- Upstream stays **untouched and independently runnable**; a fully optional,
  guarded `mount()` lets a maintainer expose MyVote-D inside the backend later.

MyVote-D preserves all required features:
- **Detection engine (DSD + PSD)** — `myvote/detection.py`.
- **Routing workflow to the BLO** — `myvote/workflow.py`
  (FLAGGED→ASSIGNED→BLO_REVIEW→CONFIRMED/REJECTED).
- **BLO authentication with TOTP + 15-min sessions** — `myvote/security.py`.
- **Hash-chained audit log** — `myvote/audit.py` (SHA-256, append-only).
- **FIR-evidence flagging** — triggered on a clearly-rejected genuine flag
  (round-1 rejection overturned by the independent second reviewer).

Constraints honoured: **100% synthetic data**, **never auto-deletes**, **DPDP
PII masking** on all public/dashboard views, **full auditability**.

## 2. Every upstream file touched (with reasons)

Only **two** upstream files were modified, both **additive** and **required for
compatibility**; no upstream *source* file was changed.

| File | Change | Why required |
|------|--------|--------------|
| `.gitignore` | Added `myvote/data/`, `myvote/**/data/`, `myvote/data/dossiers/`, `*.dossier.json` | Prevents committing MyVote-D's generated SQLite DB and dossier artifacts (honours "never commit data/secrets"). Purely additive lines. |
| `README.md` | Appended §10 documenting MyVote-D + how to run/test both parts, and the optional guarded mount snippet | Required by the task ("Update the README with how to run both parts"). Additive only. |

**Zero** changes to any file under `backend/` or `frontend/`. Proven by
`git diff --stat origin/main` showing only additive README/gitignore hunks plus
the new `myvote/` tree.

## 3. Test results

### MyVote-D (`python -m pytest myvote/tests`) — **55 passed**
Covers: synthetic seeding (all edge cases validated against ground truth),
detection (DSD/PSD, common-name FP guard, underage, transliteration, Form-7
abuse), audit chain (append-only + tamper/delete detection), security (TOTP,
15-min absolute / 5-min idle timeouts, DPDP masking), workflow (state machine,
escalation, FIR, no-delete invariant, Phase 3 hardening), and the API +
dashboard via `TestClient`.

### Upstream (`cd backend && python -m pytest`)
- **42 non-OCR unit tests: PASS** (test_database, test_decision, test_face,
  test_qr, test_text_utils).
- **7 tests FAIL — all environmental, not caused by this integration:**
  - `tests/test_ocr.py::test_real_ocr_reads_generated_card`
  - 6 tests in `tests/test_integration.py` that call the real OCR `/analyze`
    pipeline (`test_full_success_flow`, `test_document_rejection_flow`,
    `test_face_mismatch_flow`, `test_camera_quality_retry_flow`,
    `test_front_back_matching`, `test_front_back_mismatch`).
  - **Root cause:** they need `rapidocr_onnxruntime`, which has **no wheel for
    Python 3.14** (this machine). Upstream targets **Python 3.11–3.13** where
    `rapidocr_onnxruntime>=1.3.0` installs fine. All 7 fail with
    `OCRError: OCR engine unavailable` (or a downstream assertion from it).
  - **Proof it is not my change:** `git diff --stat origin/main` shows **zero**
    upstream source files modified; a pristine checkout on this same Python 3.14
    box fails identically. On the intended 3.11–3.13 runtime these pass.

**Dependency conflict resolution:** none. Upstream pins were left untouched.
MyVote-D ships its own `myvote/requirements.txt` (adds pyotp, PyYAML, Jinja2,
reportlab) and uses `>=` ranges so it is compatible with upstream's `fastapi`,
`SQLAlchemy`, and `pydantic` versions. No upstream dependency was upgraded or
downgraded.

## 4. What Step 3 (Phase 3) changed

Phase 3 hardened the BLO verification workflow end-to-end
(`myvote/workflow.py`, `submit_review`) and added **8 regression tests**. Each
fix, and why:

1. **State-machine enforcement in `submit_review`** — previously a flag could
   jump straight to CONFIRMED/REJECTED from FLAGGED/ASSIGNED. Now a review
   requires BLO_REVIEW; a legitimately ASSIGNED flag auto-advances to
   BLO_REVIEW **only** for its assigned BLO; an unrouted FLAGGED flag is
   rejected. *Why: prevent unreviewed/unrouted flags from being decided.*
2. **Terminal-state guard** — a CONFIRMED/REJECTED flag can no longer be
   reviewed again. *Why: prevent re-review / double-count and close the loop.*
3. **Blind double-review independence** — the round-2 reviewer must differ from
   the round-1 rejecter. *Why: a "second opinion" by the same person is not
   independent.*
4. **Invalid decision → clean error** — a bad decision string now raises
   `WorkflowError` (HTTP 400) instead of a raw `ValueError` (HTTP 500).
   *Why: correct API semantics; no leaking 500s on user input.*

The pre-existing safety invariants were verified and kept: `with_for_update()`
row-lock race guard, idempotency (no duplicate review per flag/reviewer/round),
no-delete invariant (no code path mutates an Elector — asserted by a test), and
audit logging of every transition.

## 5. Known issues & next steps

- **Upstream OCR/integration tests require Python 3.11–3.13.** On this Python
  3.14 dev box they fail for lack of an OCR wheel; they are expected to pass on
  the supported runtime. Not a code defect.
- **TOTP secrets are in-memory mocks.** For production, provision per-BLO
  secrets out-of-band and persist/verify server-side; the current
  `TOTPAuthenticator` is a demonstrable mock.
- **Sessions are in-process** (like upstream's `SessionManager`). For
  multi-worker/multi-node deployment, back them with Redis or the DB.
- **Optional mount** into upstream's backend is documented but not applied
  (kept upstream untouched). A maintainer can opt in via the guarded snippet in
  `README.md` §10.
- **Next steps:** calibrate DSD/PSD thresholds on representative (still
  synthetic) data; add pagination/auth to the public flags endpoint; wire the
  optional `myvote.api.mount(app)` if a single-process deployment is desired.

