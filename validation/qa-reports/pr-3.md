# QA Runtime Validation Report: PR #3

**Date:** 2026-04-21
**QA Engineer:** qa-engineer
**Branch:** `feat/pr3-sharing @ ead22cc`
**Worktree used:** `/home/isaac/Desktop/dev/shared-todos-pr3`
**Bug-repro worktree:** N/A — no bugs found

---

## Verdict: PASS

No bugs found. All runtime checks pass. No regression in PR-2 auth layer.

---

## Environment

- Python 3.12.11 / pytest 8.3.5 / uvicorn
- Real Postgres (docker compose, `shared-todos-pr3-postgres-1`)
- Real mailhog (docker compose, `shared-todos-pr3-mailhog-1`)
- Migration at head: `4df1779548df` (PR-3 migration — List, Item, Share tables)
- No mocks in test suite (ASGITransport with real app, real DB)

---

## Full Test Suite Results

**205/205 tests pass** (author-claimed count confirmed).

```
205 passed in 34.23s
```

| File | Tests | Result |
|------|-------|--------|
| `integration/test_auth_register_login.py` | 12 | PASS |
| `integration/test_authz_dependency.py` | 6 | PASS |
| `integration/test_csrf.py` | 9 | PASS |
| `integration/test_items.py` | 12 | PASS |
| `integration/test_lists.py` | 14 | PASS |
| `integration/test_logging.py` | 3 | PASS |
| `integration/test_oauth.py` | 8 | PASS |
| `integration/test_oq1_matrix.py` | 21 | PASS |
| `integration/test_password_reset.py` | 6 | PASS |
| `integration/test_rate_limit.py` | 1 | PASS |
| `integration/test_register_response_body_shape_identical_anti_enum.py` | 1 | PASS |
| `integration/test_session_token_hash.py` | 2 | PASS |
| `integration/test_shares.py` | 17 | PASS |
| `integration/test_user_check_constraint.py` | 3 | PASS |
| `integration/test_v3_hardening.py` | 3 | PASS |
| `test_alembic_boots.py` | 1 | PASS |
| `test_app_boots.py` | 2 | PASS |
| `unit/test_authz.py` | 11 | PASS |
| `unit/test_config.py` | 6 | PASS |
| `unit/test_cookies.py` | 3 | PASS |
| `unit/test_logging_config.py` | 3 | PASS |
| `unit/test_models.py` | 15 | PASS |
| `unit/test_models_sharing.py` | 13 | PASS |
| `unit/test_password.py` | 5 | PASS |
| `unit/test_rate_limiter.py` | 4 | PASS |
| `unit/test_session_service.py` | 6 | PASS |
| `unit/test_timing_invariant.py` | 1 | PASS |
| `unit/test_tokens.py` | 6 | PASS |

---

## OQ-1 Stranger-404 Matrix (In-Process Suite)

All 11 parametrized cells of `test_stranger_404_matrix` pass against real Postgres via ASGITransport:

| Cell | HTTP Verb | Resource | Status |
|------|-----------|----------|--------|
| `list×GET` | GET | `/lists/{id}` | PASS (404) |
| `list×PATCH` | PATCH | `/lists/{id}` | PASS (404) |
| `list×DELETE` | DELETE | `/lists/{id}` | PASS (404) |
| `items×POST` | POST | `/lists/{id}/items` | PASS (404) |
| `items×GET` | GET | `/lists/{id}/items` | PASS (404) |
| `item×PATCH` | PATCH | `/lists/{id}/items/{item_id}` | PASS (404) |
| `item×DELETE` | DELETE | `/lists/{id}/items/{item_id}` | PASS (404) |
| `shares×POST` | POST | `/lists/{id}/shares` | PASS (404) |
| `shares×GET` | GET | `/lists/{id}/shares` | PASS (404) |
| `share×PATCH` | PATCH | `/lists/{id}/shares/{user_id}` | PASS (404) |
| `share×DELETE` | DELETE | `/lists/{id}/shares/{user_id}` | PASS (404) |

Zero 403s observed. Anti-enumeration corollary test (`test_anti_enum_list_404_body_identical`) also passes.

---

## OQ-1 Wire-Level Verification (Real uvicorn + Real HTTP)

Booted uvicorn on port 8001 (`uv run uvicorn app.main:app --port 8001`). Made real HTTP requests via curl against the live server with real Postgres.

