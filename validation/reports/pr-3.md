# Validation Report: PR #3

**Verdict:** REQUEST_CHANGES
**Date:** 2026-04-21
**Target:** https://github.com/iceman12276/shared-todos/pull/3 (branch `feat/pr3-sharing` @ `ead22cc`)

## Summary

PR #3 ships the authorization layer for sharing — `List` / `Item` / `Share` SQLAlchemy models, the `require_list_permission` FastAPI dependency, list/item/share CRUD endpoints, and an 11-cell parametrized integration matrix enforcing OQ-1 (stranger → 404 on every verb, never 403). All CI gates green. Runtime behavior is correct: full pytest suite passes 205/205 against real Postgres, and OQ-1 holds both in-process and at real HTTP wire level with byte-identical 404 bodies between stranger-on-real-list and nonexistent-list. OWASP code review (A01, A03, A04, A09) is clean; fresh Semgrep SAST scan (2789 rules, 11 changed files) is clean; Semgrep AppSec platform reports no new findings.

Verdict is REQUEST_CHANGES due to 4 HIGH + 1 MEDIUM structural findings with two independent two-stream confirmations (items/router UUID drift; redundant Share UniqueConstraint), plus two critical test-quality gaps that touch the OQ-1 invariant's future resilience (parsed-JSON body-identicality assertion where docstring promises bytes; delete-cascade test missing Share-row assertion). Six actionable items gate the flip to PASS; nine secondary findings are documented as recommended follow-up for a cleanup PR. Auto-merge is correctly blocked by REQUEST_CHANGES per Step 2.9 of validate-new-prs.

## Stream 1 — Runtime (QA Engineer)

**Verdict from QA:** PASS — no bugs, no regression.

- `uv run pytest -v` against real Postgres + mailhog: **205/205 pass, 34.23s, no flakes.** Author's 205/205 claim confirmed exactly.
- OQ-1 matrix in-process (TestClient): 11/11 cells → HTTP 404, zero 403s.
- OQ-1 matrix at wire level via real uvicorn on port 8001 (real users registered via `curl`, stranger hitting all 11 endpoints): **11/11 cells → HTTP 404, zero 403s** — confirms OQ-1 is not a TestClient/ASGITransport artifact.
- Byte-identicality at wire: stranger-on-real-list and stranger-on-ghost-UUID both return `{"detail":"Not found"}` byte-identical.
- Anti-enumeration corollary (share-to-nonexistent-user → 404) verified in-process.
- Permission matrix spot-check: owner-creates-list 201, editor-creates-item 201, editor-blocked-from-rename 404, viewer-reads-items 200, viewer-blocked-from-create 404, revoked-editor-blocked 404.
- PR-2 regressions: none (`test_csrf.py` 9/9, `test_session_token_hash.py` 2/2).
- No bug-repro tests written (no bugs found at runtime).

Full report: `validation/qa-reports/pr-3.md`

## Stream 2 — Security (Security Reviewer)

**Verdict from security-reviewer:** PASS_WITH_FINDINGS (1 MEDIUM). Under validation-lead's binary rubric: contributes to REQUEST_CHANGES.

**SAST / SCA:**
- Semgrep MCP scan on changed files (2789 rules, 11 files): 0 findings.
- Semgrep AppSec platform SAST: 0 open findings.
- Semgrep AppSec platform SCA: 1 open finding — `pytest` CVE-2025-71176 (pre-existing, accepted non-blocking since PR-2).
- No lockfile changes — supply-chain scan skipped.

**OWASP code review:**
- **A01 Broken Access Control:** `require_list_permission` is the single gate on all 11 list/item/share endpoints. FastAPI dependency injection guarantees it resolves before handler logic.
- **A03 Injection:** all queries use SQLAlchemy ORM parameterized expressions; no raw `text()` with user input.
- **A04 Insecure Design / anti-enumeration:** stranger-on-real-list and nonexistent-list flow through the same `HTTPException(404, detail="Not found")` line; FastAPI serializes both as `{"detail":"Not found"}`.
- **A09 Logging:** authz denies log at WARNING with user_id+list_id+role+action; grants at INFO.

**OQ-1 invariants:**
- Coverage completeness: YES — every verb × every resource routed through `require_list_permission`.
- Anti-enumeration byte-identicality at code-path level: YES.
- IDOR/BOLA cross-list guard correct (contingent on item_id type fix below).

