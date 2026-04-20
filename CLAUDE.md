# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Shared todos web app — register, login, create todo lists, share with other registered users. Greenfield test-bed for the multi-team agentic coding system (planning → engineering → validation pipeline). Full initiative context lives in `docs/initiatives/2026-04-19-shared-todos-app.md` (approved memo, authoritative user decisions on scope) and `docs/initiatives/RESUME.md` (current state across restarts).

## Stack

- **Backend:** Python 3.12 / FastAPI / async SQLAlchemy 2.x / psycopg3 / Alembic (async template) / pydantic-settings / uv for deps
- **Frontend:** React / TypeScript / Vite / TanStack Query (not yet implemented; lands in PR-6+)
- **Auth:** httpOnly `SameSite=Lax` session cookies + Google OAuth + password reset via mailhog (dev) / real SMTP (prod)
- **Realtime:** WebSocket over `/ws/v1/lists/{list_id}` + `/ws/v1/user`, fan-out via Postgres `LISTEN/NOTIFY` (single-backend-replica for v1). Decision + alternatives in `docs/architecture/realtime-transport-decision.md`.

## Commands

All backend commands run from `backend/`. Uses `uv` exclusively — **never mix in `pip`**. Local dev needs `docker compose up -d postgres mailhog` first (test suite talks to real services, no mocks).

```bash
# Backend deps (reproducible install from uv.lock)
uv sync --frozen

# Run server locally
uv run uvicorn app.main:app --reload

# Tests — REAL Postgres + mailhog required (boots the real app)
uv run pytest -v

# Lint + format
uv run ruff check .
uv run ruff format --check .

# Type check
uv run mypy --strict .

# Migrations (empty versions/ until PR-2)
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "description"

# Run a single test
uv run pytest tests/test_app_boots.py::test_health_endpoint_responds_200 -v
```

CI runs the same commands via 3 parallel jobs (backend / test-quality-gate / security-gate) on PR + master push. `.github/workflows/ci.yml` is the source of truth for exact invocations.

## Required env

Backend reads env via `Settings` (pydantic-settings) with `extra="forbid"` — **unknown env vars fail at startup, loud.** `database_url` has no default; if unset, import of `app.config` raises `ValidationError`. Copy `backend/.env.example` to `backend/.env` for local dev.

- `DATABASE_URL` — async dialect accepted: `postgresql+psycopg://...` or `postgresql+psycopg_async://...`. The validator raises on unknown schemes (no silent no-op).
- `SMTP_HOST`, `SMTP_PORT` — mailhog default in dev (`localhost:1025`).

## Architecture — what to understand before touching code

### File ownership and where to add things

The repo is a **two-service monorepo** (`backend/` + future `frontend/`). There are also per-agent domain boundaries enforced by hooks in `~/.claude/hooks/domain-config.yaml`. Relevant when touching code:

- `backend/**` — backend app code + tests + `pyproject.toml`, `uv.lock`, `.python-version`, `docker-compose.yml`
- `docs/architecture/**` — ADRs. Decisions, not implementation. Authoritative for engineering.
- `docs/planning/prd-*.md` — product requirements (what + why, no implementation details)
- `docs/planning/bsd-*.md` — interaction/behavior specs referencing the PRDs (screen states, edge cases, event semantics)
- `.github/workflows/**` — CI. Adapt `~/.claude/references/ci-template.yml`; don't compose from scratch.
- `validation/reports/**` — PR validation artifacts (per-PR findings)
- `security/reports/**` — security review artifacts

### Key architectural choices (load-bearing for PR-2+)

1. **Config singleton constructed at module import.** `settings = Settings()` in `app/config.py` is instantiated once; failure to set `DATABASE_URL` cascades to every importer (tests, alembic, main). This is intentional fail-fast.

2. **URL scheme normalization is a Pydantic validator on `Settings.database_url`.** Single source of truth — do NOT re-do `.replace("postgresql+psycopg://", ...)` at call sites. `alembic/env.py` and `app/db/base.py` both consume `settings.database_url` as-is.

