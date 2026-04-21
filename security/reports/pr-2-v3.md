# Security Review: PR #2 v3

**Verdict:** PASS
**Reviewer:** security-reviewer
**Date:** 2026-04-21
**PR Branch:** feat/pr2-auth @ 057a677
**v2 Head:** 9c4faf0c (v2 verdict: PASS, 0 findings)
**v3 Delta commits:** edf6a61, a039617, d7a1e4a, 057a677
**Scope:** Files changed between v2 head (9c4faf0) and v3 head (057a677):
- `backend/app/auth/oauth.py` — missing-claim log added
- `backend/app/auth/router.py` — register body-shape harmonized
- `backend/alembic/versions/aaad963c469e_*.py` — downgrade safety fix
- `backend/semgrep-rules/no-exception-in-except-tuple.yml` — new custom rule
- `backend/tests/integration/test_v3_hardening.py` — CRIT-1/2/3 tests
- `backend/tests/integration/test_register_response_body_shape_identical_anti_enum.py`
- `backend/pyproject.toml` / `backend/uv.lock` — google-auth exact pin
- `.github/workflows/ci.yml` — Semgrep rule wired to security-gate

---

## Summary

v3 is a narrow fix-forward that closes all 5 v2 residual Actionable items (3 CRIT test gaps, 1 IMPORTANT dep pin, 2 LOW). All three targeted checks from the briefing pass. The Semgrep custom rule (`no-exception-in-except-tuple`) is functional: it fires correctly on all three anti-pattern variants (trailing, leading, middle Exception in tuple) and does NOT fire on the two legitimate patterns in the current codebase — bare `except ValueError as exc` at `oauth.py:185` and bare `except Exception as exc` (SMTP swallow) at `router.py:165`. The SMTP path is a bare (non-tuple) `except Exception` which is correctly outside the rule's scope; no `nosemgrep` marker is needed.

The `google-auth` dep is now exactly pinned at `==2.49.2` in `pyproject.toml` (v2-IMPORTANT-1 resolved). The register response body-shape is harmonized: both duplicate and new-email paths return `{"user": ..., "message": ...}` with the same key set (v2-LOW-1 resolved). The `oauth.py:205-209` missing-claim path now logs a warning before redirecting (v2-LOW-2 resolved). The downgrade migration for `aaad963c469e` clears sessions before restoring the `NOT NULL token` column.

Semgrep SAST: **0 findings** across 2,852 rules on 5 v3-changed Python files. Regression-free from v2 baseline.

---

## Check 1: Semgrep Custom Rule Meta-Test

### Rule fires on anti-pattern fixture — CONFIRMED

Ran `semgrep_scan_with_custom_rule` against a synthetic fixture containing all three anti-pattern forms:

| Variant | Fires? |
|---------|--------|
| `except (ValueError, Exception):` (trailing) | YES — line 4 |
| `except (Exception, ValueError):` (leading) | YES — line 10 |
| `except (ValueError, RuntimeError, Exception, KeyError):` (middle) | YES — line 16 |

**3/3 anti-pattern variants detected. Rule is functional.**

### Rule does NOT fire on legitimate current-tree patterns — CONFIRMED

Ran the custom rule against representative snippets of:
- `oauth.py` — bare `except ValueError as exc` at line 185 (hotfix narrowing): **0 findings**
- `router.py` — bare `except Exception as exc` (SMTP swallow) at line 165: **0 findings**

**Adjudication — SMTP `except Exception` does not need a `nosemgrep` marker:**
The rule pattern matches only tuples: `except (A, ..., Exception)` and `except (Exception, ...)`. A bare `except Exception as exc` without parentheses is structurally different and outside the rule's match scope. The SMTP swallow is intentional, logged, and documented in the commit body as "best-effort: don't leak send failures." No marker required.

### CI wire — CONFIRMED

`d7a1e4a` adds `--config backend/semgrep-rules/` to the CI `security-gate` Semgrep invocation. The custom rule will run as part of every future PR's deterministic gate.

---

## Check 2: google-auth Exact Pin

- `backend/pyproject.toml:12` — `"google-auth==2.49.2"` — exact pin, no `>=` / `~=` / `<` range operators.
- `backend/uv.lock` — `name = "google-auth"` / `version = "2.49.2"` — lockfile resolves to same version.

