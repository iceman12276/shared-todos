# Validation Report: PR #2 — Authentication Backend

**Verdict:** REQUEST_CHANGES
**Date:** 2026-04-21
**Target:** https://github.com/iceman12276/shared-todos/pull/2 (branch `feat/pr2-auth` @ `09fe902`)
**PRD:** `docs/planning/prd-1-authentication.md`
**Streams run:** 7 of 8 (qa-engineer deferred — see Process Deviation below)

---

## Summary

PR #2 implements the authentication backend for the shared-todos app: register, login, logout, Google OAuth callback, password reset via emailed single-use tokens, CSRF double-submit middleware, and in-memory rate limiting. The foundational cryptographic choices are sound — argon2id parameters match OWASP, password reset tokens use `secrets.token_urlsafe(32)` stored as SHA-256 hashes with `hmac.compare_digest`, session cookie flags (httpOnly, SameSite=lax, secure=env-gated) are correct, anti-enumeration response symmetry is exceptionally well-tested, and `_DUMMY_HASH` timing equalization is in place. PR-1's conventions (Base metadata naming convention, type_annotation_map, fail-fast Settings) propagate cleanly into three new ORM models + the auth/ package.

However, the branch carries **4 CRITICAL, 6 HIGH, and 3 MEDIUM** blockers that must be resolved before merge. The most severe are in the OAuth path: the Google ID token is base64-decoded without signature, `iss`, `aud`, or `exp` verification (CRITICAL-1); account auto-linking trusts the `email` claim without consulting `email_verified` (CRITICAL-4); and the OAuth callback never sets the `csrf_token` cookie, leaving every OAuth-authenticated browser with a silent CSRF bypass on every subsequent mutating request (HIGH-5, convergent across three specialists). Compounding these: a dead `authlib==1.5.2` dependency ships 12 CVEs including a CRITICAL JWS signature-bypass (HIGH-10) — it must be removed or upgraded in the **same commit** that lands the OAuth signature fix to avoid an interim state where the attack surface is active. The SYSTEMIC absence of any logging infrastructure in `backend/app/` (CRITICAL-2, silent-failure-hunter) means every error path above has zero audit trail — fixes to the silent-swallow cases are ~meaningless until logging lands first. Finally, `secret_key`, `google_client_id`, `google_client_secret` lack the fail-fast Settings validation that PR-1 established for `database_url` (CRITICAL-3), which is convention-erosion on a trust-root pattern.

Verdict is **REQUEST_CHANGES**. The consolidated 13-item must-fix list maps cleanly onto 8 commit groups (A-H); `scripts/preflight.sh` (Group H) is an opportunistic close-out of the "all green locally, red on CI" retrospective pattern.

---

## Process Deviation — QA Stream Deferred

The 8th stream (qa-engineer — runtime verification, browser-level E2E) did not complete. qa-engineer was dispatched at ~07:30 UTC with a worktree-checkout brief but did not produce an output before the overnight pause. User decision on resume: **close on 7/8 streams**; the verdict is already locked as REQUEST_CHANGES from structural + security signals alone, so runtime findings (if any) **stack additively in a follow-up re-review cycle** after backend-dev's fix push. This is documented for auditability — future validation passes should not take this as precedent for skipping qa-engineer; it is a one-time accommodation driven by the overnight bottleneck.

---

## Convention-Setter Signal — PASS (Baseline Carried Forward)

type-design-analyzer verified that PR-1's three load-bearing conventions propagate cleanly into PR-2:

- **`Base.metadata` naming convention** — migration `e741951e9b5f_*.py` shows deterministic constraint names (`pk_users`, `ix_sessions_token`, `fk_*`, `uq_*`) — Alembic autogenerate will produce stable diffs.
- **`type_annotation_map`** — every model uses `Mapped[UUID]` / `Mapped[datetime]` and inherits the PR-1 mapping (UUID → `Uuid(as_uuid=True)`, datetime → `DateTime(timezone=True)`). Zero naive timestamps. Zero `name=` overrides on constraints.
- **`Settings(extra="forbid")` fail-fast** — PR-2's new settings additions (`secret_key`, `smtp_*`, `google_*`, `rate_limit_*`, `cookie_*`) inherit the PR-1 `extra="forbid"` contract; no drift on this layer.

