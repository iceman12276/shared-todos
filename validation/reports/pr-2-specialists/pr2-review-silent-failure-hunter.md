# PR #2 Silent Failure Hunt — 8 CRITICAL, 6 HIGH, 5 MEDIUM

## SYSTEMIC FINDING: NO LOGGING INFRASTRUCTURE EXISTS IN `backend/app/`
`grep -r "logger\|logging\|.info(\|.error(\|.warning("` → **0 matches**. No Python logging imported, no logger configured. Every error path below has zero audit trail. Fix order must start with introducing `app/logging_config.py`.

## CRITICAL

### C1. SMTP send silently suppresses — commit message FALSELY CLAIMS "logged server-side"
`router.py:172-173` — `contextlib.suppress(Exception)` around `aiosmtplib.send`. Commit `e3c7559` message claims "SMTP errors are logged server-side" — **this claim is false**. Every SMTPConnectError/AuthenticationError/RecipientsRefused/TimeoutError vanishes. User sees 200, email never arrives, zero operational signal.

### C2. OAuth id_token decode `except (ValueError, Exception)` (overlaps code-reviewer C3)
`oauth.py:178-184` — collapses every decode failure silently. With signature verification also deferred (M1), forged id_tokens leave zero trace.

### C3. OAuth token-exchange non-200 collapsed with no upstream context
`oauth.py:169-173` — 400 (user replayed code, expected) indistinguishable from 500 (Google down, urgent) from 429 (we're rate-limited, urgent).

### C4. httpx / aiosmtplib network errors unwrapped
`oauth.py:158-167` + `email.py:20-25` — ConnectError/TimeoutException propagate as 500 with no log of which upstream failed.

### C5. `google_client_id` / `google_client_secret` default to empty string; OAuth ships broken silently
`config.py:21-22` — prod forgets env var, OAuth redirects to Google with empty client_id, Google errors, app returns `oauth_cancelled`, ops takes days to realize config missing. **Fix:** Pydantic model_validator rejecting empty creds when `cookie_secure=True`.

### C6. `secret_key` dev-default `"dev-secret-key-change-in-production"` has no prod guard
`config.py:13` — used to sign OAuth state via itsdangerous. Prod deploy forgets SECRET_KEY → forgeable state tokens → OAuth CSRF protection bypassed. No validator rejects the default.

### C7. CSRF middleware silent-bypass when cookie missing
`csrf.py:48-49` — if `csrf_token` cookie absent, skip enforcement entirely. Cookie-only check: does NOT verify session cookie also absent. Session present + CSRF absent (cookie desync, XSS-clearing, subdomain manipulation) = authenticated request sails through with zero log.

### C8. Zero audit trail for failed login, lockout, successful login, password reset, OAuth account auto-link
All security events silent. Post-breach forensics impossible. OAuth auto-link particularly dangerous (attacker links google_sub to victim's account → no log of event).

## HIGH
- H1. `InvalidHashError`/non-mismatch argon2 errors bubble as 500 with no log (password.py:24-28)
- H2. X-Forwarded-For trusted unconditionally (rate_limiter.py:24-29) [overlaps code-reviewer H2]
- H3. Google-only-account password attempt indistinguishable from wrong-email in logs (router.py:109-115)
- H4. OAuth callback: `email_verified` claim not checked [overlaps code-reviewer C2]
- H5. `password_reset_complete` partial-failure between two commits [overlaps code-reviewer H1]
- H6. Logout silently no-ops on missing/invalid token, no log of "logout killed real session vs no-op"

## MEDIUM
- M1. OAuth id_token signature verification deferred with runtime silence — no startup WARNING log, no ADR
- M2. `_decode_id_token_payload` unconditional `"=="` b64 padding
- M3. `register` two-commit partial state (user row without session → register retry hits anti-enum branch → permanent lockout for that email)
- M4. `_store` unbounded dict in rate_limiter [overlaps code-reviewer H4]
- M5. Wrong-password against existing user not logged — targeted-attack signal invisible

## VERIFIED INTENTIONAL (not findings)
Anti-enumeration register duplicate-email, login user-not-found, password-reset-request always-200. OAuth user-cancelled path. All `secrets.compare_digest` usages correct.

## Meta-recommendation
1. Introduce `app/logging_config.py` + structured logging FIRST — fixing C1-C8 without it is meaningless.
2. Wire `main.py` to configure root logger at startup.
3. Fix C1, C3, C4 (silent-swallow operational errors).
4. Fix C5, C6 (boot-time config validators — LOUD per CLAUDE.md).
5. Fix C7, C8, H-series.