**v2-IMPORTANT-1 resolved. Dep-sync convention restored.**

---

## Check 3: Semgrep SAST Regression Pass (v3 Delta)

**0 findings** across 2,852 rules on 5 v3-changed Python files:
- `backend/app/auth/oauth.py`
- `backend/app/auth/router.py`
- `backend/tests/integration/test_v3_hardening.py`
- `backend/tests/integration/test_register_response_body_shape_identical_anti_enum.py`
- `backend/alembic/versions/aaad963c469e_rename_sessions_token_to_token_hash.py`

Regression-free from v2 baseline (0 findings).

---

## v2 Residual Verification

### v2-CRIT-1: Google-only password-reset anti-enum — RESOLVED

`test_v3_hardening.py:27-67` — seeds a `User(password_hash=None, google_sub=...)`, POSTs to `/password-reset/request`, asserts HTTP 200 + `"message"` key in response body, and asserts no `PasswordResetToken` row was created. This locks the `router.py:148` branch — a refactor to that branch that leaked account type or created a token would fail this test.

### v2-CRIT-2: Multi-device session invalidation — RESOLVED

`test_v3_hardening.py:76-156` — two separate `AsyncClient` instances each acquire independent sessions (device A via register, device B via login). Device A completes a password reset. Both `session_a` and `session_b` are then asserted to return 401 on `/auth/session`. US-107 multi-device guarantee is now locked at the test level.

### v2-CRIT-3: Narrowed-except invariant — RESOLVED

`test_v3_hardening.py:165-233` — injects a `_runtime_error_verifier` that raises `RuntimeError`, uses `ASGITransport(raise_app_exceptions=False)` so the unhandled exception becomes an HTTP 500 response, and asserts `r.status_code == 500` (not 302). Future re-broadening of the `except` to catch `Exception` would swallow the `RuntimeError` and return a 302 redirect to `?error=oauth_failed` — causing this assertion to fail.

### v2-IMPORTANT-1: google-auth floating pin — RESOLVED

See Check 2 above. `==2.49.2` exact pin in both `pyproject.toml` and `uv.lock`.

### v2-LOW-1: Register body-shape parity — RESOLVED

`router.py:58` — duplicate path now returns `{"user": None, "message": ...}`.
`router.py:73` — success path returns `{"user": _user_out(user), "message": ...}`.
Both paths share the same key set (`user`, `message`). The integration test at `test_register_response_body_shape_identical_anti_enum.py:51` asserts `dup_keys == new_keys` and verifies both keys are present. A body-parsing attacker can no longer distinguish existing from new email by key-presence. Note: the success path retains `user` value (not `None`) — the fix is key-shape identity, not value identity. This is correct and sufficient: the vulnerability was key-presence leakage, not value disclosure of a newly created user object.

### v2-LOW-2: OAuth missing-claim silent redirect — RESOLVED

`oauth.py:205-211` — the `if not google_sub or not email` branch now calls `_log.warning("oauth: id_token missing required claim sub=%r email=%r, rejecting", ...)` before the redirect. Consistent with the 17 other logging call sites in the auth package.

---

## Semgrep SAST

**0 findings** across 2,852 rules on 5 v3-delta Python files. Full baseline (2,852 rules) maintained through PR #1, PR #2 v1, v2, and v3. No regressions.

Semgrep platform historical findings (`iceman12276/shared-todos`): 0 open (SAST + SCA). Unchanged.

---

## Dependencies

No new dependencies added in v3. `google-auth==2.49.2` re-pinned (exact), `uv.lock` re-generated. SCA posture unchanged from v2: all deps 0-CVE.

---

## Carried Forward (unchanged from v2)

- `pytest==8.3.5` GHSA-6w46-j5rx-g56g (LOW) — dev-only, ephemeral CI runners
- `mailhog/mailhog:latest` floating tag (INFO) — CI-only dev infrastructure
- SMTP cleartext `start_tls=False` (LOW) — acceptable for dev/CI mailhog; prod requires `SMTP_TLS=true` env override

---

## Not in Scope

- v1 / v2 verified findings — not re-examined (v2 closed all, v3 did not touch those surfaces)
- Full white-box pentest — validation-lead calls shannon-pentest at phase/release completion
- silent-failure-hunter N1-N5 carry-forwards — deferred to PR-3 per v2 synthesis
