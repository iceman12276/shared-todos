# Security Review: PR #2 v4

**Verdict:** PASS
**Reviewer:** security-reviewer
**Date:** 2026-04-21
**Head:** 56963de
**Scope:** v4-delta — Semgrep custom rule patch (`no-exception-in-except-tuple.yml`) + shared fixture (`no-exception-in-except-tuple.py`) + CI scope corrections (`.github/workflows/ci.yml`)

---

## Summary

v4 closes the partition coverage gap identified in v3. The `no-exception-in-except-tuple` rule was missing alias-form patterns (`except (..., Exception) as exc:`), which is the exact Group G regression form (`except (ValueError, json.JSONDecodeError, binascii.Error, Exception) as exc:`) that the rule exists to catch. The v4 patch adds the three missing `as $E` variants (trailing, leading, middle), and the shared fixture covers the full {position × alias} cartesian: 8 positive cases and 3 negative cases.

Empirical meta-test via `semgrep_scan_with_custom_rule`: 8/8 positives fired (including P8, the exact Group G regression line with alias), 3/3 negatives did NOT fire. CI `--exclude backend/semgrep-rules/` is correctly scoped, preventing the fixture from triggering false findings in the production security-gate run. SAST regression on changed files returned 0 findings, 0 errors against 2,852 rules. No new dependencies introduced — SCA not applicable for this delta.

One INFO observation: the CI yaml does not include a `semgrep --test backend/semgrep-rules/` step. This does not block merge — the rule is empirically verified by the shared fixture, and the fixture is committed for local testing. Recommend adding the `semgrep --test` step in a follow-up CI hardening task to automate regression detection.

---

## Findings

### INFO: No `semgrep --test` step in CI

- **Location:** `.github/workflows/ci.yml` (security-gate job)
- **Category:** Process / CI hardening
- **Issue:** The v3 synthesis prescribed adding `semgrep --test backend/semgrep-rules/` as a CI step. The v4 CI yaml adds `--exclude backend/semgrep-rules/` (correct) but does NOT add the `semgrep --test` step. The shared fixture (`no-exception-in-except-tuple.py`) exists with `# ruleid:` / `# ok:` markers, but automated regression testing of the rule itself is not wired to CI.
- **Impact:** A future rule edit that silently breaks coverage (the exact defect this patch corrects) would not be caught by CI until a human re-runs the fixture manually. Low probability, but the fixture exists precisely to prevent this class of regression.
- **Remediation:** Add to the CI security-gate job:
  ```yaml
  - name: Test custom Semgrep rules
    run: semgrep --test backend/semgrep-rules/
  ```
  This runs in seconds and requires no auth.
- **Severity:** INFO — does not block merge; rule is verified correct as of this PR.

---

## Semgrep Meta-Test Results (Shared Fixture)

Rule: `backend/semgrep-rules/no-exception-in-except-tuple.yml` (v4: 6 patterns)
Fixture: `backend/semgrep-rules/no-exception-in-except-tuple.py` (11 cases)

| Case | Form | Alias | Expected | Result |
|------|------|-------|----------|--------|
| P1 | trailing | no | FIRE | FIRED |
| P2 | trailing (3-type) | no | FIRE | FIRED |
| P3 | trailing | yes | FIRE | FIRED |
| P4 | trailing (3-type) | yes | FIRE | FIRED |
| P5 | leading | no | FIRE | FIRED |
| P6 | leading | yes | FIRE | FIRED |
| P7 | middle | no | FIRE | FIRED |
| P8 | middle (Group G exact) | yes | FIRE | FIRED |
| N1 | bare single ValueError | yes | NO FIRE | SILENT |
| N2 | bare single Exception | yes | NO FIRE | SILENT |
| N3 | bare single Exception | no | NO FIRE | SILENT |

P8 is the critical regression case: `except (ValueError, json.JSONDecodeError, binascii.Error, Exception) as exc:`. This is the exact form that was missed by the v3 rule and is the Group G class the rule was written to prevent.

**8/8 positives fired. 3/3 negatives silent. Rule is correct.**

---

## SAST Regression

Files scanned (v4 delta): `backend/app/auth/oauth.py`, `backend/app/auth/router.py`, `backend/semgrep-rules/no-exception-in-except-tuple.yml`

- Results: **0 findings**
- Errors: **0**
- Rules evaluated: **2,852**

No regressions introduced by v4 changes.

---

## Dependencies

No new dependencies in v4 delta. SCA not applicable.

---

## CI Scope Verification

| CI configuration | Status |
|---|---|
| `--config backend/semgrep-rules/` (loads custom rules) | Present — confirmed |
| `--exclude backend/semgrep-rules/` (prevents fixture scan) | Present — confirmed |
| `semgrep --test backend/semgrep-rules/` (rule regression CI step) | ABSENT — INFO finding above |

The `--exclude` scoping is correctly applied. Without it, the `# ruleid:` fixture lines would cause the production security-gate to fail on the fixture file itself. With it, the fixture is available for local `semgrep --test` runs but is not scanned by CI's security pass.

---

## Not in Scope

- v2/v3 findings (CRITICAL-1 OAuth RS256, CRITICAL-4 email_verified, HIGH-9 token_hash, HIGH-10 authlib removal) — all verified RESOLVED in v2 security report; not re-audited in v4 narrow scope.
- Full white-box pentest — validation-lead calls shannon-pentest at release boundaries.