**Findings:**
- 1 MEDIUM — `backend/app/items/router.py:44,66` — `item_id: str` on PATCH/DELETE item endpoints returns 500 instead of 404 on malformed-UUID input. Breaks OQ-1 uniform-404 stance. Inconsistent with `shares/router.py`'s `target_user_id: UUID`.

**Not-in-scope observations noted:** unbounded `GET /lists` response, naming-convention drift on Share role_valid constraint, no rate limiting on creation endpoints.

Full report: `security/reports/pr-3.md`

## Stream 3 — Structural (PR Review Specialists)

Four pr-review-toolkit specialists dispatched one-shot: code-reviewer, pr-test-analyzer, silent-failure-hunter, type-design-analyzer.

### code-reviewer — 2 HIGH + 2 MEDIUM + 3 LOW

- **H1** `models/share.py:22-24` + migration `4df1779548df:124`: redundant `UniqueConstraint(list_id, user_id)` on a table whose composite PK already enforces uniqueness; creates a duplicate index. Directly contradicts the Group A commit body's own rationale. Locked into `test_models_sharing.py`.
- **H2** `items/router.py:366,388`: `item_id: str` in update_item/delete_item → 500 on invalid UUIDs from authorized users. Inconsistent with `shares/router.py`'s `target_user_id: UUID`. Group D commit message contains an incorrect claim about FastAPI validating str-annotated path UUIDs. *(Same as security-reviewer MEDIUM — two-stream confirmation.)*
- **M1** `tests/integration/test_authz_dependency.py:28-31`: test module mutates production `app` singleton at import time via `app.include_router(_probe_router)`.
- **M2** `shares/router.py:713-720`: duplicate-share race returns 500 (not 409); check-then-insert with no locking.
- **LOW:** dead-code 404 branches in list handlers; list_shares reuses share_list permission; hardcoded ghost UUID in tests.

### pr-test-analyzer — 3 CRITICAL + 4 improvements + 3 quality

- **C-1** `test_oq1_matrix.py:148-168`: anti-enumeration body-identicality uses `r_real.json() == r_ghost.json()` (parsed JSON equality), NOT byte equality — despite the docstring promising byte-identicality. Future request-id or error-tracking middleware would silently break OQ-1 without failing this test. This is the OQ-1-critical test-quality finding.
- **C-2** `test_oq1_matrix.py:277-294`: `test_delete_list_cascades_items_and_shares` name includes "and_shares" but only asserts List + Item removal. Share cascade (`ondelete="CASCADE"` in migration) is unverified — migration could silently drop the cascade and the test would still pass.
- **C-3** `test_models_sharing.py:90-92`: role CHECK constraint verified by name presence, not by SQL enforcement. A weakened constraint with the same name would pass.
- **Improvements:** owner-demote-self untested; concurrent revoke race untested (low-priority); PATCH item order response unasserted; user-delete FK cascade deferred to a later PR.
- **Quality:** probe-router global mutation *(same as code-reviewer M1 — two-stream)*; hardcoded test emails; dead `assert != 403` after `== 404`.

### silent-failure-hunter — 2 HIGH + 4 MEDIUM + 3 LOW

