# Security Review: PR #3

**Verdict:** PASS_WITH_FINDINGS
**Reviewer:** security-reviewer
**Date:** 2026-04-21
**Scope:** 27 changed files — `backend/app/authz/`, `backend/app/{lists,items,shares}/`, `backend/app/models/{list_,item,share}.py`, `backend/app/main.py`, `backend/alembic/`, `backend/tests/`

---

## Summary

PR #3 introduces the sharing and permissions surface — the highest-risk feature in this initiative. The load-bearing authorization invariant (OQ-1: stranger → 404 on every verb, never 403) is correctly implemented at the dependency layer (`require_list_permission`) and uniformly enforced across all 11 list/item/share endpoints. No injection vectors exist; all queries use SQLAlchemy ORM expressions without raw `text()` with user input. CSRF middleware correctly covers all new mutating endpoints without additional exemptions. Authz denials are logged with full context (list_id, user_id, role, action).

One MEDIUM finding blocks merge: `item_id` path parameters in `items/router.py` are declared as `str` rather than `UUID`, creating an inconsistency that bypasses FastAPI's built-in UUID validation and will cause a 500 on malformed item_id inputs rather than a 404. This is a correctness/robustness issue with security implications (error response difference leaks information about path structure). All other checks pass cleanly.

The SCA platform reports one pre-existing open finding (pytest CVE-2025-71176, MEDIUM/LOW) that was already accepted as non-blocking in PR-2 review. No new dependency changes in this PR.

---

## Findings

### MEDIUM: `item_id` path parameters typed as `str` instead of `UUID`

- **Location:** `backend/app/items/router.py:44`, `backend/app/items/router.py:66`
- **Category:** A01 — Broken Access Control (input validation bypass at boundary)
- **Issue:** `update_item` and `delete_item` declare `item_id: str` as the path parameter type, while the `Item.id` primary key is `Mapped[UUID]`. FastAPI does not coerce or validate the path value as a UUID. `db.get(Item, item_id)` will pass the raw string to psycopg3, which will raise a DB-level type error on any non-UUID string input — producing a 500 response rather than a 404.
  
  By contrast, `shares/router.py` correctly uses `target_user_id: UUID` on both its PATCH and DELETE endpoints. The inconsistency is within the same PR.

- **Impact:** Two consequences:
  1. A malformed item_id string (e.g., `"../../etc/passwd"`, `"abc"`) triggers a 500 instead of 404, leaking that the path structure is valid but the value is malformed — a minor but real information difference from the OQ-1 uniform-404 stance.
  2. The cross-list IDOR guard `item.list_id != perm.list_id` is logically correct but depends on the `db.get` returning an `Item` object; with a string PK the lookup may silently return `None` or error depending on psycopg3's coercion behaviour, making the guard's reliability uncertain until the type is corrected.

- **Remediation:** Change both path parameter declarations to `item_id: UUID` (matching the `target_user_id: UUID` pattern in `shares/router.py`). FastAPI will then reject non-UUID strings with a 422 before the handler runs. Example:
  ```python
  async def update_item(
      item_id: UUID,   # was: str
      ...
  ) -> Item:
      item = await db.get(Item, item_id)
  ```

- **Reference:** FastAPI path parameter type validation; OWASP ASVS V5.1.3 (server-side input validation at trust boundaries)

---

### INFO: pytest CVE-2025-71176 — pre-existing, accepted non-blocking

- **Location:** `backend/uv.lock:737`
- **Category:** A06 — Vulnerable and Outdated Components
- **Issue:** pytest 8.3.5 has CVE-2025-71176 (CWE-379: temporary file in insecure directory, CVSS medium). This finding predates PR #3; no new dependencies were added in this PR.
- **Impact:** Dev-only test runner. No production exposure.
- **Remediation:** Upgrade to `pytest>=9.0.3` at next routine dep bump. Accepted as non-blocking per PR-2 review decision.
- **Reference:** GHSA accepted in PR-2-v2 review.

---

## Semgrep Output

**Local SAST scan (`semgrep_scan`):** 0 findings across 2789 rules on 11 changed files (authz + lists + items + shares + models). Clean.

**AppSec platform SAST (`semgrep_findings`, SAST, open):** 0 findings.

**AppSec platform SCA (`semgrep_findings`, SCA, open):** 1 finding — pytest CVE-2025-71176 (pre-existing, accepted non-blocking, see INFO finding above).

---

## Dependencies

No changes to `backend/uv.lock` in this PR (`git diff ead22cc --stat -- backend/uv.lock` returned empty). Supply-chain scan not required.

---

