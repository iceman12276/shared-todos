# Security Review: PR #3 — v2

**Verdict:** PASS_WITH_FINDINGS
**Reviewer:** security-reviewer
**Date:** 2026-04-21
**Scope:** Delta only — 5 fix commits (`1e8929e`..`0b2da13`, 303 lines, 9 files). PR head: `0b2da13`.
**v1 report:** `security/reports/pr-3.md`

---

## Summary

The v2 delta resolves the v1 MEDIUM finding (item_id UUID type) correctly and introduces an IntegrityError handler for race-condition safety on share creation. The OQ-1 anti-enumeration invariant is preserved and the test is strengthened to byte-level comparison. One new MEDIUM finding: the IntegrityError discrimination uses fragile string-matching on PG error messages rather than psycopg3 error class or pgcode checks. The FK-violation branch correctly emits `{"detail": "Not found"}`, preserving OQ-1 byte-identicality. No new SAST findings.

---

## v1 Finding Status

### MEDIUM: `item_id: str` → `UUID` — RESOLVED

Both `update_item` (line 44) and `delete_item` (line 64) in `backend/app/items/router.py` now declare `item_id: UUID`. FastAPI will now reject non-UUID path values with 422 before the handler runs. This is the correct behavior: 422 is a validation error at the framework boundary, distinct from the 404 OQ-1 deny, and does not leak list-level existence information.

The fix covers both endpoints — the v1 concern about "not just one" is confirmed resolved.

---

## New Findings

### MEDIUM: IntegrityError discrimination uses string-matching, not pgcode/error-class checks

- **Location:** `backend/app/shares/router.py:53–60` (IntegrityError handler in `create_share`)
- **Category:** A04 — Insecure Design (fragile exception discrimination; silent fallthrough on unexpected IntegrityError types)
- **Issue:** The handler distinguishes PK-violation (→ 409) from FK-violation (→ 404) by testing `"pk_shares" in str(exc.orig)`. In production with psycopg3, `exc.orig` is a `psycopg.errors.UniqueViolation` or `psycopg.errors.ForeignKeyViolation` instance with a stable `.pgcode` attribute (`"23505"` vs `"23503"`). The string-match approach has two weaknesses:

  1. **Silent catch-all for unexpected IntegrityError types.** If a third IntegrityError fires (e.g. the `role_valid` CHECK constraint violation — pgcode `23514`) and does not contain `"pk_shares"` in the message, the handler falls through to the FK branch and emits `HTTPException(404, detail="Not found")`. This silently masks what should be a 500 or a 400 (invalid role despite Pydantic validation). The OQ-1 body is preserved, but the signal is wrong.

  2. **Test coverage validates string-matching, not production error types.** The race-condition tests (`test_create_share_duplicate_pk_race_returns_409`, `test_create_share_fk_violation_returns_404`) mock `exc.orig` as a plain `Exception` with the PG message string. They do not exercise the actual psycopg3 error class hierarchy. If psycopg3's error formatting changes (e.g. quoting style around the constraint name), the real-path discriminator breaks while the tests continue to pass.

- **Impact:** The FK-violation branch correctly emits `{"detail": "Not found"}` (OQ-1 byte-identical). The 409 branch correctly emits `{"detail": "User already has access"}`. The immediate security risk is low. The structural risk is that an unexpected IntegrityError (e.g. future schema change adding a new constraint) would silently produce a misleading 404 rather than a 500, making the error invisible in monitoring.

- **Remediation:** Use psycopg3 error class checks instead of string-matching. Replace:
  ```python
  orig = str(exc.orig)
  if "pk_shares" in orig:
      raise HTTPException(status_code=409, ...)
  raise HTTPException(status_code=404, ...)
  ```
  With:
  ```python
  from psycopg.errors import UniqueViolation, ForeignKeyViolation
  cause = exc.orig
  if isinstance(cause, UniqueViolation):
      raise HTTPException(status_code=409, detail="User already has access") from exc
  if isinstance(cause, ForeignKeyViolation):
      raise HTTPException(status_code=404, detail="Not found") from exc
  raise  # unexpected — let it propagate as 500
  ```
  This also adds an explicit `raise` for unexpected IntegrityError types, making monitoring-visible 500s rather than silent 404s. Update the race-condition tests to mock `exc.orig` as the proper psycopg3 error class instances.

