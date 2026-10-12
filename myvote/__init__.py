"""MyVote-D: Electoral Roll Discrepancy Detection & BLO Verification System.

A self-contained, decision-support subsystem integrated into the upstream
``cline`` monorepo as an isolated top-level package.

Hard guarantees (unchanged from the original prototype):
  * 100% SYNTHETIC data only (never real voter data);
  * the system NEVER auto-deletes a voter record (it only flags, routes to a
    BLO, and generates ERO notices);
  * PII is masked on all public-facing dashboards (DPDP-inspired);
  * every state change is written to an append-only, SHA-256 hash-chained
    audit trail.
"""

__version__ = "1.0.0"