3. **`Base` (SQLAlchemy `DeclarativeBase`) imposes two conventions — inherit, don't override:**
   - `metadata = MetaData(naming_convention={...})` — every constraint gets a deterministic name (`ix_*`, `uq_*`, `ck_*`, `fk_*`, `pk_*`). Alembic autogenerate produces stable diffs because of this; don't set `name=` on constraints unless you need to bypass the convention (which would silently do so — be explicit in a comment).
   - `type_annotation_map = {UUID: Uuid(as_uuid=True), datetime: DateTime(timezone=True)}` — `Mapped[UUID]` and `Mapped[datetime]` columns pick up the right SQL types automatically. **Every datetime is timezone-aware by default**; for a naive timestamp, override via explicit `mapped_column(DateTime(timezone=False))`.

4. **Session pattern for endpoints:** FastAPI dependency `get_session()` in `app/db/base.py`. It yields an `AsyncSession` from `async_session_factory`; on exception the session rolls back via `__aexit__`. **Handlers MUST explicitly `await session.commit()`** — unhandled paths roll back (consistent with tests silently passing but no DB persistence). Docstring on `get_session()` codifies the contract.

5. **Tests import `_engine` directly in `conftest.py` for fixture wiring.** This is an accepted bounded-consumer pattern (v3 PASS justification on PR #1). Rename-safety is enforced by mypy `--strict` + the integration test hitting real Postgres. If a second non-test consumer of `_engine` appears, PR-2+ is the natural cleanup moment (export as non-private `engine`).

6. **Integration tests boot the REAL app against REAL Postgres.** No mocks. `tests/conftest.py` provides `db_engine` (session-scoped, disposes at teardown) + `db_session` fixtures. When adding tests, extend this pattern — do NOT mock SQLAlchemy / httpx / FastAPI.

### Authorization model (lands in PR-3; pinned now for engineering)

**OQ-1 (user-approved, pinned in ADR and PRD-3):** stranger → **404 on every verb**, never 403. For any list/item/share endpoint, if the caller lacks read permission → return 404 regardless of whether the resource exists. Prevents list-existence enumeration. Mixed 404/403 would reintroduce the leak.

Roles: `owner` (implicit, list creator), `editor` (full CRUD on items), `viewer` (read-only). Sharing is registered-users-only (no email-invite to non-users). Full matrix — 4 roles × 10 actions — is enumerated in `docs/planning/prd-3-sharing-permissions.md`.

## Test infrastructure discipline

Per `~/.claude/rules/coding-principles.md` (global user rule), services that expose endpoints MUST have integration tests that boot the real assembled app. This is enforced here via `tests/test_app_boots.py` + `conftest.py`. The CI `test-quality-gate` job greps for `@pytest.mark.skip`, empty test bodies, and `# type: ignore` in tests — don't introduce any of these.

TDD is mandatory: red → green → refactor. Bug fixes start with a failing test that reproduces the bug.

## Commit discipline

Every commit MUST have a 4-Ws body:
```
<short subject ≤50 chars>

Why: <problem or goal>

Considered:
- <alternative>: <why rejected>
- <chosen>: <why chosen>

Trade-offs:
- <consequence>

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

See any existing commit on `origin/feat/pr1-foundation` for exemplars. Planning-phase deliverables (PRDs/BSDs) and infrastructure changes (`.gitignore`) use the same format.

## Dependency management

Per `~/.claude/rules/dependency-sync.md`:
- **Always `uv add <pkg>`** for new backend deps (never edit `pyproject.toml` by hand)
- `uv.lock` is authoritative and committed; CI runs `uv sync --frozen`
- `backend/.python-version` pins `3.12` to match CI

## GitHub Actions hardening

All actions pinned to full 40-char commit SHAs (not `@v4`/`@v5` tags). When bumping, resolve the new SHA via `gh api repos/<owner>/<repo>/git/refs/tags/<tag>` and update the comment trailer.

## Known CI behavior

- CI triggers: `push` to `master`, and `pull_request` (any branch). Feature-branch pushes alone don't trigger CI — first fire is when a PR opens.
- `semgrep-cloud-platform/scan` (external Semgrep GitHub App check) takes 2-3 min to complete and reports independently of the workflow jobs.
- `gh pr edit` can fail with a "Projects (classic) is being deprecated" GraphQL error. Workaround for PR body updates: `gh api repos/<owner>/<repo>/pulls/<n> --method PATCH -f body="$(cat body.md)"`.
- `gh pr review --request-changes` fails on PRs authored by the same GitHub account as the authenticated user ("can't request changes on your own PR"). Fallback: `gh pr comment <n> --body-file <body>` — findings land on the PR as a persistent comment.
