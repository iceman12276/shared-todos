# QA Runtime Validation Report: PR #2 v2

**Date:** 2026-04-21
**QA Engineer:** qa-engineer
**Branch:** `feat/pr2-auth` @ `9c4faf0c48ed34dd8058e4c42e4feb4228ffddd8`
**Worktree used:** `/home/isaac/Desktop/dev/shared-todos-pr1`
**Bug-repro worktree:** `/home/isaac/Desktop/dev/shared-todos-qa-repro-pr2` (branch `test/repro-pr2`)

---

## Environment

- Python 3.12.11 / pytest 8.3.5 / uvicorn
- Real Postgres (docker compose, `shared-todos-pr1-postgres-1`)
- Real mailhog (docker compose, `shared-todos-pr1-mailhog-1`)
- Migration at head: `380d8a29fa13`
- No mocks in test suite (confirmed: `ASGITransport` with real app, real DB)

---

## Local Test Suite Results

**96/96 tests pass** (CI shows 68+; the additional 28 tests are from PR-2 v2 remediation commits that landed after the original CI run).

```
96 passed in 6.90s
```

All test files:

| File | Tests | Result |
|------|-------|--------|
| `integration/test_auth_register_login.py` | 12 | PASS |
| `integration/test_csrf.py` | 9 | PASS |
| `integration/test_logging.py` | 3 | PASS |
| `integration/test_oauth.py` | 8 | PASS |
| `integration/test_password_reset.py` | 6 | PASS |
| `integration/test_rate_limit.py` | 1 | PASS |
| `integration/test_session_token_hash.py` | 2 | PASS |
| `integration/test_user_check_constraint.py` | 3 | PASS |
| `test_alembic_boots.py` | 1 | PASS |
| `test_app_boots.py` | 2 | PASS |
| `unit/test_config.py` | 6 | PASS |
| `unit/test_cookies.py` | 3 | PASS |
| `unit/test_logging_config.py` | 3 | PASS |
| `unit/test_models.py` | 15 | PASS |
| `unit/test_password.py` | 5 | PASS |
| `unit/test_rate_limiter.py` | 4 | PASS |
| `unit/test_session_service.py` | 6 | PASS |
| `unit/test_timing_invariant.py` | 1 | PASS |
| `unit/test_tokens.py` | 6 | PASS |

---

## Preflight.sh Results (Group H)

All gates green:

```
==> ruff check (lint)     — All checks passed!
==> ruff format --check   — 49 files already formatted
==> mypy --strict         — Success: no issues found in 49 source files
==> pytest                — 96 passed in 6.89s
```

---

## v1 Blockers Resolution Verification

All 13 blockers from the v1 validation report confirmed resolved via static analysis + in-process runtime:

| # | Severity | Finding | Status |
|---|----------|---------|--------|
| CRITICAL-1 | CRITICAL | OAuth RS256 via google-auth `verify_oauth2_token` | RESOLVED |
| CRITICAL-2 | CRITICAL | `app/logging_config.py` exists, wired at startup | RESOLVED |
| CRITICAL-3 | CRITICAL | `require_secure_secrets_in_production` model_validator in config.py | RESOLVED |
| CRITICAL-4 | CRITICAL | `email_verified` check in oauth.py callback | RESOLVED |
| HIGH-5 | HIGH | `app/auth/cookies.py` shared module with csrf_token set | RESOLVED |
| HIGH-6 | HIGH | No bare `except Exception` in oauth.py | RESOLVED |
| HIGH-7 | HIGH | `trust_proxy: bool = False` default; `_client_ip()` ignores XFF | RESOLVED |
| HIGH-8 | HIGH | Atomic reset: single `db.commit()` covering token-burn + password + session-invalidation | RESOLVED |
| HIGH-9 | HIGH | `Session.token_hash` column replaces raw `token` column | RESOLVED |
| HIGH-10 | HIGH | `authlib` removed from `pyproject.toml` and `uv.lock` | RESOLVED |
| MEDIUM-11 | MEDIUM | `CheckConstraint("password_hash IS NOT NULL OR google_sub IS NOT NULL")` on `User` | RESOLVED |
| MEDIUM-12 | MEDIUM | `tests/unit/test_timing_invariant.py` exists and passes | RESOLVED |
| MEDIUM-13 | MEDIUM | Bug-encoding comments in csrf.py and rate_limiter.py corrected | RESOLVED |

---

## Targeted Runtime Exercises

### Exercise 1: OAuth state tamper rejection

**Result: PASS**

Manual HTTP call to `/api/v1/auth/oauth/google/callback?code=FAKE_CODE&state=TAMPERED_STATE` with valid `oauth_state_nonce` cookie returns `400 {"detail": "Invalid state"}`. State signature verification is enforced.

### Exercise 2: Rate limit with spoofed XFF (HIGH-7)

**Result: PASS**

In-process ASGI test with 10 failed logins, each with a different `X-Forwarded-For` header (10.0.0.1 through 10.0.0.10). All 10 land in the same `127.0.0.1` bucket. 11th attempt returns 429.

Log confirmation: `rate-limit: login lockout triggered ip=127.0.0.1 attempts=10`

The rate limiter correctly uses `request.client.host` (`127.0.0.1`), ignoring all 10 different XFF values. `trust_proxy=False` is the default and is not set in `.env`.

**Environment-parity observation:** In-memory `_store` does not persist across server restarts. Manual HTTP calls to a detached uvicorn process failed to trigger 429 because each bash shell spawned and killed a new uvicorn process (fresh in-memory state). This is expected behavior (documented in the PR body: "In-memory store resets on server restart — acceptable for v1"). The integration test correctly exercises this in-process. No bug.

