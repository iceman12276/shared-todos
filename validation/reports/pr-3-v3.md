# Validation Report: PR #3 (v3)

**Verdict:** PASS
**Date:** 2026-04-21
**Target:** https://github.com/iceman12276/shared-todos/pull/3 (branch `feat/pr3-sharing` @ `0548756c`)

## Summary

v3 is the final revision of the sharing/authz PR. All 3 v2 must-fix items resolved with positive-evidence strengthening. All 4 active validation streams returned clean at the strict rubric bar: pr-test-analyzer CLEAN, silent-failure-hunter CLEAN (both v2 HIGHs closed via live verification), security-reviewer PASS, qa-engineer PASS across all 4 wire checks. Zero findings at any severity in the 229-line delta.

This is the first commit in the PR-3 iteration where "no findings across every active stream" genuinely holds. The v3 IntegrityError refactor — `isinstance(exc.orig, psycopg.errors.UniqueViolation | ForeignKeyViolation)` with explicit `raise` for unknown subtypes — closed the v2 three-stream convergence finding with a single targeted change. Engineering's additional `CheckViolation → 500` integration test (exercising the re-raise path with a real psycopg3 error class) is the "positive-evidence" fix-quality pattern that separates removing-the-bad-path from proving-the-good-path. Auto-merge fires per Step 2.9.

## Stream 1 — Runtime (QA Engineer)

**Verdict from QA:** PASS (all 4 checks).

- Full pytest suite against real Postgres: **211/211 pass** (author's claim confirmed exactly, up from v2's 209 via 3 new positive-evidence tests). Note on a transient `InvalidRequestError` seen on first run due to v2 wire-test DB state pollution — resolves cleanly in isolation, confirmed not a v3 regression.
- OQ-1 wire matrix at `0548756c`: 11/11 cells return HTTP 404 at real uvicorn. Zero 403s. The new dispatch path preserves the authz gate behavior.
- FK-violation wire path: `POST /lists/{id}/shares` with nonexistent user_id → 404, `{"detail":"Not found"}`, byte-identical to stranger-on-real-list 404. isinstance dispatch preserves the OQ-1 anti-enumeration invariant on the new path.
- Unknown stored-role wire scenario (positive evidence): injected `role='admin'` Share row via direct SQL (dropped `ck_shares_role_valid` CHECK constraint, inserted, restored). Bad-role user hitting `GET /lists/{id}` returns HTTP 500 plain-text `Internal Server Error` — visible at the wire, NOT silent 404. Confirms raise-end-to-end behavior intended by commit `26062c9`.
- PR-2 authz + session layers: no regressions.

Full report: `validation/qa-reports/pr-3-v3.md`

## Stream 2 — Security (Security Reviewer)

**Verdict from security-reviewer:** PASS.

- Semgrep MCP scan (2789 rules, 3 v3-delta production files): 0 findings.
- Semgrep AppSec platform: 0 new open. 1 pre-existing INFO (pytest CVE-2025-71176, accepted since PR-2, unchanged).
- Lockfile unchanged — SCA skipped.

**v2 finding resolutions verified:**
- v2 MEDIUM on IntegrityError dispatch: RESOLVED via isinstance refactor + `bare raise` for unknown subtypes. All three branches tested with real psycopg3 error class instances. `CheckViolation` integration test asserts the re-raise path reaches the 500 handler.
- v2 INFO on log level: RESOLVED stronger than recommended. backend-dev chose to replace `_log.error(...)` with `raise ValueError(...)` entirely, matching `can_perform()`'s raise-on-unknown-action contract. This surfaces the failure to ops AND client rather than just to logs.

**OWASP spot-checks:**
- A01 access control: `require_list_permission` gate unchanged. isinstance-chain ordering verified — `UniqueViolation` and `ForeignKeyViolation` are disjoint siblings under `IntegrityError`, so ordering is immaterial.
- A04 anti-enumeration / byte-identicality: same FastAPI serialization path; `detail="Not found"` matches authz-deny exactly. No drift from v2.

Full report: `security/reports/pr-3-v3.md`

## Stream 3 — Structural (PR Review Specialists)

Two specialists dispatched for v3 (code-reviewer and type-design-analyzer skipped per routing — v2 CLEAN + narrow delta).

### pr-test-analyzer v3 — CLEAN

All 3 v3 test groups verified as meaningful positive-evidence tests:
- **CheckViolation → 500 (10/10):** Real E2E via `AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False))`. Real `psycopg.errors.CheckViolation()` instance, not faked. Asserts the loud path (unknown IntegrityError reaches 500 handler).
- **422-on-bad-UUID PATCH + DELETE (7/10):** Both covered, real FastAPI validation layer, status-code-only assertion (correct tradeoff).
- **Unknown share_role raises ValueError (9/10):** Uses `pytest.raises(ValueError, match=...)`. Alembic-fileConfig workaround AND `_log`/`logging` imports all removed cleanly — no half-converted state.

**Test-fidelity upgrade noted:** v2→v3 refactor from `Exception('pk_shares')` string-mocks to real `psy_errors.UniqueViolation()` instances is a strict improvement — closes the mock/prod drift the test-analyzer flagged in v2.

