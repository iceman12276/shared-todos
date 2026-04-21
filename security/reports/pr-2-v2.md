# Security Review: PR #2 v2

**Verdict:** PASS
**Reviewer:** security-reviewer
**Date:** 2026-04-21
**PR Branch:** feat/pr2-auth @ 9c4faf0c
**v1 Head:** 09fe902 (v1 verdict: FAIL — 4 findings blocked merge)
**Scope:** `backend/app/auth/` (11 modules incl. new `cookies.py`, `logging_config.py`), `backend/app/models/` (3 models), `backend/alembic/versions/` (2 new migrations), `backend/app/config.py`, `backend/app/main.py`, `backend/pyproject.toml`, `backend/uv.lock`

---

## Summary

The v2 push (`9c4faf0c`) resolves all four v1 FAIL-blocking findings and all 13 blockers from the consolidated validation report. Every security verification item from the re-review brief was confirmed in code. The cryptographic path is now sound end-to-end: Google ID tokens are verified with `google.oauth2.id_token.verify_oauth2_token` (RS256 + iss + aud + exp), `email_verified` is checked before any DB write, session tokens are stored as SHA-256 hashes, and `authlib` (which carried a CRITICAL JWS signature bypass) has been removed and replaced by `google-auth==2.49.2`. The rate limiter no longer trusts `X-Forwarded-For` unconditionally; a `trust_proxy: bool = False` setting makes the safe default explicit.

The hotfix commit `9c4faf0c` correctly narrows the `except` tuple from `(ValueError, json.JSONDecodeError, binascii.Error, Exception)` to bare `except ValueError`, which is exactly right: `google.oauth2.id_token.verify_oauth2_token` raises only `ValueError` for all verification failures (bad signature, expired, wrong iss/aud). The password reset is now fully atomic (single `db.commit()` covering token-burn + password-update + session-invalidation). The v1 INFO finding on CSRF skip-for-no-cookie has the scope-assumption comment added at `csrf.py:48-54` as recommended; the exploitability scope remains unchanged and the adjudication holds.

Semgrep SAST: **0 findings** across 2,852 rules on 17 files — regression-free from the PR-1 baseline. SCA: `authlib` absent from `pyproject.toml` and `uv.lock`; `google-auth==2.49.2` and its transitive deps (`cryptography==46.0.7`, `pyasn1==0.6.3`, `cachetools==5.5.2`, `rsa` absent — not in lockfile) carry **0 CVEs**.

---

## v1 Blocker Verification

### CRITICAL-1: OAuth signature verification — RESOLVED

- **Claim:** `google.oauth2.id_token.verify_oauth2_token` is used in production; `_production_verify_id_token` is the default verifier.
- **Verified:** `oauth.py:47-56` defines `_production_verify_id_token` which imports `google.auth.transport.requests` and `google.oauth2.id_token` and calls `verify_oauth2_token(id_token, grequest, client_id)`. This is a live call against Google's JWKS — RS256 signature + iss + aud + exp verified in a single library call. `verify_id_token_dep` (the FastAPI dependency) yields `_production_verify_id_token` as the default (non-test) verifier at `oauth.py:59-65`. Tests inject their own verifier via `app.dependency_overrides`. Production path is unambiguously the real verifier.

### CRITICAL-4: email_verified check — RESOLVED

- **Claim:** `payload.get("email_verified") is not True` gates account-link; runs before any User row touch; redirect path does not touch DB.
- **Verified:** `oauth.py:192-199` — after `verify_token()` succeeds, the very next block checks `if payload.get("email_verified") is not True`. On failure it logs a warning and returns a 302 redirect to `?error=oauth_failed` — no `db.execute()`, no `db.commit()`, no User row touch in that path. The DB queries (`select(User)`, `db.add()`, `db.commit()`) appear starting at line 212, downstream of the email_verified gate.

### HIGH-9: Session.token_hash — RESOLVED

- **Model:** `models/session.py:15` — `token_hash: Mapped[str] = mapped_column(sa.String(64), unique=True, index=True)`. Raw token column is gone.
- **On write:** `session.py:16` — `Session(user_id=user_id, token_hash=hash_token(raw_token), ...)`. `hash_token` is imported from `app.auth.tokens`.
- **On read:** `session.py:27` — `.where(Session.token_hash == hash_token(token), ...)`. SQL equality lookup on the hash — correct.
- **On invalidate:** `session.py:33` — `delete(Session).where(Session.token_hash == hash_token(token))` — consistent.
- Migration `aaad963c469e` renames the column and clears existing sessions before the schema change (correct — avoids stale raw-token rows being treated as hashes).

### HIGH-10: authlib removal — RESOLVED

- **pyproject.toml:** No `authlib` entry (confirmed — grep on `*.toml` returned no matches).
- **uv.lock:** No `name = "authlib"` entry (confirmed — both direct and phrase search returned no matches).
- **Import scan:** No `import authlib` or `from authlib` anywhere in `backend/` (confirmed — google-auth search returned only `google.auth`/`google.oauth2` references, not authlib).

### HIGH-10 corollary: google-auth SCA — CLEAN

| Package | Version | CVEs |
|---------|---------|------|
| google-auth | 2.49.2 | 0 |
| cryptography | 46.0.7 | 0 |
| pyasn1 | 0.6.3 | 0 |
| cachetools | 5.5.2 | 0 |

