# MyVote-D — Electoral Roll Discrepancy Detection & BLO Verification

A **self-contained subsystem** of the `cline` monorepo. It flags electoral-roll
anomalies (duplicates, transliteration variants, underage voters, bulk/abusive
Form 7 deletions) and routes them to a **Booth Level Officer (BLO)** for
*physical* verification. It **never** deletes a voter record — it only flags,
routes, and generates ERO notices.

> ⚠️ **100% synthetic data.** Every elector, face vector, and Form submission is
> fabricated by `MockERONET`. No real voter data is used, scraped, or requested.

## Constraints (enforced)
| # | Constraint | Where |
|---|------------|-------|
| 1 | Synthetic data only | `eronet.py` (`SYN…` EPICs, seeded RNG) |
| 2 | No auto-deletion | no delete path exists; a test asserts it (`test_workflow.py`) |
| 3 | DPDP PII masking | `security.PIIMasker` on all public/dashboard views |
| 4 | Hash-chained audit | `audit.AuditChain` (SHA-256, append-only) |

## Layout
```
myvote/
  config.py     YAML config loader (isolated; project-root = this dir)
  db.py         SQLAlchemy engine + own Base (separate DB: myvote/data/electoral.db)
  enums.py      FlagState, FlagCategory, ConfidenceTier, ...
  models.py     Elector, FormSubmission, DiscrepancyFlag, BLOReviewSubmission, AuditLogEntry
  eronet.py     MockERONET synthetic seeder (plants all edge cases)
  detection.py  DSD (name/age/relative/address) + PSD (mock cosine) + tiering
  flags.py      turns detections into persisted DiscrepancyFlag rows (audited)
  audit.py      AuditChain: append-only SHA-256 hash chain + verify()
  security.py   TOTP auth, 15-min absolute / 5-min idle sessions, PII masking
  workflow.py   state machine, routing, blind double-review, FIR + negligence dossier
  schemas.py    Pydantic v2 API schemas
  api.py        FastAPI router under /myvote/api + mount() adapter
  pages.py      server-rendered Jinja2 dashboard at /myvote/
  main.py       standalone FastAPI app
  templates/    dashboard.html (Tailwind via CDN)
  tests/        pytest suite (47 tests)
```

## Run standalone
```bash
pip install -r myvote/requirements.txt
uvicorn myvote.main:app --host 127.0.0.1 --port 8001
# dashboard: http://127.0.0.1:8001/myvote/
# health:    http://127.0.0.1:8001/myvote/api/health
```

## Tests
```bash
# from the repo root
python -m pytest myvote/tests -q
```

## Mount into the upstream backend (optional, opt-in)
MyVote-D does **not** require any change to upstream. To expose it inside the
existing backend app, add this to `backend/app/main.py` (fully optional):
```python
try:
    from myvote.api import mount as mount_myvote
    mount_myvote(app)   # adds /myvote/api/* and /myvote/ pages
except Exception:
    pass  # MyVote-D is an optional subsystem; never break upstream if absent
```

## Workflow
```
FLAGGED -> ASSIGNED -> BLO_REVIEW -> CONFIRMED
                                     \-> REJECTED
```
- A **HIGH**-confidence rejection by the first BLO escalates to a **second,
  independent reviewer** (blind double-review).
- If the second reviewer **overturns** (confirms), a **Negligence Review
  Dossier** (JSON + PDF) is generated for the ERO and a **FIR-evidence** flag
  is set. No voter record is ever deleted or altered.