This is a **strong signal for PR-3/4/5** (lists, sharing, realtime) — backend-dev is not eroding the foundation. The three failures below (`secret_key` / `google_client_id` / `google_client_secret` lacking Pydantic validators) are the *next layer up* — convention on validator strictness, which PR-1 established on `database_url`. They are recorded as CRITICAL-3 on convention-erosion grounds, not foundational instability.

---

## Convergent-Signal Alert — 6 findings, 2-4 streams each

Six of the 13 blockers were independently flagged by multiple streams. Per the validation-synthesis rule, these are consolidated into a single item each, citing all sources. **Convergent signal = high confidence, escalate severity.** Cited finding numbers below match the per-stream reports.

| # | Severity | Finding | Streams citing |
|---|----------|---------|----------------|
| CRITICAL-1 | CRITICAL | OAuth ID token signature + iss/aud/exp not verified | security-reviewer (CRITICAL), code-reviewer (H3), silent-failure-hunter (M1) |
| CRITICAL-4 | CRITICAL | OAuth auto-link without `email_verified` check | code-reviewer (C2), silent-failure-hunter (H4) |
| HIGH-5 | HIGH | OAuth callback does not set `csrf_token` cookie | code-reviewer (C1), silent-failure-hunter (C7-related), code-simplifier (#3 — fix-via-hoist) |
| HIGH-6 | HIGH | `except (ValueError, Exception)` catch-all in `_decode_id_token_payload` | code-reviewer (C3), silent-failure-hunter (C2), code-simplifier (#11) |
| HIGH-7 | HIGH | Rate limiter trusts X-Forwarded-For unconditionally | security-reviewer (HIGH), code-reviewer (H2), silent-failure-hunter (H2) |
| HIGH-8 | HIGH | `password_reset_complete` non-atomic (2 commits → lockout on crash) | code-reviewer (H1), silent-failure-hunter (H5), code-simplifier (#8) |

---

## Adjudication Precedent — Code-Scope vs. Exploitability-Scope

A pattern surfaced during this PR that's worth recording for future rubrics: **silent-failure-hunter flagged CSRF skip-on-no-cookie as a broad code-scope CRITICAL (C7)**; **security-reviewer pinned the exploitability-scope as INFO** (the only endpoint actually reachable unauthenticated with a mutating verb is `/password-reset/request`, which is anti-enumerated and 32-byte-token-bounded on `/complete`). Validation-lead records **both halves**: the code-scope concern is real (pattern could regress if a future endpoint lands unauthenticated + mutating), the exploitability-scope concern is bounded (nuisance spam, not account compromise). Resolution: keep as **INFO in the final list**, but add a code comment at `csrf.py:48-49` explicitly documenting the scope assumption, so a future reader doesn't lift the skip-branch into a new endpoint context.

---

## Engineering-Lead Pre-Open Review — Acknowledged Separately

Engineering-lead's pre-open review of PR #2 caught 4 defects before the PR opened (captured in commits `64d856b`, `ae04fb6`, `e3c7559`, `b98c76d`). The **13 new blockers are additive to, not contradictions of, those pre-open fixes**. Where the new list intersects eng-lead's "do NOT fix" list (X-Forwarded-For was flagged then deferred; authlib was flagged then deferred), the concession framing is explicit: "the following contradict my earlier 'do NOT fix' list on convergent-signal grounds" — protects backend-dev trust and prevents whiplash.

---

## Stream 1 — Runtime (QA Engineer)

**Deferred.** See Process Deviation above. Runtime findings, if any, stack additively in a follow-up re-review cycle.

---

## Stream 2 — Security (Security Reviewer)

**Report:** `security/reports/pr-2.md` (committed at `a6a5e2c`)

**Verdict:** FAIL — 1 CRITICAL, 2 HIGH, 1 MEDIUM, 1 LOW, 1 INFO

Findings:

| Severity | Finding | Location |
|----------|---------|----------|
| CRITICAL | Google OAuth ID token not signature-verified | `oauth.py::_decode_id_token_payload` |
| HIGH | Rate limiter trusts X-Forwarded-For unconditionally | `rate_limiter.py::_client_ip` |
| HIGH | `authlib==1.5.2` — 12 CVEs in dead (unimported) dependency | `pyproject.toml`, `uv.lock` |
| MEDIUM | `secret_key` accepts insecure default, no startup validation | `config.py` |
| LOW | SMTP connection uses cleartext (`start_tls=False`) | `email.py::send_password_reset_email` |
| INFO | CSRF skip on no-cookie requests — scope-appropriate | `csrf.py` |

**Semgrep SAST:** 0 findings across 2,852 rules on 13 files. Custom rule `jwt-signature-not-verified` fired on the CRITICAL finding above. Semgrep platform historical findings for `iceman12276/shared-todos`: 0 open.

**SCA:** `authlib==1.5.2` carries GHSA-wvwj-cvrp-7pv5 (CRITICAL CVSS 9.1, JWS signature bypass when `key=None`) + 4 HIGH advisories. Remediation: **remove OR upgrade to 1.7.0** — must be landed in the SAME commit that implements the OAuth signature fix (Group C below), so the tree never sits in an interim state where the fix relies on a vulnerable library.

---

## Stream 3 — Structural (PR Review Toolkit Specialists)

Six specialists dispatched. Reports in `validation/reports/pr-2-specialists/`.

### code-reviewer — 3 CRITICAL, 4 HIGH, 4 INFO
- **CRITICAL:** OAuth callback missing csrf_token cookie (C1); OAuth email-link without `email_verified` (C2); `except (ValueError, Exception)` catch-all in id_token decode (C3)
- **HIGH:** Non-atomic password_reset_complete (H1); X-Forwarded-For unconditional trust (H2); id_token iss/aud/exp not verified (H3); unbounded `_store` dict in rate limiter (H4)
- **INFO:** logout doesn't clear csrf cookie; `_CSRF_COOKIE` / `_COOKIE_NAME` duplicated; `verify_password(body.password, make_dummy_hash())` return value ignored (wrap in named helper); `_user_out` bypasses Pydantic output contract
- **CLAUDE.md compliance:** PASS on every check

### pr-test-analyzer — 3 CRITICAL gaps, 2 HIGH gaps, 5 MEDIUM
- 66 tests total (PR body claimed 68) — strong on anti-enumeration coverage
- **CRITICAL gaps:** Google-only-account password-reset anti-enum branch untested; login user-not-found timing vs wrong-password timing not asserted (defeats purpose of `_DUMMY_HASH`); password_reset_complete invalidates-ALL-sessions claim tested on single-cookie fixture only (US-107 guarantee untested)
- **HIGH gaps:** rate-limit window-reset + counter-reset-on-success untested; no OPTIONS preflight CSRF bypass test (PR body claimed "OPTIONS bypass")
- **TDD concern:** Commit `64d856b` (CSRF middleware FIRST ADDED) post-dates CSRF tests in commit `4e4b68b` — integration test for "POST without X-CSRF-Token → 403" should have existed before the middleware commit

### silent-failure-hunter — 8 CRITICAL, 6 HIGH, 5 MEDIUM + SYSTEMIC
- **SYSTEMIC:** `grep -r "logger\|logging\|.info(\|.error(\|.warning("` across `backend/app/` → **0 matches**. No logging infrastructure exists. Every error path below has zero audit trail.
- **CRITICAL:** SMTP silent suppress (commit message FALSELY claims "logged server-side" — no logger exists); id_token decode catch-all; token-exchange non-200 collapsed; httpx/aiosmtplib network errors unwrapped; `google_client_id`/`google_client_secret` default-empty ships broken silently; `secret_key` dev default no prod guard; CSRF middleware silent-bypass when cookie missing; zero audit trail for failed-login/lockout/successful-login/password-reset/OAuth-link
- **HIGH/MEDIUM:** argon2 `InvalidHashError` bubbles as 500; XFF trust; Google-only vs wrong-email indistinguishable; `email_verified` unchecked; reset_complete partial-failure; logout silent no-op; id_token signature deferred with runtime silence; b64 padding unconditional; register two-commit partial state; unbounded `_store`; wrong-password against existing-user not logged

### type-design-analyzer — 2 MEDIUM, 5 LOW — convention-setter PASS
- **MEDIUM:** `Session.token` stored RAW (vs sibling `PasswordResetToken.token_hash` correctly SHA-256-hashed — glaring asymmetry within same PR); `User` missing CheckConstraint on `password_hash IS NOT NULL OR google_sub IS NOT NULL` (identity invariant not enforced at DB)
- **LOW:** `UserOut.id: str` should be `UUID`; SecretStr for plaintext fields; `Session` lacks `relationship(User, lazy="raise")`; PasswordResetToken partial unique index; `secret_key` dev default; `rate_limit_login_attempts` missing `le=` bound
- **Convention check: PASS** — PR-1 Base + type_annotation_map + fail-fast Settings propagate cleanly

### comment-analyzer — 5 HIGH (bug-encoding), 6 missing WHY, 4 dead WHAT
- **HIGH (bug-encoding — fix first):** csrf.py:7-11 docstring claims `/api/v1/auth/oauth/*` exempt but code only exempts login/register (security-bug-encoded comment); csrf.py:40-41 stale comment about OAuth POST protection with no corresponding code; oauth.py:1-11 module docstring overstates state integrity (signing alone ≠ CSRF); oauth.py:78-83 `_decode_id_token_payload` docstring says "dev/test only path" but called unconditionally in production; rate_limiter.py:18 describes a dict shape the code doesn't have (leftover from fixed-window)
- **Missing WHY:** dependencies.py `require_auth` contract; router.py `_set_auth_cookies` httponly=False rationale; register anti-enum user-facing quirk; password-reset Google-only branch intent; `create_session` security-critical docstring; OAuth account-linking threat model
- **Exemplars to preserve:** password.py:9-11 dummy hash rationale, router.py:106-108 login dummy-hash timing, router.py:72-75 register Set-Cookie anti-enum, oauth.py:44 `_NONCE_TTL` magic-number justification

### code-simplifier — 8 real wins
- **Wins:** DELETE `verify_token_hash` + 3 unit tests (dead code); DELETE `UserOut` Pydantic model (dead code — router uses `_user_out` dict); HOIST `_set_auth_cookies` to shared module (fixes HIGH-5); `dict[str, Any]` replaces 8 `# type: ignore[type-arg]` trailers in router.py; extract `_redirect_to_error` in oauth.py (4 identical blocks); test file import hoisting + `_create_reset_token_for` helper (-30 LOC); delete dead `oauth2/v3/userinfo` branch in test mock; single-transaction `password_reset_complete` (overlaps HIGH-8)

---

## Consolidated Must-Fix List (13 blockers)

### CRITICAL (4)
1. **OAuth ID token signature + iss/aud/exp verification** (`oauth.py::_decode_id_token_payload`) — verify RS256 against Google JWKS; check `iss`, `aud`, `exp`. Use `google-auth` OR `authlib==1.7.0` (drop 1.5.2). [Convergent: security, code-reviewer H3, silent-failure M1]
2. **Logging infrastructure** (`app/logging_config.py` new module) — configure root logger at startup, instrument every auth event (register, login, logout, password reset, OAuth link, lockout, rate-limit, SMTP send). Must land **before** silent-swallow fixes (Groups D/E) for those fixes to be meaningful. [silent-failure-hunter SYSTEMIC + C1/C3/C4/C8]
3. **Fail-fast Settings parity** (`config.py`) — Pydantic `model_validator` rejecting empty/default values for `secret_key`, `google_client_id`, `google_client_secret` when `cookie_secure=True` (i.e., prod context). Restores PR-1 convention established for `database_url`. [silent-failure-hunter C5/C6, security MEDIUM]
4. **OAuth auto-link requires `email_verified` is True** (`oauth.py:184-197`) — reject the auto-link path if `payload.get("email_verified") is not True`. Google Workspace custom-domain attack vector. [Convergent: code-reviewer C2, silent-failure H4]

### HIGH (6)
5. **OAuth callback sets `csrf_token` cookie** (`oauth.py:210`) — hoist `_set_auth_cookies` from `router.py:37-55` to shared module (e.g., `app/auth/cookies.py`); call from OAuth success path. Add test `test_oauth_callback_sets_csrf_cookie`. [Convergent: code-reviewer C1, silent-failure C7-adjacent, code-simplifier #3]
6. **Narrow `except (ValueError, Exception)`** (`oauth.py:465`) — replace with `except (ValueError, json.JSONDecodeError, binascii.Error)` and log the failure with structured context. [Convergent: code-reviewer C3, silent-failure C2, code-simplifier #11]
7. **X-Forwarded-For: drop unconditional trust** (`rate_limiter.py::_client_ip`) — for v1 single-replica, use `request.client.host`. Add `trust_proxy: bool = False` to Settings (fail-closed default). Add integration test. [Convergent: security HIGH, code-reviewer H2, silent-failure H2]
8. **Single-transaction `password_reset_complete`** (`router.py:218-230`) — hash outside transaction; single atomic commit for burn-token + update-password + invalidate-all-sessions. Crash between current commits 1 and 2 permanently locks the user out. [Convergent: code-reviewer H1, silent-failure H5, code-simplifier #8]
9. **`Session.token` stored hashed** (`models/session.py:15`) — parity with sibling `PasswordResetToken.token_hash`. Rename column to `token_hash`, hash via `app/auth/tokens.py::hash_token` in `create_session`, compare via `hmac.compare_digest` in `get_session_user`. PR-5 (realtime WS auth) inherits this if not fixed now. [type-design MEDIUM-1]
10. **`authlib==1.5.2` — remove OR upgrade to 1.7.0** — MUST land in the SAME commit as Finding #1 (avoid interim state where OAuth fix relies on a vulnerable library). If authlib is genuinely unused after fix (i.e., we use `google-auth` instead), remove from `pyproject.toml` entirely. [security HIGH]

### MEDIUM (3)
11. **`User` CheckConstraint** (`models/user.py`) — add `__table_args__ = (sa.CheckConstraint("password_hash IS NOT NULL OR google_sub IS NOT NULL", name="at_least_one_auth_method"),)`. Naming convention produces `ck_users_at_least_one_auth_method`. Prevents ghost users from OAuth-linking regressions. [type-design MEDIUM-2]
12. **`_DUMMY_HASH` timing invariant test** — monkeypatch-counter or ratio-timing assertion on `make_dummy_hash()` calls in `test_login_nonexistent_email_same_as_wrong_password`. Refactor removing the dummy-hash call would silently pass the current test. [pr-test-analyzer CRIT-2]
13. **Comment accuracy fixes** — 5 bug-encoding comments flagged by comment-analyzer items 1-5 (csrf.py:7-11 docstring, csrf.py:40-41 stale comment, oauth.py:1-11 module docstring, oauth.py:78-83 `_decode_id_token_payload` docstring "dev/test only", rate_limiter.py:18 data-structure description).

---

## Accepted / Carried Forward

### Accepted false positive (carried from PR-1 v3)
- **`_engine` underscore import in `tests/conftest.py`** — precedent set in PR-1 v3 PASS review: bounded-consumer pattern, rename-safety covered by mypy `--strict` + real-Postgres integration test. PR-2 does not extend the pattern; no new consumers. No action required.

### INFO (recorded, not blocking)
- **CSRF skip on no-cookie requests** — `csrf.py:48-49`. Code-scope concern real, exploitability-scope bounded (only unauthenticated + mutating endpoint is `/password-reset/request`, which is anti-enumerated). Recommendation: add an in-code comment documenting the scope assumption so a future reader doesn't lift the skip-branch into a new endpoint context. [Adjudicated: silent-failure-hunter C7 broad, security-reviewer INFO narrow]
- **SMTP cleartext (`start_tls=False`)** — acceptable for dev (mailhog) + CI. Add `smtp_tls: bool = False` setting, wire to `aiosmtplib.send()`, set `True` via env in prod. [security LOW]
- **`mailhog:latest` floating tag** — CI-only dev infrastructure, carried forward from PR-1 baseline. Not blocking.
- **`pytest==8.3.5` GHSA-6w46-j5rx-g56g** — dev-only, ephemeral CI runners. Carried forward from PR-1 baseline.

---

## Required Actions — Suggested Commit Grouping (A-H)

Backend-dev receives this via engineering-lead's remediation brief.

- **Group A — Logging infrastructure** (CRITICAL-2). `app/logging_config.py` new; `main.py` wires root logger at startup. Foundational for Groups D/E.
- **Group B — Fail-fast Settings** (CRITICAL-3). Pydantic `model_validator` on `secret_key`, `google_client_id`, `google_client_secret`.
- **Group C — OAuth signature + iss/aud/exp + email_verified + authlib-drop** (CRITICAL-1, CRITICAL-4, HIGH-10). **Single commit, single `pyproject.toml` touch** — replaces `authlib==1.5.2` with `google-auth` (or `authlib==1.7.0`) in one atomic move.
- **Group D — CSRF cookie hoist + except narrow** (HIGH-5, HIGH-6). Extract `_set_auth_cookies` to shared module; narrow catch-all with logging (now that Group A has landed).
- **Group E — XFF + single-transaction reset + Session.token hash** (HIGH-7, HIGH-8, HIGH-9). Three behavior changes; grouped by blast radius (all touch request/session handling).
- **Group F — User CheckConstraint + _DUMMY_HASH test + CSRF-scope INFO comment** (MEDIUM-11, MEDIUM-12, INFO). Includes new alembic revision for the CheckConstraint.
- **Group G (optional) — Comment-analyzer docstring fixes** (MEDIUM-13). 5 bug-encoding comment corrections.
- **Group H — `scripts/preflight.sh` + CLAUDE.md Commands update**. Opportunistic Phase 9 retrospective close-out. Script wraps `uv run ruff check . && uv run ruff format --check . && uv run mypy --strict . && uv run pytest`. Neutralizes 2-of-3 "all green locally, red on CI" patterns observed this session.

---

## Next Steps

1. Orchestrator posts the review body via `gh pr comment 2 --body-file /tmp/pr2-review-body.md`.
2. Orchestrator applies labels via `gh api -X POST repos/iceman12276/shared-todos/issues/2/labels` — remove `claude-validating`, add `claude-validated:v1` + `claude-validated:changes-requested`.
3. Engineering-lead fires backend-dev brief with the A-H commit grouping.
4. On backend-dev's fix push + CI green, re-review cycle: run qa-engineer (deferred this pass) + re-validate specialists on the diff. Any net-new findings stack additively.
5. If all 13 blockers are resolved + qa-engineer clean → PASS, label flips to `claude-validated:pass`.