- **Reference:** psycopg3 docs — `psycopg.errors` module; PG error codes `23503` (FK), `23505` (unique), `23514` (check)

---

### INFO: unknown share_role logged at ERROR level, not WARNING

- **Location:** `backend/app/authz/permissions.py:62–63`
- **Issue:** The new branch `if share_role is not None: _log.error(...)` logs an unknown share_role at ERROR. An unknown role in the DB (e.g. data corruption or a future migration that adds a role not yet in code) would fire ERROR on every authz call for that user's shares. ERROR severity typically pages on-call; WARNING is more appropriate since the system handles it safely (returns None → 404).
- **Impact:** Alert fatigue / false pages. No security impact.
- **Remediation:** Change `_log.error(...)` to `_log.warning(...)` on the unknown share_role branch.
- **Verdict impact:** INFO — does not block merge.

---

## OQ-1 Anti-Enumeration — v2 Status

**Byte-identicality test upgraded: VERIFIED**

The v2 delta upgrades the anti-enumeration assertion from `r_real.json() == r_ghost.json()` to `r_real.content == r_ghost.content` (raw byte comparison). This is a strengthening — it catches future middleware fields (e.g. `request_id`, `trace_id`) injected into error responses that would pass JSON equality but differ in bytes. Both cases still flow through the same `raise HTTPException(404, detail="Not found")` code path, so byte-identicality holds.

**IntegrityError FK-violation path:** The new FK-violation handler raises `HTTPException(status_code=404, detail="Not found")` — byte-identical to the authz-deny 404. OQ-1 is preserved on this new code path.

**IntegrityError PK-violation path:** Returns 409 with `{"detail": "User already has access"}`. This is correct — the caller already passed list-level authz (they are the owner), so 409 does not leak list existence. Not an OQ-1 concern.

---

## A09 Logging — IntegrityError Paths

The new IntegrityError handler does **not** log either the PK or FK violation branch before raising. The existing `_log.info` for successful share creation is unreachable when an IntegrityError fires (execution jumps to the except block before `_log.info`).

This means race-condition IntegrityErrors on share creation are silent in the application log — no WARNING, no discriminator tag. They will only appear in the DB connection error log (if enabled). The briefing explicitly asks for WARNING-level logging with a `reason=` discriminator on both paths.

Remediation: add `_log.warning("share: integrity violation list_id=%s user_id=%s reason=%s", perm.list_id, body.user_id, reason)` before each `raise HTTPException` in the except block, where `reason` is `"duplicate_pk"` or `"fk_violation"`. This does not affect the OQ-1 response body.

---

## Semgrep Output

**Local SAST scan (`semgrep_scan`):** 0 findings across 2789 rules on 4 changed production files. Clean.

**AppSec platform SAST:** 0 open findings (unchanged from v1).

**SCA:** No lockfile changes (`git diff ead22cc..0b2da13 --stat -- backend/uv.lock` returned empty). SCA scan skipped.

---

## v1 Fix Verification Checklist

| Item | Status |
|---|---|
| `item_id: UUID` on `update_item` | RESOLVED — line 43 |
| `item_id: UUID` on `delete_item` | RESOLVED — line 64 |
| 422 (not 404) on non-UUID item_id | CORRECT — FastAPI path param validation |
| Redundant UniqueConstraint removed from `models/share.py` | RESOLVED — replaced with comment |
| Migration `4df1779548df` edited (not new file added) | RESOLVED — existing file edited, `uq_shares_list_id` line replaced with comment |
| Anti-enum test upgraded to byte comparison | RESOLVED — `r_real.content == r_ghost.content` |
| Share cascade test covers share row deletion | RESOLVED — asserts `share_result.scalar_one_or_none() is None` |

---

## Not in Scope

- **No audit logging on IntegrityError paths** — noted above in A09 section; not a new v2 finding, the v1 report noted logging was present on the pre-existing paths. The new race-condition paths lack logging entirely. Recommend as a follow-up if not addressed.
- **Test mocking pattern** — the race-condition tests mock `AsyncSession.commit` globally with a call counter, which is order-dependent (fires on the Nth call). If the test session adds more commits (e.g. fixture changes), the counter logic could misfire. This is a test robustness concern, not a security finding.
