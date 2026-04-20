# Security Review: PR #1

**Verdict (current):** CLEAN — v2 @ f8f9fad (2026-04-20)
**Verdict (v1):** FAIL — REQUEST_CHANGES @ c19da03 (2026-04-20) — see v1 findings below
**Reviewer:** security-reviewer
**Date:** 2026-04-20
**Scope:** `.github/workflows/ci.yml`, `backend/app/main.py`, `backend/app/config.py`, `backend/app/db/base.py`, `backend/alembic/env.py`, `backend/uv.lock` (34 packages v1 / 35 packages v2)
**Branch:** `feat/pr1-foundation` → `master`

---

## Summary

This PR establishes the backend foundation: FastAPI skeleton, SQLAlchemy/Alembic bootstrap, Pydantic Settings configuration, and the CI workflow that will gate every future commit. The Python application code (~110 LOC) is clean — Semgrep (2,852 rules, 5 files) returned zero findings, and no injection sinks, secret handling failures, or authz gaps are present at this stage. The CI workflow is well-structured with correct permissions scoping (`contents: read` only), no `pull_request_target` misuse, and no expression-injection vectors.

However, two issues block merge: (1) two CVEs in `starlette==0.46.2` that cannot be patched without also upgrading `fastapi`, and (2) all four GitHub Actions are pinned to mutable tag refs rather than immutable commit SHAs, meaning a compromised upstream tag could silently inject malicious code into every CI run gating this repository. A third non-blocking issue (pytest CVE and one advisory-level finding) is noted for awareness. Fixing the starlette/fastapi pair now — before PR-2 adds auth and business logic — is the cleanest path forward.

---

## Findings

### HIGH: Two unpatched CVEs in starlette==0.46.2 (DoS — network-exploitable)

- **Location:** `backend/uv.lock` (transitive via `fastapi==0.115.12`)
- **Category:** A06:2021-Vulnerable and Outdated Components
- **CVE 1:** GHSA-7f5h-v6xp-fcq8 / CVE-2025-62727
  - **CVSS:** 7.5 (CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H)
  - **Issue:** O(n²) DoS via crafted HTTP `Range` header in `starlette.responses.FileResponse._parse_range_header()`. An unauthenticated attacker sends a multi-range request that triggers quadratic CPU work per request, exhausting the server.
  - **Fixed in:** starlette 0.49.1
- **CVE 2:** GHSA-2c2j-9gv5-cj73 / CVE-2025-54121
  - **CVSS:** 5.3 (CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:L)
  - **Issue:** When parsing multipart form uploads with files exceeding the spool threshold, Starlette blocks the async event loop on a sync disk flush, preventing new connections from being accepted.
  - **Fixed in:** starlette 0.47.2
- **Constraint conflict:** `fastapi==0.115.12` pins `starlette<0.47.0,>=0.40.0`, making it impossible to upgrade starlette alone. The full fix requires upgrading **both** packages.
  - fastapi 0.121.x allows starlette < 0.50.0 (covers the 0.49.1 fix for both CVEs)
  - fastapi >= 0.136.0 (latest as of 2026-04-20) allows starlette >= 0.46.0 with no upper cap
