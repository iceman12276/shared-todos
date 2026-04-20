# Security Review: PR #2

**Verdict:** FAIL
**Reviewer:** security-reviewer
**Date:** 2026-04-20
**PR Branch:** feat/pr2-auth @ 09fe902
**Scope:** `backend/app/auth/` (10 modules), `backend/app/models/` (3 models), `backend/alembic/versions/e741951e9b5f_*.py`, `backend/pyproject.toml`, `backend/uv.lock`, `backend/app/config.py`, `backend/app/main.py`

---

## Summary

PR #2 delivers the authentication backend (register, login, logout, Google OAuth, password reset, CSRF, rate limiting) against PRD-1. The password hashing, token entropy, session cookie flags, anti-enumeration responses, session invalidation on logout/reset, CSRF double-submit pattern, and OAuth state-binding all implement their PRD requirements correctly.

However, two issues are blocking merge. First, the Google OAuth ID token is decoded without signature verification — the JWT payload (`sub`, `email`) is base64-decoded from the token returned by Google's token endpoint without being verified against Google's JWKS. This allows an attacker who can interpose on the callback (or who can supply a crafted `id_token` directly in a modified token-exchange response) to inject arbitrary identity claims and take over any account. Second, the `X-Forwarded-For` header is trusted unconditionally in the rate limiter, allowing any client to spoof its IP address and bypass the login rate limit entirely.

There is also one HIGH-severity supply-chain finding: `authlib==1.5.2` carries 12 CVEs including a CRITICAL JWS signature bypass (GHSA-wvwj-cvrp-7pv5, CVSS 9.1) and 3 additional HIGHs. **authlib is not imported anywhere in the application code** — it is a dead dependency. This does not exercise the vulnerability in the current code, but the package is installed in every environment and must be either removed (preferred) or bumped to >=1.6.9.

The `secret_key` default of `"dev-secret-key-change-in-production"` is a configuration-time risk: if not overridden, itsdangerous OAuth state signing is trivially bypassable. This is MEDIUM — the `.env.example` documents it, but Settings does not raise on the insecure default.

---

## Findings

### CRITICAL: Google OAuth ID Token Not Signature-Verified