`requests` is NOT in the lockfile — google-auth's `requests` extra is not pulled in by this project.

---

## Hotfix Commit Verification (9c4faf0c)

**Concern:** Group G commit `381fe30` shipped `except (ValueError, json.JSONDecodeError, binascii.Error, Exception)` — `Exception` in the tuple nullified narrowing.

**Hotfix state confirmed:** `oauth.py:185` reads `except ValueError as exc:` — bare ValueError only. The `json`, `binascii` imports that were only used in the old except clause are also removed. This is correct: `google.oauth2.id_token.verify_oauth2_token` raises only `ValueError` for all verification failures; unexpected errors (e.g. network errors during JWKS fetch) correctly bubble as 500.

---

## CSRF Skip Verification (v1 INFO — still holds)

**Concern:** CSRF middleware skip-branch when no cookie present — scope unchanged?

**Verified:** `csrf.py:47-56` — the skip branch is present and now has the scope-assumption comment added exactly as recommended in v1 adjudication:

> "If a future endpoint is added that is (a) unauthenticated AND (b) has meaningful side-effects beyond the reset flow, this skip-branch MUST be revisited — add an explicit path exemption rather than relying on the absence of a cookie."

The exploitability scope remains: only `/password-reset/request` is reachable unauthenticated + mutating, and it is anti-enumerated with no sensitive state-change possible from a CSRF trigger. INFO adjudication stands — no action required.

---

## Semgrep SAST

**0 findings** across 2,852 rules on 17 files (all changed auth + model + config modules).

Files scanned: `oauth.py`, `csrf.py`, `session.py`, `cookies.py`, `rate_limiter.py`, `router.py`, `dependencies.py`, `email.py`, `password.py`, `tokens.py`, `schemas.py`, `config.py`, `logging_config.py`, `main.py`, `models/user.py`, `models/session.py`, `models/password_reset_token.py`.

Semgrep platform historical findings (`iceman12276/shared-todos`): 0 open (SAST + SCA).

Regression-free from the PR-1 and PR-2 v1 baselines.

---

## Dependencies (Changed in v2)

**Removed:**
- `authlib==1.5.2` — 12 CVEs (CRITICAL CVSS 9.1 JWS bypass + 4 HIGH). Removed cleanly. **No CVEs in tree.**

**Added:**
- `google-auth==2.49.2` — 0 CVEs
- `cryptography==46.0.7` (transitive, via google-auth) — 0 CVEs
- `pyasn1==0.6.3` (transitive) — 0 CVEs
- `cachetools==5.5.2` (transitive) — 0 CVEs

Carried forward (unchanged, non-blocking):
- `pytest==8.3.5` GHSA-6w46-j5rx-g56g (LOW) — dev-only, ephemeral CI runners
- `mailhog/mailhog:latest` floating tag (INFO) — CI-only dev infrastructure

---

## Additional New Concerns — Cleared

**SSRF via google-auth JWKS fetch:** `_production_verify_id_token` calls `google.oauth2.id_token.verify_oauth2_token`, which internally fetches Google's JWKS endpoint (`https://www.googleapis.com/oauth2/v3/certs`). This is a fixed Google-controlled URL hardcoded in the library — not user-supplied. No SSRF vector. The `grequest = google.auth.transport.requests.Request()` wrapper uses the `requests` library but only to reach Google's own endpoint. No application-controlled URL is passed.

**SSJI / injection:** No string interpolation into shell commands or SQL. The `google_client_id` passed to `verify_oauth2_token` comes from `Settings.google_client_id` (env-loaded, not user-supplied at request time). Clean.

---

## Positive Security Observations (v2 additions)

- **Logging infrastructure** (`logging_config.py`, `main.py`) — root logger configured at startup; all auth events (register, login, logout, OAuth, rate-limit lockout, password reset) are instrumented. Addresses the CRITICAL-2 systemic gap from v1.
- **Fail-fast Settings** (`config.py:51-81`) — `model_validator(mode="after")` rejects insecure `secret_key`, empty `google_client_id`/`google_client_secret` when `cookie_secure=True`. Mirrors the PR-1 `database_url` pattern.
- **cookies.py shared module** — `set_auth_cookies()` is the single authoritative source for session + CSRF cookie writes, called from both `router.py` and `oauth.py`. Eliminates the drift that caused HIGH-5 (missing CSRF cookie on OAuth path).
- **Atomic password reset** — `prt.used_at`, `user.password_hash`, `invalidate_all_user_sessions(commit=False)` all in a single `db.commit()`. Crash-safe.
- **trust_proxy: bool = False** in Settings — XFF trust is explicit opt-in, not ambient.
- **User CheckConstraint** (`ck_users_has_auth_method`) — DB-level enforcement that every User has at least one auth method (password_hash or google_sub).

---

## Not in Scope

- Full white-box pentest — validation-lead calls shannon-pentest at phase/release completion
- Frontend authentication UI (not yet implemented — PR-6+)
- Runtime E2E with real Google accounts (test verifier used in integration tests; full E2E at release boundary)
- SMTP TLS in production (carried forward from v1 LOW: `start_tls=False` acceptable for dev/CI mailhog; track as follow-up for production SMTP config)