### silent-failure-hunter v3 — CLEAN

Both v2 HIGHs closed, via live-verification methodology (not just code-reading).

**NEW-H1 (IntegrityError dispatch) closed:**
- isinstance dispatch verified live (`UniqueViolation → 409`, `ForeignKeyViolation → 404`, classes disjoint, no ordering bug)
- Unknown IntegrityError subtypes re-raise cleanly; integration test `test_create_share_unknown_integrity_error_reraises` asserts 500
- OQ-1 body-identicality preserved (grep confirms all 4 stranger-404 sites + `authz/dependencies.py:82` use identical `detail="Not found"`)
- CSRFMiddleware (BaseHTTPMiddleware) doesn't intercept exceptions from `call_next` — re-raise reaches FastAPI's 500 handler untouched

**NEW-H2 (effective_role silent-None) closed:**
- `ValueError` surfaces end-to-end (traced call chain: `permissions.py:65` → `dependencies.py:72` no try/except → FastAPI default 500)
- Grep'd ALL `except ValueError` in backend: 2 callers exist (`auth/oauth.py` token-decode, `auth/router.py` email best-effort) — neither in the authz path
- Cleanup correctness: removed `_log` import clean, removed `logging`/caplog/fileConfig workaround clean — no half-converted state
- Unit tests verified live: 12/12 pass

**No test-side silent failures introduced by the v3 changes.**

## Cross-Stream Picture — All Streams Clean

| Stream | Verdict | Key evidence |
|---|---|---|
| code-reviewer | (skipped v3 per routing) | v2 was CLEAN; delta is fixes-only |
| pr-test-analyzer | CLEAN | Positive-evidence framing confirmed; tests exercise real failure modes |
| silent-failure-hunter | CLEAN | NEW-H1 + NEW-H2 both closed; live verification methodology |
| security-reviewer | PASS | OQ-1 byte-identicality preserved on new dispatch path; Semgrep clean |
| qa-engineer | PASS | 211/211 pass; OQ-1 matrix 11/11; FK-violation byte-identical at wire; unknown-role raises end-to-end |

## v1→v3 Iteration Arc

| Revision | Must-fix items | Stream-level signal |
|---|---|---|
| v1 | **6** — items/router UUID drift, redundant Share UniqueConstraint, IntegrityError mapping, effective_role unknown-role log, byte-identicality test, cascade-share assertion | Mixed HIGH/MEDIUM across 4 specialists |
| v2 | **3** — IntegrityError dispatch design, effective_role silent-return, missing 422-on-bad-UUID test | 3-stream convergence on the dispatch anti-pattern |
| v3 | **0** | All 4 streams clean |

## Patterns Captured

Two patterns worth carrying forward to future validation cycles:

**1. Three-stream convergence (from v2).** When the same root design choice is independently flagged by structural review, security impact, AND test-side validity at three different layers, the finding moves from "one specialist's opinion" to "the design is wrong." v2's three-stream convergence on string-match constraint dispatch was closed by engineering with a single isinstance refactor — matching the "one root, one fix" framing. Use the 3-row layer table in review bodies (production / security / test) to name the signal explicitly.

**2. Positive-evidence test pattern (adopted in v3).** Tests that assert the loud path works (e.g., `test_create_share_unknown_integrity_error_reraises` constructs a real `CheckViolation()` and asserts 500) are strictly stronger than tests that assert "the bad path is absent." The former fails if the loud behavior regresses; the latter can silently weaken under refactor. This is the fix-quality signal that separates "I removed the silent-failure mode" from "I proved the visible-failure mode works." When reviewing revision PRs closing silent-failure findings, require positive-evidence tests rather than accepting absence-based tests.

## Auto-merge interaction

Per Step 2.9 of the `validate-new-prs` skill, PASS triggers auto-merge: `gh pr merge 3 --squash --delete-branch`, followed by SendMessage notification to engineering-lead. This was the dry-eval-tested flow that is now live.

## Deferred to follow-up (carried over)

All v1 recommended follow-up items remain deferred to a cleanup PR:
- `Action` / `Role` `Literal` narrowing
- `StoredShareRole` vs `EffectiveRole` split
- `can_perform` symmetry (raise on unknown role strings) — partially addressed in v3 via `effective_role` raise, but `can_perform` itself unchanged
- SQL `UNION` replacement for `list_lists` Python-side dedup
- `reason=` discriminator in authz deny logs
- Audit log on cross-list item_id probes
- Fixture-scoped test app for the probe router
- LOW items: Item.order server_default, hardcoded ghost UUID, test helper email-normalization bypass

None of these block PR-3 merge. They're tracked here for whoever owns the cleanup PR.

## Notable cross-cycle observation

The `ValueError` on unknown stored role currently surfaces as uvicorn's default plain-text 500 rather than JSON. Acceptable for v3 given the invariant (end-to-end visibility) is preserved — JSON-wrapping via a FastAPI exception handler would be a DevEx nicety, not an OQ-1 correctness issue. If frontend work in later phases wants a JSON-shaped 500 for client handling, that's a future-PR task.
