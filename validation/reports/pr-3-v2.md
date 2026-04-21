# Validation Report: PR #3 (v2)

**Verdict:** REQUEST_CHANGES
**Date:** 2026-04-21
**Target:** https://github.com/iceman12276/shared-todos/pull/3 (branch `feat/pr3-sharing` @ `0b2da13`)

## Summary

v2 revision addresses all 6 v1 must-fix items: items/router UUID path types, redundant Share `UniqueConstraint`, `create_share` IntegrityError mapping, `effective_role` unknown-role logging, byte-identicality test assertion upgraded to `.content ==`, and cascade-delete Share-row assertion. 5 fix commits on top of v1 head (`ead22cc` → `0b2da13`), 303-line delta, +4 new tests (total 209/209 pass). CI fully green; runtime behavior correct end-to-end — qa-engineer re-verified the 11-cell OQ-1 matrix at the wire plus the two new IntegrityError wire paths (FK-violation → 404 byte-identical; duplicate-share → 409).

Verdict is REQUEST_CHANGES due to a **three-stream convergence** on one root design choice — the `create_share` IntegrityError handler dispatches via substring match (`"pk_shares" in str(exc.orig)`) with a catchall `else: → 404`. silent-failure-hunter flagged it as a production-code bug (CRITICAL), security-reviewer flagged the OQ-1 monitoring impact (MEDIUM), and pr-test-analyzer independently flagged the test-side brittleness where tests mock `Exception(...)` strings rather than real psycopg3 error classes (MEDIUM). That's the strongest convergence signal across v1 or v2. Plus two smaller items — `effective_role` still silent to user-path on unknown stored role, and a missing integration test for the 422-on-bad-UUID path that commit `1e8929e`'s message promises.

Three must-fix items total, all small, all narrow. Notable progress on v1 items: no v1 must-fix was rolled back, code-reviewer found no new regressions, and v2 preserves anti-enumeration byte-identicality on the new FK-violation path.

## Stream 1 — Runtime (QA Engineer)

**Verdict from QA:** PASS.

- Full pytest suite against real Postgres: **209/209 pass** (author's claim confirmed exactly, up from v1's 205).
- OQ-1 wire matrix at `0b2da13`: 11/11 cells return HTTP 404 via real uvicorn, zero 403s. Byte-identical `{"detail":"Not found"}` for stranger-on-real-list and ghost-UUID.
- FK-violation wire path: `POST /lists/{id}/shares` with nonexistent user_id → 404, body byte-identical to all other 404 paths. No enumeration oracle.
- Duplicate-share wire path: first share → 201, duplicate → 409 `{"detail":"User already has access"}`. Not 500.
- No PR-2 regressions; CSRF + session token tests remain green.

Full report: `validation/qa-reports/pr-3-v2.md`

## Stream 2 — Security (Security Reviewer)

**Verdict from security-reviewer:** PASS_WITH_FINDINGS (1 new MEDIUM). Under validation-lead's binary rubric: contributes to REQUEST_CHANGES.

**v1 resolutions verified:**
- v1 MEDIUM (`item_id: str` → UUID): RESOLVED. FastAPI validates boundary; non-UUID returns 422, not a 500 leak.

**SAST / SCA / OWASP:**
- Semgrep MCP scan (2789 rules, 4 v2-delta production files): 0 findings.
- Semgrep AppSec platform: 0 new open. 1 INFO pre-existing (pytest CVE-2025-71176, accepted since PR-2).
- Lockfile unchanged — SCA skipped.
- A01 access control: `require_list_permission` gate unchanged and correct.
- A04 anti-enumeration: byte-identicality preserved on the new FK-violation → 404 path.
- A09 logging: new IntegrityError branches have no `_log.*` calls before raising.

**Findings:**
- 1 MEDIUM — IntegrityError discrimination at `shares/router.py:53-60` uses substring match, and tests mock `Exception(...)` rather than psycopg3 error classes.
- 1 INFO — `effective_role` unknown-role log at ERROR; WARNING is more appropriate.
- 1 A09 observation — IntegrityError branches lack logging before raising.

Full report: `security/reports/pr-3-v2.md`

## Stream 3 — Structural (PR Review Specialists)

### code-reviewer v2 — CLEAN

All 6 v1 must-fix items verified fixed in the delta:
- `item_id: UUID` (update_item line 43, delete_item line 64)
- Redundant Share `UniqueConstraint` removed across 3 lockstep files (model, migration, test)
- IntegrityError handler present with PK/FK distinction
- `effective_role` emits `_log.error(...)` on unknown role
- `test_anti_enum_list_404_body_identical` uses `r_real.content == r_ghost.content`
- `test_delete_list_cascades_items_and_shares` now asserts the Share row is gone

Reformat commit (`0b2da13`) is cosmetic. No new regressions in the delta.

### pr-test-analyzer v2 — 1 gap + 1 echo

- C-1 and C-2 from v1 closed correctly. C-3 addressed via the constraint-behavior work in `1e8929e`.
- **Gap:** No integration test covers the 422-on-bad-UUID path that `1e8929e`'s commit message promises (`PATCH /lists/{id}/items/not-a-uuid` → 422). Single-line test fix.
- **Echo:** Item 3's tests are coupled to the substring-match implementation — they construct `Exception(...)` with hardcoded `"pk_shares"`/`"fk_..."` substrings rather than instantiating real psycopg3 error classes. Won't catch real driver version drift. (Two-stream: same root as silent-failure-hunter NEW-H1.)

