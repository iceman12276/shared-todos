# PR #2 Code Review (code-reviewer) — 3 CRITICAL, 4 HIGH, 4 INFO

## CRITICAL

### C1. OAuth callback does not set `csrf_token` cookie — Google-auth users have NO CSRF protection (confidence 98)
`backend/app/auth/oauth.py:210` (`_set_session_cookie` at line 94-101)
OAuth callback only sets session cookie, not csrf_token. Combined with `csrf.py:49-51` (skip-when-no-cookie), EVERY mutating request from OAuth-authenticated browsers bypasses CSRF. PR-3+ will inherit a CSRF-unprotected session from OAuth users. **Fix:** hoist `_set_auth_cookies` helper to shared location; call from oauth.py. Add test `test_oauth_callback_sets_csrf_cookie`.

### C2. OAuth account-linking by email without `email_verified` check — account takeover (confidence 95)
`backend/app/auth/oauth.py:184-197`
id_token payload contains `email_verified` but never consulted. Attacker with Google Workspace (custom domain) can register `victim@existing-user.com` without verifying, sign in via OAuth, system links their google_sub to victim's existing password account → full access. Google docs explicitly warn to check email_verified before trust. **Fix:** reject if `not payload.get("email_verified")` before linking.

### C3. `except (ValueError, Exception)` swallows all errors (confidence 92)
`backend/app/auth/oauth.py:465`
`except (ValueError, Exception)` — Exception subsumes ValueError, catches everything. Masks any bug in `_decode_id_token_payload`, redirects with generic oauth_failed, logs nothing. **Fix:** narrow to `(ValueError, json.JSONDecodeError, binascii.Error)`.

## HIGH

### H1. `/password-reset/complete` non-atomic (confidence 88)
`backend/app/auth/router.py:218-230` — 2 separate commits (burn token, update password), plus a 3rd in invalidate_all_user_sessions. Crash between commits 1 and 2 permanently locks user out (token burned, no password change). **Fix:** hash outside transaction, single atomic commit for all 3 mutations.

### H2. Rate-limiter trusts X-Forwarded-For unconditionally (confidence 85)
`backend/app/auth/rate_limiter.py:22-28` — commit `b98c76d` acknowledges but no code enforces "trusted proxy". Attacker sends XFF with random IP per request → bypass 10/15min limit. **Fix:** add `trust_proxy: bool = False` to Settings (fail-closed). Add integration test.

### H3. ID token iss/aud/exp not verified (confidence 82)
`backend/app/auth/oauth.py:363-374` — only base64-decodes. Signature deferral documented but iss/aud/exp MUST be checked regardless. One-line fix worth doing now to avoid "just decode and trust" becoming the OAuth pattern.

### H4. `_store` unbounded dict in rate-limiter (confidence 80)
`backend/app/auth/rate_limiter.py:19` — IPs never pruned unless successful login. Memory leak / DoS vector when combined with H2. **Fix:** prune on record_failed_login entry.

## INFO (MEDIUM downgraded per guidance)

- I1. `logout` does not delete csrf_token cookie — router.py:134-136
- I2. `_CSRF_COOKIE` / `_COOKIE_NAME` duplicated across router.py + oauth.py + csrf.py — rename hazard
- I3. `verify_password(body.password, make_dummy_hash())` ignored return value — wrap in named helper `_equalize_login_timing`
- I4. `_user_out` returns raw dict, bypassing Pydantic output contract — set response_model

## CLAUDE.md compliance: PASS across all checks
Base.metadata, type_annotation_map, explicit-commit, fail-fast Settings, uv-only, TDD, 4-Ws commits, file organization.

## Verdict
**3 CRITICAL, 4 HIGH, 4 INFO. Request-changes recommended.** C1/C2 are auth defects PR-3/4/5 would inherit. C1, C2, C3, H1 must-fix; H2/H3/H4 acceptable as tracked follow-ups WITH minimal safeguards; INFO nits for cleanup.
