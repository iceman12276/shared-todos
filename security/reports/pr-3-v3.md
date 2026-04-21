# Security Review: PR #3 — v3

**Verdict:** PASS
**Reviewer:** security-reviewer
**Date:** 2026-04-21
**Scope:** Delta only — 3 fix commits (`231ec2a`..`0548756c`, 229 lines, 5 files). PR head: `0548756c`.
**v2 report:** `security/reports/pr-3-v2.md`

---

## Summary

The v3 delta resolves both v2 MEDIUM findings cleanly. The IntegrityError discrimination now uses `isinstance` checks against psycopg3 error classes; unknown IntegrityErrors explicitly re-raise rather than silently producing a 404. The unknown-share-role path now raises `ValueError` rather than logging at ERROR — a stronger contract that surfaces as a monitoring-visible 500. OQ-1 byte-identicality is preserved on all code paths. No new findings.

---

## v2 Finding Status

### MEDIUM: IntegrityError string-match discrimination — RESOLVED

`backend/app/shares/router.py:47–62` — the handler now uses:

```python
if isinstance(exc.orig, psy_errors.UniqueViolation):
    raise HTTPException(status_code=409, detail="User already has access") from exc
if isinstance(exc.orig, psy_errors.ForeignKeyViolation):
    raise HTTPException(status_code=404, detail="Not found") from exc
raise  # unknown IntegrityError — propagates as 500
```

Both v2 concerns are closed:
1. Unknown IntegrityError types now `raise` explicitly — they surface as 500 and appear in monitoring rather than being silently swallowed as 404.
2. Tests now mock `exc.orig` as `psy_errors.UniqueViolation()` and `psy_errors.ForeignKeyViolation()` — the real psycopg3 error class instances, not plain `Exception`. A new third test (`test_create_share_unknown_integrity_error_reraises`) uses `psy_errors.CheckViolation()` and asserts 500, exercising the explicit re-raise path.

### INFO: unknown share_role logged at ERROR — RESOLVED (stronger fix)

`backend/app/authz/permissions.py:62–64` — the v2 delta changed `_log.error(...)` to `raise ValueError(f"unknown share_role: {share_role!r}")`. This is a stricter contract than the WARNING-log approach recommended in v2: it matches `can_perform()`'s raise-on-unknown-input pattern and surfaces as a monitoring-visible 500 via FastAPI's default exception handler, rather than silently returning None → 404 with a log line that could be missed. The docstring explains the design intent (DB data drift, not a user-facing error). Accepted as a better outcome.

The corresponding unit test (`test_unknown_share_role_raises`) now asserts `pytest.raises(ValueError, match="unknown share_role")` — correct.

---

## Specific Checks

### Check 1 — OQ-1 byte-identicality on FK-violation → 404: PASS

The FK-violation branch raises `HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")`. This is the same `detail` string as the authz dependency's deny path (`raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")`). Both flow through FastAPI's default HTTPException handler, producing `{"detail": "Not found"}` with identical serialization. No drift introduced.

### Check 2 — isinstance chain ordering: PASS

`psy_errors.UniqueViolation` and `psy_errors.ForeignKeyViolation` are sibling classes in the psycopg3 error hierarchy — both inherit from `psycopg.errors.IntegrityError` (DB-level), which itself is a subclass of `psycopg.errors.DatabaseError`. Neither is a parent of the other. The ordering of the two `isinstance` checks is immaterial for correctness. No parent-before-child risk.

### Check 3 — Semgrep SAST on delta files: PASS

0 findings across 2789 rules on 3 changed production files (`shares/router.py`, `authz/permissions.py`, `items/router.py`). AppSec platform: 0 open SAST findings.

### Check 4 — Lockfile delta: PASS (SCA skipped)

`git diff 0b2da13..0548756c --stat -- backend/uv.lock` returned empty. `psycopg` was already a production dependency. No new dependencies introduced.

### Check 5 — item_id UUID 422 tests: PASS

Two new tests in `test_items.py` (`test_patch_item_bad_uuid_returns_422`, `test_delete_item_bad_uuid_returns_422`) confirm that non-UUID `item_id` path segments return 422 — validating the v1 fix at the integration level, not just by type annotation inspection.

---

## Semgrep Output

**Local SAST scan:** 0 findings, 2789 rules, 3 production files.
**AppSec platform SAST:** 0 open findings.
**SCA:** Skipped — no lockfile changes.

---

## Not in Scope

- A09 monitoring gap (no WARNING logs on IntegrityError branches before raising) — deferred per validation-lead's v2 synthesis note. The explicit `raise` on unknown IntegrityErrors partially addresses this (500s are now visible); the PK/FK paths remain silent before raising. Flagged in v2 report; no change in v3.
- v1-deferred follow-ups (unbounded list pagination, rate limiting) — out of scope per briefing.