- **Location:** `backend/app/auth/oauth.py`, function `_decode_id_token_payload`
- **Category:** A07 — Identification and Authentication Failures; A08 — Software and Data Integrity Failures
- **Issue:** The function base64-decodes the JWT payload segment without verifying the RS256 signature against Google's JWKS endpoint. The `sub` and `email` fields extracted from the payload are used directly to create or link user accounts. The function comment acknowledges this: "dev/test only path, trust token from Google's own endpoint."
- **Impact:** An attacker who can modify the `id_token` field in the token exchange response (MITM on the HTTP call to `oauth2.googleapis.com/token`, or a misconfigured `google_client_secret` that allows code reuse, or a dependency injection of a malicious httpx transport in a test environment) can forge arbitrary identity claims. In particular, they can set `email` to any existing user's email and link their Google account to that user, then authenticate as them permanently.
- **Remediation:** Verify the ID token's RS256 signature against Google's public JWKS before trusting any claims. Use `authlib` (already a declared dep) or `google-auth`: call `google.oauth2.id_token.verify_oauth2_token(id_token, google.auth.transport.requests.Request(), client_id)` — this handles JWKS fetch, signature verification, `iss`/`aud`/`exp` checks. For v1, the httpx client is already injectable so tests can provide a stub JWKS response.
- **Reference:** [Google Sign-In ID token verification](https://developers.google.com/identity/gsi/web/guides/verify-google-id-token); OWASP A08; [OAuth 2.0 Security Best Current Practice §4.2](https://datatracker.ietf.org/doc/html/draft-ietf-oauth-security-topics)

---

### HIGH: Rate Limiter Trusts X-Forwarded-For Without Proxy Validation

- **Location:** `backend/app/auth/rate_limiter.py`, function `_client_ip`
- **Category:** A04 — Insecure Design
- **Issue:** `_client_ip` reads `X-Forwarded-For` unconditionally from the request headers and uses the leftmost value as the client IP. Any client can spoof this header with an arbitrary IP (e.g., `X-Forwarded-For: 192.168.1.1`) and bypass the 10-failed-attempts-per-IP rate limit entirely, reducing brute-force protection to zero.
- **Impact:** PRD-1 US-102 explicitly requires rate limiting as a hard requirement. An attacker can cycle through arbitrary spoofed IPs and attempt unlimited password guesses against any account. This negates the only brute-force mitigation in the system.
- **Remediation:** Either (a) do not trust `X-Forwarded-For` at all for the v1 single-replica deployment (use `request.client.host` directly — this is the actual connected IP when there is no trusted reverse proxy in front), or (b) use a trusted proxy list from settings (e.g., `trusted_proxies = ["127.0.0.1", "10.0.0.0/8"]`) and only extract the client IP from the header when the connection arrives from a trusted proxy. For the v1 single-replica local/CI deployment, option (a) is simpler and correct: `return request.client.host if request.client else "unknown"`.
- **Reference:** OWASP Testing Guide v4.2 WSTG-SESS-003; [OWASP Cheat Sheet: Denial of Service](https://cheatsheetseries.owasp.org/cheatsheets/Denial_of_Service_Cheat_Sheet.html)

---

### HIGH: authlib==1.5.2 — CRITICAL/HIGH CVEs in Installed Dead Dependency

- **Location:** `backend/pyproject.toml`, `backend/uv.lock`
- **Category:** A06 — Vulnerable and Outdated Components
- **Issue:** `authlib==1.5.2` has 12 open OSV advisories. Key findings:

  | ID | Severity | Summary | Fixed In |
  |----|----------|---------|----------|
  | GHSA-wvwj-cvrp-7pv5 | CRITICAL (CVSS 9.1) | JWS JWK Header Injection — signature verification bypass when `key=None` | 1.6.9 |
  | GHSA-9ggr-2464-2j32 | HIGH (CVSS 7.5) | JWS/JWT accepts unknown `crit` headers → authz bypass | 1.6.4 |
  | GHSA-pq5p-34cr-23v9 | HIGH (CVSS 7.5) | DoS via oversized JOSE segments | 1.6.5 |
  | GHSA-7432-952r-cw78 | HIGH (CVSS 8.2) | JWE RSA1_5 Bleichenbacher padding oracle | 1.6.9 |
  | GHSA-m344-f55w-2m6j | HIGH (CVSS 8.1) | OIDC hash binding fail-open | 1.6.9 |

- **Current exposure:** authlib is NOT imported anywhere in the application code — it is a declared dependency that is installed but unused. The vulnerabilities are not exercised in the current PR. However, the library is installed in every deployment environment, and any future code that imports authlib (especially for the ID token verification fix recommended above) will immediately exercise these CVEs unless the package is updated first.
- **Remediation:** Either (a) remove `authlib` from `pyproject.toml` entirely if it is genuinely unused (preferred — eliminates the attack surface), or (b) update to `authlib==1.7.0` (latest, fixes all 12 advisories including all CRITICAL/HIGH CVEs fixed at ≥1.6.9). If authlib is retained for the ID token fix, option (b) is required.
- **Reference:** OSV.dev GHSA-wvwj-cvrp-7pv5, GHSA-9ggr-2464-2j32, GHSA-7432-952r-cw78, GHSA-m344-f55w-2m6j, GHSA-pq5p-34cr-23v9

---

### MEDIUM: SECRET_KEY Default Is Cryptographically Weak — No Startup Validation

- **Location:** `backend/app/config.py`, `Settings.secret_key`
- **Category:** A02 — Cryptographic Failures; A05 — Security Misconfiguration
- **Issue:** `secret_key` defaults to `"dev-secret-key-change-in-production"`. This value is used by itsdangerous to sign OAuth state parameters. If a production deployment omits this environment variable (misconfiguration), the state signing key is publicly known, allowing an attacker to forge valid OAuth state tokens and bypass the CSRF protection on the OAuth callback. Unlike `database_url` (which raises on missing value), `secret_key` silently accepts the insecure default.
- **Impact:** If deployed with the default key, the OAuth CSRF protection (nonce + signed state) is broken. An attacker can forge the `state` parameter for any nonce they control, enabling OAuth CSRF account takeover.
- **Remediation:** Add a startup validator: `@field_validator("secret_key") def must_not_be_default(cls, v): if v == "dev-secret-key-change-in-production" and os.getenv("ENV", "dev") == "production": raise ValueError("secret_key must be set to a secure random value in production")`. For simpler v1: add a minimum-length validator (e.g., 32 chars) that forces a real value to be set regardless of environment. The `.env.example` hint is insufficient — the framework must enforce this.
- **Reference:** OWASP A05; [OWASP Cryptographic Failures Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html)

---

### LOW: SMTP Connection Uses Cleartext (start_tls=False)

- **Location:** `backend/app/auth/email.py`, `send_password_reset_email`
- **Category:** A02 — Cryptographic Failures
- **Issue:** `aiosmtplib.send(..., start_tls=False)` sends password reset emails over an unencrypted SMTP connection. In dev/CI (mailhog on localhost), this is harmless. In production, if the SMTP server supports STARTTLS (all real transactional email providers do), this transmits reset links in cleartext.
- **Impact:** Network-adjacent attacker can intercept password reset links in transit if production SMTP is not TLS-enforced at the network layer.
- **Remediation:** Add a `smtp_tls: bool = False` setting to `Settings`. Default `False` for dev/CI compatibility (mailhog). Set `True` in production env. Pass `start_tls=settings.smtp_tls` to `aiosmtplib.send()`. Alternatively, move to a transactional email provider SDK (SendGrid, Postmark) that enforces TLS by default.
- **Reference:** OWASP A02; [OWASP Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html)

---

### INFO: CSRF Skip on No-Cookie Requests Affects /password-reset/request

- **Location:** `backend/app/auth/csrf.py`, lines ~195-200
- **Category:** A05 — Security Misconfiguration (design decision, not a defect)
- **Issue:** When no `csrf_token` cookie is present, the CSRF middleware skips the check entirely. A request from a browser that has never visited the site (no session cookie) to `/password-reset/request` with a POST body will pass CSRF without a token. The test `test_reset_request_opaque_for_nonexistent_email` confirms this passes with status 200 from an unauthenticated client.
- **Impact:** A CSRF attack from a third-party page against a victim who has no session on the site would trigger a password reset email to the attacker-chosen email. Since the response is always 200 (anti-enumeration), no information is leaked, and no account takeover occurs — the attack is a nuisance (spam reset emails) rather than a security compromise. The endpoint is correctly anti-enumeration.
- **Assessment:** This is a scope-appropriate design decision for the CSRF-skip-on-no-session pattern. The risk is low (spam, not account compromise). Documented here for the record. No action required before merge if engineering accepts the reasoning.

---

## Semgrep SAST

**0 findings** across 2,852 rules on 13 files (10 auth modules + 3 model files). Regression-free from the PR-1 baseline.

Files scanned: `csrf.py`, `dependencies.py`, `email.py`, `oauth.py`, `password.py`, `rate_limiter.py`, `router.py`, `schemas.py`, `session.py`, `tokens.py`, `models/user.py`, `models/session.py`, `models/password_reset_token.py`.

Semgrep platform historical findings (SAST + SCA): 0 open findings for `iceman12276/shared-todos`.

Custom rule `jwt-signature-not-verified` fired on `oauth.py:_decode_id_token_payload` — escalated to CRITICAL finding above.

---

## Dependencies (Changed)

New direct dependencies introduced:

| Package | Version | Status |
|---------|---------|--------|
| aiosmtplib | 3.0.2 | CLEAN |
| argon2-cffi | 23.1.0 | CLEAN |
| argon2-cffi-bindings | 25.1.0 | CLEAN |
| **authlib** | **1.5.2** | **12 CVEs (1 CRITICAL, 4 HIGH) — see finding above** |
| cffi | 2.0.0 | CLEAN |
| email-validator | 2.2.0 | CLEAN |
| httpx | 0.28.1 | CLEAN |
| itsdangerous | 2.2.0 | CLEAN |
| slowapi | 0.1.9 | CLEAN |

Dev additions:

| Package | Version | Status |
|---------|---------|--------|
| anyio | 4.9.0 (from 4.13.0) | CLEAN (downgrade acceptable for dev fixture) |
| respx | 0.21.1 | CLEAN |

`cryptography` is a transitive dependency of authlib. Version not queried; will be resolved when authlib is updated.

Carried forward from PR-1 (not blocking):
- `pytest==8.3.5` GHSA-6w46-j5rx-g56g (LOW) — dev-only, ephemeral CI runners
- `mailhog/mailhog:latest` floating tag (INFO) — CI-only dev infra

---

## Positive Security Observations

The following were explicitly verified and implement their PRD requirements correctly:

- **argon2id parameters** — `time_cost=3, memory_cost=65536, parallelism=1` match OWASP recommendations
- **Timing equalization** — `_DUMMY_HASH` precomputed at module load; `verify_password(input, _DUMMY_HASH)` called on user-not-found path ensuring identical argon2 timing to wrong-password path
- **Password reset tokens** — `secrets.token_urlsafe(32)` (≥32 bytes entropy), stored as SHA-256 hash via `hmac.compare_digest`, single-use (`used_at` timestamp set), 1h TTL enforced DB-side
- **Session invalidation** — `invalidate_session` deletes DB row on logout; `invalidate_all_user_sessions` wipes all sessions on password reset (US-107 hard requirement met)
- **Session tokens** — `secrets.token_urlsafe(32)` stored in DB, looked up with expiry check
- **Cookie flags** — httpOnly=True, SameSite=lax, `secure=settings.cookie_secure` (dev=False, prod=True)
- **Anti-enumeration** — register duplicate email returns 201 with matching Set-Cookie headers (session + csrf_token); login and password-reset responses are identical regardless of email existence
- **CSRF double-submit** — `secrets.compare_digest` for timing-safe comparison; logout requires CSRF header (CSRF-forced-logout is a real attack, correctly not exempt)
- **OAuth CSRF** — itsdangerous-signed state + nonce bound to httpOnly cookie; `secrets.compare_digest` for nonce validation

---

## Not in Scope

- Frontend authentication UI (not yet implemented — PR-6+)
- Google OAuth E2E against a real Google account (stub-only in PR-2 tests; full E2E at release boundary)
- `slowapi` integration (imported in pyproject.toml but not wired to any endpoint in this PR — if unused, can be removed like authlib)
- Full white-box pentest of the assembled auth stack — validation-lead calls shannon-pentest at phase completion

---

## Verdict Rubric

**FAIL** — two merge-blocking findings:

1. **CRITICAL (must fix before merge):** OAuth ID token decoded without signature verification (`oauth.py:_decode_id_token_payload`). Fix: verify against Google JWKS.
2. **HIGH (must fix before merge):** Rate limiter trusts `X-Forwarded-For` unconditionally (`rate_limiter.py:_client_ip`). Fix: use `request.client.host` for v1, or trusted-proxy list.

Additionally:
- **HIGH (dead dep, must fix before merge or explicitly justified):** authlib==1.5.2 CRITICAL/HIGH CVEs. Fix: remove authlib if unused, or update to 1.7.0.
- **MEDIUM (fix or justify before merge):** `secret_key` no startup validation.
- **LOW (follow-up acceptable):** SMTP cleartext.
- **INFO (design decision, no action required):** CSRF skip on no-cookie requests.