### Exercise 3: Password reset atomicity (HIGH-8)

**Result: PASS**

Confirmed via both static analysis and functional test:
- Single `await db.commit()` in `password_reset_complete`
- `invalidate_all_user_sessions(db, user.id, commit=False)` called before the commit
- Three sessions created for a test user — all 0 remain after reset
- Token marked `used_at` — confirmed
- Password hash changed — confirmed
- All mutations atomic in one transaction

### Exercise 4: `_DUMMY_HASH` timing invariant (MEDIUM-12)

**Result: PASS**

`make_dummy_hash()` is called on the combined condition `if user is None or user.password_hash is None` — this covers BOTH the user-not-found path AND the google-only-account path in a single branch. `verify_password(body.password, make_dummy_hash())` is the exact call made, matching the wrong-password path's argon2 `verify()` operation.

`test_timing_invariant.py` passes with a 10x threshold to absorb CI noise.

### Exercise 5: Anti-enumeration byte-compare

**Result: PARTIAL PASS / LOW BUG FOUND**

| Scenario | Status | Detail |
|----------|--------|--------|
| Login(nonexistent) vs login(wrong-password) | PASS | Both 401, identical `{"detail": "Invalid credentials"}` |
| Register(existing) cookies vs register(new) cookies | PASS | Both set `session` + `csrf_token` |
| Register status codes | PASS | Both 201 |
| Password-reset(existing) vs password-reset(nonexistent) | PASS | Both 200, identical body |
| **Register body shape** | **BUG** | **Bodies have different JSON keys** |

**Bug found:** `register(existing-email)` returns `{"user": null, "message": "If this email is available..."}` while `register(new-email)` returns `{"user": {...}}`. The `message` key is present only in the duplicate-email branch.

---

## Bug Found: Register Body Shape Anti-Enum Leak

**Severity: LOW/INFO**

**Behavior:** `POST /api/v1/auth/register` with a duplicate email returns a JSON body with keys `{user, message}` while a new email returns `{user}`. A body-parsing API caller can distinguish existing from new email addresses by checking for the presence of the `message` key.

**What IS correctly anti-enumerated:**
- HTTP status: both 201
- Set-Cookie: both set `session` + `csrf_token` cookies
- Login and password-reset endpoints: byte-identical

**What is NOT anti-enumerated:**
- JSON response body key shape (duplicate adds `message`)

**Assessment:** The BSD-1 primary anti-enum constraint ("no 409 for duplicate email") is met. The PR body's claim of "identical body" is technically inaccurate. Exploitability requires active JSON body parsing — not passive status/header inspection. This is a lower-severity residual information disclosure.

**Bug-repro test:**
- File: `tests/regression/pr2/test_bug_repro_register_body_shape_leak.py`
- Branch: `test/repro-pr2` @ `c24a521`
- Worktree: `/home/isaac/Desktop/dev/shared-todos-qa-repro-pr2`
- Status: FAILS against `feat/pr2-auth @ 9c4faf0c` for the correct reason

**Remediation options:**
1. **Accept as INFO** — add a code comment documenting that body shape may differ; update PR body claim to be accurate. Delete bug-repro test.
2. **Fix** — either include `message` in both branches (harmless for new registrations) or strip it from the duplicate branch. Make bug-repro test pass.

---

## E2E Verdict per User Story (BSD-1 API layer)

| Story | Endpoint | Verdict |
|-------|----------|---------|
| US-101: Register (email+pw) | `POST /api/v1/auth/register` | PASS (96 tests green) |
| US-102: Login + rate limit | `POST /api/v1/auth/login` | PASS |
| US-103: Google OAuth | `GET /api/v1/auth/oauth/google` + `/callback` | PASS |
| US-104: Logout | `POST /api/v1/auth/logout` | PASS |
| US-105: Session maintenance | `GET /api/v1/auth/session` | PASS |
| US-106: Password reset request | `POST /api/v1/auth/password-reset/request` | PASS |
| US-107: Password reset complete + invalidate all sessions | `POST /api/v1/auth/password-reset/complete` | PASS |

---

## Environment Parity Observations

1. **In-memory rate limiter state vs process lifecycle:** In-memory `_store` resets on server restart. Manual HTTP tests against a detached uvicorn (which terminates per shell invocation) cannot replicate multi-request rate-limit behavior. The integration test suite correctly tests this in-process. No divergence from CI — this is expected behavior, not a bug.

2. **Test count: 96 local vs 68+ CI:** The v2 commits added 28 more tests (logging, session_token_hash, user_check_constraint, config unit tests, cookies unit tests, etc.). CI number reflects the original PR head before remediation commits. All 96 pass locally with real Postgres.

3. **No flakes detected:** All 96 tests pass deterministically in two consecutive runs. No timing-sensitive failures observed.

4. **Alembic round-trip test:** `test_alembic_boots.py::test_alembic_upgrade_then_downgrade` passes against real Postgres. The worktree's DB was already at head before the test run.

---

## QA Verdict

**PASS with one LOW/INFO bug found.**

All 13 v1 blockers are resolved. All 7 user stories pass at the API layer. The one bug found (register body shape) is LOW/INFO severity — the primary anti-enumeration guarantee (no 409, matching status + cookies) is met. The bug represents a residual information disclosure at the body-key level. Engineering/validation-lead should adjudicate whether to accept as INFO or fix.

**The QA stream does NOT block merge on its own.** Routing the body-shape finding to validation-lead for adjudication.
