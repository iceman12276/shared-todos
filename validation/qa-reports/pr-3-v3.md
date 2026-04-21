# QA Runtime Validation Report: PR #3 v3

**Date:** 2026-04-21
**QA Engineer:** qa-engineer
**Branch:** `feat/pr3-sharing @ 0548756`
**Worktree used:** `/home/isaac/Desktop/dev/shared-todos-pr3`
**Bug-repro worktree:** N/A — no bugs found

---

## Verdict: PASS

No bugs found. All 4 wire-level checks pass.

---

## Environment

- Python 3.12.11 / pytest 8.3.5 / uvicorn
- Real Postgres (docker compose, `shared-todos-pr3-postgres-1`)
- Migration at head: `4df1779548df`
- Worktree already at `0548756` — no pull needed

**v3 commits (since 0b2da13):**
- `231ec2a` — Replace substring IntegrityError dispatch with psycopg isinstance
- `26062c9` — Raise ValueError for unknown share_role in effective_role
- `0548756` — Add 422-on-bad-UUID tests for item PATCH and DELETE

---

## Check 1: Full Test Suite

**211/211 pass** (author-claimed count confirmed), 32.80s.

Δ from v2: +2 tests (`test_patch_item_bad_uuid_returns_422`, `test_delete_item_bad_uuid_returns_422`).

**First-run note:** The very first `pytest` invocation produced 2 `InvalidRequestError` failures on `test_create_share_duplicate_pk_race_returns_409` and `test_create_share_fk_violation_returns_404`. Root cause: DB state left by v2's wire-level test session (duplicate email rows from `qa_v2_*` users) caused SQLAlchemy's identity-map `refresh()` to fail during `_seed()`. A targeted re-run of both tests immediately after confirmed **2/2 pass** in isolation. This is a test-session isolation artifact from cross-session DB pollution, **not a v3 regression**. The full suite run (second pass) is 211/211 clean.

---

## Check 2: OQ-1 Wire Matrix Re-Run @ 0548756

All 11 cells pass against real uvicorn on port 8001. Authz layer unchanged by v3 commits.

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

**Byte-identicality:** PASS — `{"detail":"Not found"}` for both real-list-stranger and ghost UUID.

---

## Check 3: FK Violation Scenario (isinstance dispatch) — Wire Level

Owner POSTs `/api/v1/lists/{list_id}/shares` with `user_id=00000000-0000-0000-0000-000000000077` (not in users table). The v3 commit `231ec2a` replaced substring-matching IntegrityError dispatch with psycopg `isinstance` checks.

| Measure | Result |
|---------|--------|
| HTTP status | **404** PASS |
| Raw body | `{"detail":"Not found"}` |
| Byte-identical to stranger-on-real-list 404 | **True** PASS |

The isinstance-based dispatch preserves the byte-identicality invariant. No regression from v2.

---

## Check 4: Unknown Stored Role — End-to-End Wire Verification

**Setup:** Directly injected a `shares` row with `role='admin'` via psql (bypassing Pydantic). The `ck_shares_role_valid` check constraint required dropping temporarily:

```sql
ALTER TABLE shares DROP CONSTRAINT IF EXISTS ck_shares_role_valid;
INSERT INTO shares (list_id, user_id, role, granted_at)
  VALUES ('{list_id}', '{badrole_user_id}', 'admin', NOW());
-- constraint restored after test via separate call
ALTER TABLE shares ADD CONSTRAINT ck_shares_role_valid CHECK (role IN ('owner', 'editor', 'viewer'));
```

**Observed behavior when bad-role user hits `GET /api/v1/lists/{list_id}`:**

| Measure | Result |
|---------|--------|
| HTTP status | **500 Internal Server Error** |
| Response body | `Internal Server Error` (plain text, uvicorn default) |
| Content-Type | `text/plain; charset=utf-8` |
| Is this a silent 404? | **No** — correctly surfaces as 500 |

**Verdict: PASS for the raise-end-to-end choice.** The `ValueError` raised by `effective_role` on unknown role propagates as a 500, not silently swallowed as a 404. This is the correct behavior per commit `26062c9`'s design intent — an unknown DB role is a data-integrity signal that should be loud, not hidden.

**Notable:** The 500 body is uvicorn's generic plain-text handler (`Internal Server Error`), not a FastAPI JSON error. This is expected — FastAPI's `RequestValidationError` handler doesn't intercept unhandled `ValueError`. The check constraint prevents this scenario in practice; the 500 path is defense-in-depth for DB corruption scenarios.

**DB cleanup:** bad-role row deleted, `ck_shares_role_valid` constraint restored before server teardown. Verified constraint present in `pg_constraint` after restore.

---

## Bugs Found

None. No bug-repro tests written.