**Setup:**
- User A (owner) registered: `qa_wire_owner@example.com`
- User B (stranger) registered: `qa_wire_stranger@example.com`
- Owner created list: `2574a426-b21e-479e-86c8-83222328ba60`
- Stranger authenticated (CSRF token captured from Set-Cookie header)

**Stranger 404 matrix at wire level — all 11 cells:**

| Cell | Method | Endpoint | Wire Status |
|------|--------|----------|-------------|
| `list×GET` | GET | `/api/v1/lists/{id}` | 404 PASS |
| `list×PATCH` | PATCH | `/api/v1/lists/{id}` | 404 PASS |
| `list×DELETE` | DELETE | `/api/v1/lists/{id}` | 404 PASS |
| `items×POST` | POST | `/api/v1/lists/{id}/items` | 404 PASS |
| `items×GET` | GET | `/api/v1/lists/{id}/items` | 404 PASS |
| `item×PATCH` | PATCH | `/api/v1/lists/{id}/items/{item_id}` | 404 PASS |
| `item×DELETE` | DELETE | `/api/v1/lists/{id}/items/{item_id}` | 404 PASS |
| `shares×POST` | POST | `/api/v1/lists/{id}/shares` | 404 PASS |
| `shares×GET` | GET | `/api/v1/lists/{id}/shares` | 404 PASS |
| `share×PATCH` | PATCH | `/api/v1/lists/{id}/shares/{user_id}` | 404 PASS |
| `share×DELETE` | DELETE | `/api/v1/lists/{id}/shares/{user_id}` | 404 PASS |

**Result: ALL PASS — OQ-1 holds at the wire level, not just in-process.**

---

## Byte-Identicality Result (Wire Level)

Stranger hits owner's real list vs. a nonexistent ghost UUID — both via real HTTP against live uvicorn.

| Request | Status | Raw body |
|---------|--------|----------|
| GET `/api/v1/lists/2574a426-b21e-479e-86c8-83222328ba60` (stranger) | 404 | `{"detail":"Not found"}` |
| GET `/api/v1/lists/00000000-0000-0000-0000-000000000099` (ghost) | 404 | `{"detail":"Not found"}` |

**Bodies are byte-identical at the wire.** An attacker comparing response bodies gets zero signal to distinguish "exists but you can't see it" from "doesn't exist."

---

## PR-2 Regression Results

`test_csrf.py` and `test_session_token_hash.py` run explicitly against PR-3 head:

```
11 passed in 1.48s
```

- `test_csrf.py` — 9/9 PASS (login/register cookie setting, CSRF enforcement on state-mutating endpoints, exemptions on auth routes)
- `test_session_token_hash.py` — 2/2 PASS (token hash storage, lookup by raw token)

No regressions in PR-2 auth layer.

---

## BSD-3 Coverage Note

BSD-3 is a UI-only spec (ShareDialog, RealtimePresenceIndicator, RevocationBlockingOverlay, etc.). This PR is backend-only — no frontend shipped. BSD-3 UI verification is deferred to the PR that delivers the frontend implementation. The backend API behavior the BSD references (REST endpoints, response shapes, error codes) is fully covered by the integration test suite above.

---

## Bugs Found

None. No bug-repro tests written.

---

## E2E Verdict per Feature Area

| Feature | Endpoints | Verdict |
|---------|-----------|---------|
| List CRUD | `POST/GET/PATCH/DELETE /api/v1/lists` | PASS |
| Item CRUD | `POST/GET/PATCH/DELETE /api/v1/lists/{id}/items` | PASS |
| Share management (owner only) | `POST/GET/PATCH/DELETE /api/v1/lists/{id}/shares` | PASS |
| OQ-1 authz — stranger 404 matrix (11 cells) | all list/item/share endpoints | PASS |
| OQ-1 anti-enumeration byte-identicality | GET `/lists/{id}` | PASS |
| Editor CRUD allowed, list/share management denied | mixed | PASS |
| Viewer read-only | items read allowed, write denied | PASS |
| Delete cascade (list → items + shares) | DELETE `/lists/{id}` | PASS |
| Revocation immediate enforcement | DELETE `/shares/{user_id}` → editor loses access | PASS |
| Wire-level OQ-1 (real uvicorn) | all 11 cells | PASS |
| PR-2 regression (CSRF + session hash) | test_csrf.py + test_session_token_hash.py | PASS |