- **Impact:** Any endpoint that uses `FileResponse`, `StaticFiles`, or multipart form parsing is exploitable. PR-1 only has `/health` which doesn't exercise these, but PR-2+ will almost certainly add file upload or static serving. Locking these CVEs in now is harder to fix under a live service.
- **Remediation:** Upgrade fastapi to >= 0.121.0 and regenerate `uv.lock`. The minimum safe pinned pair is `fastapi==0.121.0` + `starlette==0.49.1`. Recommend going to latest fastapi (0.136.0) to avoid re-hitting the constraint ceiling in future minor bumps.
- **Reference:** [GHSA-7f5h-v6xp-fcq8](https://github.com/advisories/GHSA-7f5h-v6xp-fcq8), [GHSA-2c2j-9gv5-cj73](https://github.com/advisories/GHSA-2c2j-9gv5-cj73)

---

### MEDIUM: All GitHub Actions pinned to mutable tag refs, not commit SHAs

- **Location:** `.github/workflows/ci.yml` (lines 53, 65, 70, 163, 170, 189)
- **Category:** A08:2021-Software and Data Integrity Failures / supply-chain
- **Issue:** All four distinct actions use floating tag refs:
  - `actions/checkout@v4` (3 occurrences)
  - `actions/setup-python@v5` (2 occurrences)
  - `astral-sh/setup-uv@v3` (1 occurrence)
  - `gitleaks/gitleaks-action@v2` (1 occurrence)

  A tag in GitHub is mutable: an attacker who compromises or typosquats the upstream repo (or gains write access to it) can push new code to `@v4` without any change to the workflow YAML. Because this CI workflow is the security gate for every future PR, a compromised action runs with the full `GITHUB_TOKEN` and access to the checkout — exfiltrating secrets, injecting malicious builds, or silently bypassing security checks.
- **Impact:** Supply-chain compromise of any referenced action owner → code execution in CI with access to `GITHUB_TOKEN` and workspace. This is how the `tj-actions/changed-files` and `reviewdog` supply-chain incidents worked.
- **Remediation:** Pin every `uses:` reference to its full 40-character commit SHA. Then update via Dependabot or Renovate. Example:
  ```yaml
  # Before
  - uses: actions/checkout@v4
  # After (example SHA — verify current)
  - uses: actions/checkout@a5ac7e51b41094c92402da3b24376905380afc29  # v4.1.6
  ```
  Use `gh api repos/actions/checkout/git/refs/tags/v4` to resolve the current SHA for each action.
- **Reference:** [GitHub hardening guide](https://docs.github.com/en/actions/security-guides/security-hardening-for-github-actions#using-third-party-actions), [OWASP CI/CD Security A08](https://owasp.org/www-project-top-10-ci-cd-security-risks/)

---

### LOW: pytest==8.3.5 CVE in dev dependency (local privilege escalation, not CI-relevant)

- **Location:** `backend/uv.lock` (dev dependency group)
- **Category:** A06:2021-Vulnerable and Outdated Components
- **CVE:** GHSA-6w46-j5rx-g56g / CVE-2025-71176
  - **CVSS:** 6.3 (CVSS:3.1/AV:L/AC:L/PR:N/UI:N/S:C/C:L/I:L/A:L)
  - **Issue:** pytest through 9.0.2 uses predictable `/tmp/pytest-of-{user}` directories on UNIX, allowing local users to potentially cause DoS or gain privileges via symlink attacks.
  - **Fixed in:** pytest 9.0.3
- **Impact assessment:** LOW in this context. The attack requires local filesystem access to the machine running tests. In CI (ubuntu-latest runner, ephemeral VM), there are no other local users to exploit this. On developer machines it is a local privilege escalation concern, not a remote one. Dev dependency only — not shipped to production.
- **Remediation:** Upgrade `pytest` to `>=9.0.3` in `pyproject.toml` and regenerate `uv.lock`. Non-urgent; schedule for the next routine dep bump.
- **Reference:** [GHSA-6w46-j5rx-g56g](https://github.com/advisories/GHSA-6w46-j5rx-g56g)

---

### INFO: Hardcoded default credentials in config.py

- **Location:** `backend/app/config.py:8-10`
- **Category:** A05:2021-Security Misconfiguration
- **Issue:** `Settings.database_url` defaults to `postgresql+psycopg_async://shared_todos:shared_todos@localhost:5432/shared_todos`. If `Settings()` is ever constructed in a deployed environment without an `.env` file or env var override, the application will attempt to connect with these weak, guessable credentials.
- **Impact assessment:** INFO at this stage — Pydantic Settings correctly reads from the environment, `.env` is gitignored, and `.env.example` is present with no secrets. The default value is functionally a dev-bootstrap convenience. The actual risk materializes only if a deployment misconfiguration omits the env var, which is a deployment concern, not a code defect in this PR.
- **Remediation (for PR-2):** Consider replacing the default with a value that fails fast and loudly (`database_url: str` with no default, or a sentinel like `"UNSET"`). Pydantic will raise `ValidationError` at startup if the var is missing, which is safer than silently using weak defaults. This is advisory — do not block PR-1 on it, but address before first deployed environment.
- **Reference:** [OWASP ASVS V6.1](https://owasp.org/www-project-application-security-verification-standard/)

---

### INFO: mailhog/mailhog:latest — unmaintained image with floating tag in CI

- **Location:** `.github/workflows/ci.yml:44`
- **Category:** A08:2021-Software and Data Integrity Failures
- **Issue:** `mailhog/mailhog:latest` is used as a CI service. The `mailhog` Docker Hub repository is unmaintained (last meaningful update ~2021), and `latest` is a floating tag — non-deterministic and potentially subject to tag mutation.
- **Impact assessment:** Very low in practice. This is a CI-only dev email sink with no external network exposure. The risk is theoretical (non-deterministic builds; if the image were hijacked, it could affect CI). No known active exploitation of this specific image.
- **Remediation:** Pin to a specific digest (e.g., `mailhog/mailhog@sha256:<digest>`) or switch to `axllent/mailpit` which is actively maintained. Non-blocking.

---

## Semgrep Output

- **Scan engine:** Semgrep via MCP
- **Rules applied:** 2,852
- **Files scanned:** `base.py`, `ci.yml`, `config.py`, `env.py`, `main.py`
- **Errors:** 0
- **Skipped rules:** 0
- **Findings:** **0**

All five files returned zero SAST findings across 2,852 rules including OWASP Top Ten, Python security, secrets, and injection patterns. This is a strong baseline for the code layer.

---

## Dependencies (Supply Chain Audit)

**Method:** OSV.dev API queried per-package for all 34 packages in `backend/uv.lock`.
Note: `semgrep_scan_supply_chain` MCP tool requires an active Semgrep daemon (not available in this environment). Semgrep platform historical SCA findings (`semgrep_findings issue_type=sca`) returned empty — no prior scans on record.

| Package | Version | Status | Notes |
|---------|---------|--------|-------|
| starlette | 0.46.2 | **VULN (2 CVEs)** | See HIGH finding above |
| pytest | 8.3.5 | **VULN (1 CVE)** | See LOW finding above |
| fastapi | 0.115.12 | Clean | But constrains starlette fix |
| sqlalchemy | 2.0.41 | Clean | |
| alembic | 1.15.2 | Clean | |
| psycopg | 3.2.9 | Clean | |
| pydantic | 2.11.4 | Clean | |
| pydantic-settings | 2.9.1 | Clean | |
| uvicorn | 0.34.2 | Clean | |
| mako | 1.3.11 | Clean | |
| h11 | 0.16.0 | Clean | |
| httpx | 0.28.1 | Clean | |
| anyio | 4.13.0 | Clean | |
| certifi | 2026.2.25 | Clean | |
| All other 20 packages | various | Clean | |

**Finding summary:** 2 HIGH CVEs (starlette), 1 LOW CVE (pytest-dev), 31 packages clean.

---

## CI Workflow Security Analysis

| Check | Result | Notes |
|-------|--------|-------|
| `pull_request_target` misuse | PASS | Not present |
| Top-level `permissions` | PASS | `contents: read` only |
| Job-level permissions override | PASS | None present; inherits least-privilege |
| `GITHUB_TOKEN` usage | PASS | Only in gitleaks action, appropriate |
| `GITHUB_OUTPUT` injection | PASS | Value from committed file `.python-version`, not user-controlled input |
| `GITHUB_ENV` injection | PASS | Not used |
| Script injection via `${{ github.event.* }}` | PASS | No PR body/title interpolated into shell |
| Action commit SHA pinning | **FAIL** | All 4 actions use tag refs (see MEDIUM finding) |
| Container image pinning | **ADVISORY** | `mailhog/mailhog:latest` floating tag |
| Semgrep coverage | PASS | p/default + p/python + p/owasp-top-ten + p/secrets |
| Gitleaks secret scan | PASS | Correctly configured with `GITHUB_TOKEN` |
| `uv sync --frozen` | PASS | Lockfile-based installs prevent dep drift |

---

## Baseline Established (What Is Clean for PR-2 Reference)

The following patterns are correctly established in this PR and should be preserved in PR-2+:

- **Secret handling:** Pydantic `BaseSettings` with env var priority, `.env` gitignored, `.env.example` committed — correct pattern.
- **DB URL normalization:** Both `env.py` and `db/base.py` correctly normalize `postgresql+psycopg://` → `postgresql+psycopg_async://`. The logic is consistent.
- **Async engine:** `create_async_engine` + `async_sessionmaker` + `NullPool` for migrations — correct async-first setup.
- **No DB URL logging:** `echo=False` on the engine — DB queries not logged to stdout.
- **CI permissions:** Least-privilege `contents: read` at workflow level, no excessive scopes.
- **No `pull_request_target`:** Workflow uses `pull_request` — correct; avoids the write-permission-on-fork attack vector.
- **`uv sync --frozen`:** Lockfile-pinned installs in CI — correct, reproducible builds.
- **Semgrep rules in CI:** p/default + p/python + p/owasp-top-ten + p/secrets — good coverage set.

---

---

## v2 Review (2026-04-20) — commit f8f9fad

**Verdict: PASS**
**Delta commits reviewed:** `db05c37` (fastapi/starlette bump), `1478e1f` (CI SHA pinning), `eac64c5` (Settings/Base refactor), `f8f9fad` (type_annotation_map fix)

### RESOLVED

**HIGH — starlette CVEs (GHSA-7f5h-v6xp-fcq8 + GHSA-2c2j-9gv5-cj73): RESOLVED**

Confirmed via OSV.dev advisory metadata (not arithmetic inference):
- GHSA-7f5h-v6xp-fcq8 (CVE-2025-62727, CVSS 7.5): affected range `introduced: 0.39.0 / fixed: 0.49.1`. starlette==1.0.0 is past the fix boundary. OSV query for starlette==1.0.0 returns 0 open vulns.
- GHSA-2c2j-9gv5-cj73 (CVE-2025-54121, CVSS 5.3): affected range `introduced: 0 / fixed: 0.47.2`. starlette==1.0.0 is past the fix boundary. Confirmed closed.
- fastapi==0.136.0 OSV query: 0 vulns. Compatible with starlette>=0.46.0 (no upper cap).

**MEDIUM — GitHub Actions tag pinning: RESOLVED**

All 7 action call sites verified as 40-character hex commit SHAs:
- `actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # v4` — 3 call sites, all pinned
- `actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065 # v5` — 2 call sites, both pinned
- `astral-sh/setup-uv@8d55fbecc275b1c35dbe060458839f8d30439ccf # v3` — 1 call site, pinned
- `gitleaks/gitleaks-action@ff98106e4c7b2bc287b24eaf42907196329070c7 # v2` — 1 call site, pinned

Zero tag refs (`@v\d+`, short SHAs, or branch names) remain.

**ADVISORY — Hardcoded DATABASE_URL default: RESOLVED**

`config.py` refactored: `database_url: str` now has no default — Pydantic will raise `ValidationError` at startup if the env var is absent. `extra="forbid"` also upgraded from `extra="ignore"`, closing the silent-unknown-field-accepted vector. URL normalization consolidated into a single `@field_validator("database_url")` — no more call-site repetition in `db/base.py` or `alembic/env.py`.

### NEW PACKAGES (dep delta audit)

**annotated-doc==0.0.4 — CLEAN (new transitive from fastapi 0.136.0)**
- Not a direct dep (absent from `pyproject.toml`).
- Author: Sebastián Ramírez (tiangolo@gmail.com) — FastAPI creator; repo at `fastapi/annotated-doc`.
- No dependencies of its own (`Requires dist: None`).
- OSV query: 0 vulns.
- Verdict: legitimate, low-risk utility library from the same author as fastapi.

### SAST REGRESSION CHECK

- **Scan:** Semgrep, 2,852 rules, 5 files (`config.py`, `db/base.py`, `alembic/env.py`, `conftest.py`, `test_app_boots.py`), 0 errors
- **Findings: 0** — regression-free through the refactor
- **Notable clean patterns added in v2:**
  - `conftest.py`: fixtures use `async_sessionmaker` directly against `_engine` — no mock injection, no type escapes
  - `env.py`: `config.set_main_option` now receives already-normalized URL from `settings.database_url` — normalization is single-source
  - `base.py`: `type_annotation_map` uses `Uuid(as_uuid=True)` and `DateTime(timezone=True)` — explicit, no implicit type coercion

### REMAINING (unchanged from v1, accepted as non-blocking)

| Finding | Status | Rationale |
|---------|--------|-----------|
| pytest==8.3.5 LOW CVE (GHSA-6w46-j5rx-g56g) | Accepted, not fixed | Engineering-lead accepted; dev-only dep, local privesc only, fix at next routine bump (pytest>=9.0.3) |
| mailhog/mailhog:latest INFO | Accepted, not fixed | CI-only email sink, no prod exposure |

---

## Not In Scope (Deferred to PR-2+)

- **OQ-1 (unauthenticated → 404):** Codified in ADR; no auth endpoints exist yet. Verify enforcement when authz middleware lands in PR-2.
- **DAST/runtime testing:** No deployed service yet; `/health` only.
- **Auth/authz patterns:** No auth code in this PR.
- **Rate limiting on auth endpoints:** Deferred to when auth endpoints land.