## OQ-1 Anti-Enumeration Verification

**Dependency layer (`backend/app/authz/dependencies.py`):**

The `require_list_permission` dependency performs two independent ORM queries:
1. `SELECT lists.id WHERE lists.id = :list_id AND lists.owner_id = :user_id` → `is_owner`
2. `SELECT shares.role WHERE shares.list_id = :list_id AND shares.user_id = :user_id` → `share_role`

When neither query returns a row, `effective_role()` returns `None` and the dependency raises `HTTPException(status_code=404, detail="Not found")`. This is the same code path for both cases:
- List exists but stranger has no access: `is_owner=False`, `share_role=None` → `role=None` → 404
- List does not exist: same result (both queries return nothing) → `role=None` → 404

**Handler layer:** All handlers that do a secondary `db.get(List, perm.list_id)` after the dependency (e.g., `get_list`, `rename_list`, `delete_list`) use the same `detail="Not found"`. However, these secondary lookups are reached only after `require_list_permission` has already granted access — they cannot be triggered by a stranger.

**Anti-enumeration test (`test_anti_enum_list_404_body_identical`):**
```python
assert r_real.json() == r_ghost.json()
```
This asserts JSON structural equality between a stranger-on-real-list 404 and a ghost-list 404. Both responses originate from the same `raise HTTPException(status_code=404, detail="Not found")` in `require_list_permission`, so FastAPI serializes them identically as `{"detail": "Not found"}`. The assertion is correct and sufficient for JSON APIs. Raw byte comparison is not required here since the serialization path is deterministic (no timestamps, no request-ID injection into error bodies).

**Verdict:** OQ-1 is correctly implemented at both the dependency and test levels. No timing differences exist (both cases take the same two SELECT paths before raising). No response-size or header differences: FastAPI's default error handler returns the same Content-Type and body structure for both.

---

## CSRF Enforcement on New Endpoints

All new mutating endpoints (POST/PATCH/DELETE on `/api/v1/lists/`, `/api/v1/lists/{id}/items`, `/api/v1/lists/{id}/shares`) fall under `/api/v1/` with mutating verbs. The `CSRFMiddleware` in `backend/app/auth/csrf.py` intercepts all `POST/PUT/PATCH/DELETE` requests to `/api/v1/` unless they are in `_CSRF_EXEMPT_PATHS` (only `/api/v1/auth/login` and `/api/v1/auth/register`). No new exemptions were added. CSRF protection applies correctly to all new endpoints.

Integration tests confirm this: the `_login()` helper in all new test files extracts the `csrf_token` cookie and injects it as `X-CSRF-Token` before mutation calls. The absence of this header would return 403, not 404, and tests would fail.

---

## A03 Injection Analysis

No injection risk found. All new DB queries use SQLAlchemy ORM:
- `sa.select(List.id).where(List.id == list_id, List.owner_id == user.id)` — parameterized
- `sa.select(Share.role).where(Share.list_id == list_id, Share.user_id == user.id)` — parameterized
- `sa.select(Item).where(Item.list_id == perm.list_id).order_by(Item.order)` — parameterized
- `db.get(Item, item_id)` / `db.get(List, perm.list_id)` — ORM primary key lookup

No raw `text()` with user input. No `literal_column()`. No string formatting in SQL expressions.

---

## A09 Logging and Monitoring

Authz denials are logged at WARNING level with full context:
```
authz: denied list_id=%s user_id=%s role=%r action=%r
```
Authz grants are logged at INFO level. All item/list/share mutations log the operation with relevant IDs. Silent 404 on IDOR attempt is the correct HTTP response per OQ-1; the audit trail is preserved via the logging statement before the exception is raised.

---

## Not in Scope

The following were observed but are out of scope for this PR review:

- **`GET /api/v1/lists` list-listing endpoint has no pagination.** A user with thousands of shared lists will receive unbounded results. This is a DoS/resource-exhaustion concern, not a per-PR security issue; it should be a follow-up task for a future PR.
- **`Share.role` column is validated by a DB CHECK constraint** (`role IN ('editor', 'viewer')`) and a Pydantic regex field validator (`^(editor|viewer)$`) — defense in depth, clean. However the naming convention divergence between the migration (`ck_shares_role_valid` via `op.f()`) and the model's `__table_args__` (`name="role_valid"`) means the Alembic autogenerate may produce a spurious diff on the next `alembic revision --autogenerate`. This is not a security issue but a migration hygiene concern.
- **No rate limiting on list/item/share creation endpoints.** An authenticated user can create lists/items at unbounded rate. Out of scope for this PR; follow-up recommended at a later phase.
