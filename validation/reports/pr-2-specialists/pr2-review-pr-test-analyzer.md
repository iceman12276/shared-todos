# PR #2 Test Coverage (pr-test-analyzer) — 3 CRITICAL gaps, 2 HIGH gaps

## Totals: 66 tests (PR body claims 68)
32 unit + 34 integration. Strong on anti-enumeration register Set-Cookie, security-fix test coverage (CSRF middleware, OAuth state). Test-quality-gate passes except 1 `# type: ignore[attr-defined]` in `test_models.py:13` inside helper `_col()` (dynamic SQLAlchemy attr access — may or may not trip the grep gate).

## CRITICAL gaps

### CRIT-1. No test for password-reset-request anti-enumeration on Google-only accounts (severity 9)
PR body claims "Google-only account: direction-to-Google message; no email sent." `test_password_reset.py` has 0 tests for user where `password_hash IS NULL`. The `router.py` branch at ~line 160 is untested. Future refactor helpfully returning `{"message": "Use Google sign-in"}` reintroduces enumeration leak.

### CRIT-2. No test that login user-not-found timing matches wrong-password timing (severity 9)
Entire reason `make_dummy_hash()` exists. `test_login_nonexistent_email_same_as_wrong_password` only asserts both return 401 — no timing assertion. A refactor removing `verify_password(body.password, make_dummy_hash())` to save argon2 work would silently pass all tests. **Fix:** monkeypatch counter on `make_dummy_hash` + ratio-timing assertion.

### CRIT-3. No integration test that password-reset-complete invalidates **all** sessions, not just one (severity 8)
`test_reset_complete_success_invalidates_all_sessions` uses ONE user/ONE cookie. If `invalidate_all_user_sessions()` is replaced with `invalidate_session(current)`, test passes. US-107 guarantee of multi-device logout is untested. **Fix:** 2-browser (2-AsyncClient) test → reset → both cookies 401. ~4 lines.

## HIGH gaps

### HIGH-1. Rate-limit window-reset + counter-reset-on-success untested (severity 7)
Only 11-attempts → 429 covered. `reset_failed_logins()` function has zero tests. Successful login within window clearing counter, natural window expiry — both uncovered.

### HIGH-2. No OPTIONS preflight CSRF bypass test (severity 7)
PR body claims "OPTIONS bypass" but `test_csrf.py` has zero OPTIONS tests. Future refactor adding OPTIONS to `_MUTATING_METHODS` would break all CORS preflights silently.

## MEDIUM gaps
- M1. OAuth "provider error / user cancelled" path untested (severity 6)
- M2. Token single-use under concurrent redemption (severity 6)
- M3. No explicit "expired token → error" test (tampered ≠ expired) (severity 6)
- M4. Session TTL expiry at HTTP layer untested (unit only) (severity 5)
- M5. Password-reset-complete new-password min-12-char validation untested at endpoint (severity 5)

## LOW: email validator single bad input, no XFF proxy test, no compare_digest assertion, no csrf cookie httponly=False assertion

## Test Quality Issues
- Rate-limiter `_store` global state: no visible fixture resetting between tests → hidden flake risk
- `test_reset_validate_valid_token`: `password_hash="x"` with `noqa: S106` — not a real argon2 hash; future model invariant would break this silently
- OAuth tests don't assert `user.google_sub == FAKE_GOOGLE_SUB` after link

## TDD concern
Commit #11 (`64d856b`) is where CSRF middleware was FIRST ADDED. Prior CSRF tests in #10 (`4e4b68b`) couldn't have verified enforcement — middleware didn't exist. Integration "POST without X-CSRF-Token → 403" test should have existed BEFORE the middleware commit.

## Positive observations
Anti-enumeration Set-Cookie coverage exceptional. Real Postgres+mailhog throughout, zero global mocks (httpx surgical-mocked via `MockTransport`). OAuth state-cookie-mismatch test directly verifies commit 64d856b's fix.

## Verdict
Body overstates what's tested in 4 concrete places (OPTIONS bypass, Google-only reset, rate-limit reset, expired vs tampered token). 3 CRITICAL gaps are ~60 LOC of additive test code. Recommend these land as a test-hardening commit before merge rather than separate PR.