- **H1** `shares/router.py:696-724`: `create_share` IntegrityError on concurrent target-user deletion masked as generic 500. Should map to 404 for OQ-1 consistency (target-user-doesn't-exist is structurally indistinguishable from never-existed) or 409 if FK-violation can be distinguished from duplicate-key.
- **H2** `authz/permissions.py:291-302`: `effective_role` silently returns `None` for unknown `share_role` values. Cascades to bare 404 with no log trail — data drift (manually-corrupted share row, future role-string migration bug) becomes invisible.
- **M1** `authz/permissions.py:305-313`: `can_perform` silently returns `False` for unknown role strings — asymmetric with the module's `raise ValueError` on unknown actions.
- **M2** `lists/router.py:474-492`: Python-side dedup in `list_lists` is fragile; recommend SQL `UNION`.
- **M3** `authz/dependencies.py:219-226`: authz deny log missing `reason=` discriminator (stranger vs insufficient-role) — hurts OQ-1 monitoring granularity.
- **M4** `items/router.py:364-397`: cross-list item_id probes collapsed into 404 with no audit log.
- **LOW:** Item.order missing server_default; test helper bypasses email normalization; TRUNCATE order verified safe.

### type-design-analyzer — ratings + 3 high-leverage fixes

Quantitative ratings (1-10 scale):

| Type | Encapsulation | Invariant | Usefulness | Enforcement |
|------|:-:|:-:|:-:|:-:|
| List | 5 | 7 | 7 | 6 |
| Item | 5 | 6 | 6 | 5 |
| Share | 4 | 8 | 8 | 7 |
| Role/matrix | 8 | 6 | 9 | 7 |
| **Average** | **5.5** | **6.75** | **7.5** | **6.25** |

Highest-leverage fixes (ordered):

1. Remove redundant `UniqueConstraint` on Share *(same as code-reviewer H1 — two-stream confirmation)*.
2. Narrow `Action` and `Role` to `Literal` end-to-end. Currently str-in-model → Literal-in-matrix → str-at-dependency-boundary loses mypy protection at each layer.
3. Split `Role` into `StoredShareRole` (editor|viewer — DB CHECK enforced) vs `EffectiveRole` (owner|editor|viewer). Current conflation types `owner` as valid on a `Share` row, which the DB rejects.

## Cross-Stream Correlations (two-stream-confirmed findings)

1. **Redundant Share `UniqueConstraint`** → code-reviewer H1 + type-design-analyzer top fix. HIGH confidence.
2. **Probe router global `app` mutation** → code-reviewer M1 + pr-test-analyzer Q-1. MEDIUM.
3. **`create_share` IntegrityError handling** → silent-failure-hunter H1 + code-reviewer M2 (different triggers — concurrent user-delete vs concurrent duplicate-share — same class of unhandled race). HIGH confidence together; fix is a single IntegrityError mapping.
4. **Role typing inconsistency** → type-design-analyzer (standout weakness) + silent-failure-hunter H2 (silent-None on unknown role). MEDIUM-HIGH.
5. **`item_id: str` → 500 vs OQ-1 uniform-404** → code-reviewer H2 + security-reviewer MEDIUM. HIGH.

## Required Actions (gate the flip to PASS)

1. `backend/app/items/router.py:44,66` — `item_id: str` → `item_id: UUID` on update_item and delete_item. Correct the Group D commit message on next rebase. *(code-reviewer H2 + security-reviewer MEDIUM)*
2. `backend/app/models/share.py:22-24` and migration `4df1779548df:124` — remove redundant `UniqueConstraint(list_id, user_id, name="uq_shares_list_user")` and duplicate index. Update locked-in assertion in `test_models_sharing.py`. *(code-reviewer H1 + type-design-analyzer)*
3. `backend/app/shares/router.py:696-724` — IntegrityError handler distinguishing FK-violation (concurrent target-user delete) → 404 from duplicate-key (share exists) → 409. *(silent-failure-hunter H1)*
4. `backend/app/authz/permissions.py:291-302` — `effective_role` raises typed exception or logs at ERROR on unknown stored role (symmetric with `can_perform`'s `raise ValueError`). Add test that seeds malformed `share_role`. *(silent-failure-hunter H2)*
5. `backend/tests/integration/test_oq1_matrix.py:148-168` — strengthen `test_anti_enum_list_404_body_identical` to assert `r_real.content == r_ghost.content` (raw bytes). *(pr-test-analyzer C-1)*
6. `backend/tests/integration/test_oq1_matrix.py:277-294` — `test_delete_list_cascades_items_and_shares` must actually assert Share-row removal. *(pr-test-analyzer C-2)*

## Recommended Follow-up (not merge-blocking)

Tracked here so engineering can bundle into a cleanup PR after PR-3 merges:

- `Action` / `Role` as `Literal` end-to-end.
- Split `Role` into `StoredShareRole` vs `EffectiveRole`.
- `can_perform` symmetry (raise on unknown role strings).
- SQL `UNION` replacement for Python-side dedup in `list_lists`.
- `reason=` discriminator in authz deny logs.
- Audit log on cross-list item_id probes.
- Fixture-scoped test app for the probe router.
- CHECK-constraint SQL-enforcement assertion.
- LOW items: Item.order server_default; test helper email-normalization bypass; hardcoded ghost UUID; dead-code 404 branches in list handlers.

## Auto-merge interaction

Per Step 2.9 of the updated `validate-new-prs` skill, REQUEST_CHANGES blocks auto-merge. Polling loop will post the review body via `gh pr comment`, apply `claude-validated:v1` + `claude-validated:changes-requested` labels, and leave the PR awaiting human action. When engineering addresses findings and re-pushes, removing both labels forces re-validation on the next polling tick.
