# QA Runtime Validation Report: PR #3 v2

**Date:** 2026-04-21
**QA Engineer:** qa-engineer
**Branch:** `feat/pr3-sharing @ 0b2da13`
**Worktree used:** `/home/isaac/Desktop/dev/shared-todos-pr3`
**Bug-repro worktree:** N/A — no bugs found

---

## Verdict: PASS

No bugs found. All runtime checks pass.

---

## Environment

- Python 3.12.11 / pytest 8.3.5 / uvicorn
- Real Postgres (docker compose, `shared-todos-pr3-postgres-1`)
- Real mailhog (docker compose, `shared-todos-pr3-mailhog-1`)
- Migration at head: `4df1779548df`
- Worktree already at `0b2da13` — no pull needed

**v2 commits (since ead22cc):**
- `009afc8` — Tighten test_oq1_matrix.py guardrails (items 5+6)
- `1e8929e` — Fix item path param type + drop redundant Share UniqueConstraint
- `266ca6d` — Handle IntegrityError in create_share for race-condition safety
- `08b23e8` — Log ERROR for unknown share_role in effective_role
- `0b2da13` — Reformat test_shares.py to pass ruff format check

---

## Full Test Suite Results

**209/209 pass** (author-claimed count confirmed exactly), 32.47s.

Δ from v1: +4 tests. New tests confirmed present and passing:
- `test_create_share_duplicate_pk_race_returns_409` — IntegrityError → 409
- `test_create_share_fk_violation_returns_404` — FK violation → 404
- `TestEffectiveRole::test_unknown_share_role_returns_none` — unknown role → None
- `TestEffectiveRole::test_unknown_share_role_logs_error` — unknown role logs ERROR

---

## OQ-1 Wire-Level Matrix Re-Run @ 0b2da13

All 11 cells pass against real uvicorn on port 8001. Authz layer did not regress under v2 commits.

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

**Byte-identicality:** PASS — stranger on real list and ghost UUID both return `{"detail":"Not found"}` — byte-identical at the wire.

---

## IntegrityError Scenarios (commit `266ca6d`) — Wire-Level

### Scenario A: FK violation — nonexistent `user_id`

Owner POSTs `/api/v1/lists/{list_id}/shares` with `user_id=00000000-0000-0000-0000-000000000077` (not in users table).

| Measure | Result |
|---------|--------|
| HTTP status | **404** PASS (not 500) |
| Raw body | `{"detail":"Not found"}` |
| Byte-identical to stranger-on-real-list 404 | **True** PASS |

The IntegrityError handler correctly converts the FK violation into a uniform 404 with the same body as all other not-found paths — no leak distinguishing "user not found" from "list not found".

### Scenario B: Duplicate share — same `user_id` twice (race-safe path)

Owner shares list with `target_id`, then immediately shares again with the same `target_id`.

| Request | HTTP status | Body |
|---------|-------------|------|
| First share | 201 | `{"list_id":..., "user_id":..., "role":"viewer", "granted_at":...}` |
| Duplicate share | **409** PASS | `{"detail":"User already has access"}` |

Returns 409 (not 500). The race-safe IntegrityError handler correctly surfaces a structured 409 for duplicate-key rather than leaking a raw database error.

---

## Bugs Found

None. No bug-repro tests written.
