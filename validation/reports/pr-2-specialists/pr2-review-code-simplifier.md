# PR #2 Code Simplification — 8 real wins

## Biggest wins (ranked)

### 1. DELETE `verify_token_hash` + 3 unit tests (dead code)
`app/auth/tokens.py:16-18` only used by `tests/unit/test_tokens.py`. Router does SQL-layer comparison via `token_hash == hash_token(token)` directly. `hmac` import goes away.

### 2. DELETE `UserOut` Pydantic model (dead code)
`app/auth/schemas.py:18-23` — LSP confirms zero references outside its own definition. Router uses hand-rolled `_user_out(user) -> dict` instead. Delete OR replace `_user_out` with it.

### 3. Share `_set_auth_cookies` with OAuth (bug fix, not just simplification)
`router.py:37-55` sets session+csrf. `oauth.py:92-100` sets only session. OAuth users CAN'T make CSRF-protected writes (csrf cookie never set) until re-login. **Hoisting fixes this silent bug** — recommended action in two reviews (code-reviewer C1 + here).

### 4. `dict[str, Any]` replaces 8 `type: ignore[type-arg]` trailers
`router.py` every `-> dict` line (58, 67, 100, 135, 143, 154, 182, 203) carries `# type: ignore[type-arg]`. One `from typing import Any` + `dict[str, Any]` replaces all.

### 5. Extract `_redirect_to_error(error: str) -> Response` in oauth.py
`oauth.py:141-143, 171-173, 181-184, 191-194` — 4 identical 4-line blocks building error redirects. Tiny helper removes duplication.

### 6. Hoist imports + extract `_create_reset_token_for(email)` in test file
`tests/integration/test_password_reset.py:59-66, 101-108, 150-157` — 3 tests re-import same modules + re-do 10-line token creation dance. Hoist + helper removes ~30 lines.

### 7. Delete dead `oauth2/v3/userinfo` branch in test mock
`tests/integration/test_oauth.py:50-51` — userinfo URL mocked but production code doesn't hit it (dropped in `ae04fb6`). Dead test scaffolding.

### 8. Single-transaction `password_reset_complete` (CORRECTNESS bonus)
`router.py:219-229` — 3 commits for one logical op. Crash between 1 and 2 permanently locks user out. Combine into single transaction [overlaps code-reviewer H1]. Correctness improvement + simplification.

## Minor
- #9. Inline `make_dummy_hash()` — it's a trivial getter returning `_DUMMY_HASH`. Export as module constant.
- #10. Module-level `_SIGNER = URLSafeSerializer(...)` instead of `_signer()` factory on every call.
- #11. `except (ValueError, Exception):` → `except Exception:` OR narrow to `(ValueError, json.JSONDecodeError, binascii.Error)` [overlaps code-reviewer C3, silent-failure C2].

## VERIFIED justified — do NOT extract
- Anti-enumeration cookie duplication in register (router.py:75 vs 90)
- Explicit `secrets.compare_digest` (csrf.py:59, oauth.py:154)
- Four separate auth modules (csrf/oauth/password/tokens)
- `_client_ip` trusts XFF — security concern, not simplification (flagged elsewhere)

## Verdict
Diff is NOT at KISS-optimum. Real simplifications, not nitpicks. Anti-enumeration + security boilerplate correctly preserved. Test infrastructure is weakest area — duplicated imports + dead mock branch.