### silent-failure-hunter v2 — 2 new HIGH + 1 MEDIUM

- **NEW-H1 (CRITICAL)** `shares/router.py:45-56` — dispatch via `"pk_shares" in str(exc.orig)`:
  - Substring match against constraint name is not a stable API (psycopg3 version, locale, future rename).
  - `else: → HTTPException(404)` is an unconditional catchall. CHECK violations (pgcode 23514), NOT NULL (23502), and any future IntegrityError class get silently returned as "Not found" — indistinguishable from legitimate 404s.
  - OQ-1 byte-identicality is preserved on the known-good FK path, but the catchall hides production 500s that should surface in monitoring.
  - One-line fix: dispatch via `isinstance(exc.orig, psycopg.errors.UniqueViolation | ForeignKeyViolation)` or `exc.orig.sqlstate`; re-raise unrecognized.
- **NEW-H2 (HIGH)** `authz/permissions.py:62-65` — `_log.error(...)` is correct level, but function still returns `None` silently. Users with legitimately-unrecognized roles (e.g., future migration bug corrupting `share_role`) experience unexplained access loss with no visible signal. Current state (ERROR log + silent 404) is the worst of both — ops see it, user sees nothing distinguishable from stranger-deny.
- **NEW-M1 (MEDIUM)** Test-side brittleness of Item 3's tests — coupled to the substring-match implementation, manufacturing `Exception(...)` with hardcoded constraint-name substrings. Fixing NEW-H1 fixes this too.

## Cross-Stream Correlations

**Three-stream confirmation — IntegrityError dispatch (the v2 blocker):**

| Layer | Specialist | Finding | Severity |
|-------|-----------|---------|----------|
| Production dispatch logic | silent-failure-hunter | NEW-H1 — substring match + catchall 404 swallows unrelated IntegrityErrors | CRITICAL |
| Security impact | security-reviewer | MEDIUM — OQ-1 body preserved but diagnostic signal is wrong; 500s never surface in monitoring | MEDIUM |
| Test-side | pr-test-analyzer | Echo — tests mock `Exception(...)` rather than psycopg3 error classes | MEDIUM |

Three streams, one root cause: pgcode is the stable API; constraint-name substrings are not. A single refactor (isinstance or sqlstate dispatch) resolves all three findings and fixes the tests-are-weaker-than-they-look-on-paper problem in the same commit.

**This is the strongest convergence signal we've observed across v1 or v2.** Convergence at 3 layers — production code, security-layer impact, test-side validity — crosses from "stylistic opinion" to "design is wrong."

## Required Actions (gate the flip to PASS)

1. `backend/app/shares/router.py:45-60` — replace `"pk_shares" in str(exc.orig)` substring match with `isinstance`-based dispatch on `psycopg.errors.UniqueViolation` → 409 and `psycopg.errors.ForeignKeyViolation` → 404. Re-raise unrecognized `IntegrityError` to the 500 handler rather than silently 404-ing. Update `test_shares.py` to mock `exc.orig` with real psycopg3 error class instances, not bare `Exception(...)`. *(silent-failure-hunter NEW-H1 + security-reviewer MEDIUM + pr-test-analyzer echo — three-stream)*
2. `backend/app/authz/permissions.py:62-65` — `effective_role` must not be silent to the user on unknown stored role. Either (a) raise a typed exception end-to-end, or (b) keep graceful-degrade `return None` but document the policy explicitly in the docstring and add a metric counter. Current state (ERROR log + silent 404) is the worst of both. *(silent-failure-hunter NEW-H2)*
3. Add a single-line integration test asserting `PATCH /lists/{id}/items/not-a-uuid` returns 422. Commit `1e8929e`'s message promises this behavior; test coverage should match the claim. *(pr-test-analyzer gap)*

## Recommended Follow-up (not merge-blocking; defer to cleanup PR)

- All v1 deferred follow-up items remain deferred (Literal tightening, `StoredShareRole`/`EffectiveRole` split, SQL UNION for `list_lists` dedup, `reason=` log discriminators, audit log on cross-list item_id probes, probe-router fixture isolation, Item.order server_default, test helper email-normalization bypass, hardcoded ghost UUID, dead-code 404 branches).
- security-reviewer v2 INFO (ERROR→WARNING log level on unknown share_role): subsumed by NEW-H2 fix.
- security-reviewer v2 A09 (no logs on IntegrityError branches before raising): subsumed by the sqlstate dispatch refactor.

## Auto-merge interaction

Per Step 2.9 of the `validate-new-prs` skill, REQUEST_CHANGES blocks auto-merge. Review body posted via `gh pr comment`; labels `claude-validated:v1` + `claude-validated:changes-requested` applied. Next-action for engineering: either fix the 3 items (push commits, remove both labels to force re-validation) or reply on PR with per-finding false-positive justification.

## Notable patterns from this cycle

**The v1→v2 cycle demonstrated that fixes introducing new attack surface deserve targeted re-review at the new surface.** The v2 IntegrityError handler is new code written to close v1 findings; it introduced a new failure class (substring fragility + catchall 404). This class of pattern — fix-creates-new-finding — is why delta-focused re-review is more valuable than rubber-stamping "all v1 findings addressed."
