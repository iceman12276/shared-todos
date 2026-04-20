# Resume State — shared-todos-app Initiative (Restart #2)

**Saved:** 2026-04-19 ~23:46 America/New_York (second restart)
**Reason for this save:** engineering-lead's frontmatter added `Bash` (at `~/.claude/agents/engineering-lead.md`), but the harness caches subagent-type tool lists at session start — so even a mid-session respawn doesn't pick up the new Bash tool. A full Claude Code session restart is needed so the subagent registration re-reads the updated .md file.

---

## One-line summary for the agent that resumes

> Read this file in full, then read `docs/initiatives/2026-04-19-shared-todos-app.md` (the approved memo). Phase 4 complete. Phase 6 is IN PROGRESS: `feat/pr1-foundation` is pushed to origin (commits `895bd1b` ADR + `c73324e` CI), 2 commits ahead of master. First CI run has been triggered on the branch push. No PR yet. After respawn engineering-lead has Bash natively — first action is to verify Bash works, then brief backend-dev to add the FastAPI skeleton on top of these two commits. Once backend-dev is done, open PR-1.

---

## Initiative metadata

| Field | Value |
|-------|-------|
| Slug | `shared-todos-app` |
| Repo | https://github.com/iceman12276/shared-todos (public) |
| Main working tree | `/home/isaac/Desktop/dev/shared-todos` |
| PR-1 worktree | `/home/isaac/Desktop/dev/shared-todos-pr1` (branch `feat/pr1-foundation`) |
| master HEAD (pushed) | `4ab5612` — Add RESUME.md |
| feat/pr1-foundation HEAD (pushed to origin) | `c73324e` — Add CI: backend + test-quality + security gates |
| Initiative memo | `docs/initiatives/2026-04-19-shared-todos-app.md` |
| Status | APPROVED — Phase 4 complete, Phase 6 in progress |

---

## Phases — state at save

| # | Phase | Status | Notes |
|---|-------|--------|-------|
| 0 | Prereqs + team create | ✅ complete | |
| 1 | CEO meeting | ✅ complete | |
| 2 | Synthesize memo | ✅ complete | |
| 3 | User approval gate | ✅ complete | |
| 4 | Planning (PRD + BSD) | ✅ complete | |
| 5 | Start polling loop | ⏸ paused | Cron loop running before pause; re-arm on resume |
| 6 | Engineering | 🚧 IN PROGRESS | ADR committed locally; CI authored-not-committed; backend-dev unbriefed |
| 7 | Pentest | pending | Semgrep now installed ✓ |
| 8 | Final verdict | pending | |
| 9 | Meta-audit + cleanup | pending | |

---

## User's authoritative decisions (unchanged from prior RESUME)

| Q | Decision |
|---|----------|
| Q1. Sharing target | Registered-users-only |
| Q2. Permission roles | Two roles: `viewer` (read-only) + `editor` (full CRUD on items) |
| Q3. Auth providers | Email + password AND Google OAuth |
| Q4. Password reset | IN v1 |
| Q5. Realtime sync | HARD REQUIREMENT |
| Q6. GitHub remote | https://github.com/iceman12276/shared-todos (public) |

### Additional pinned rules surfaced during Phase 6 kickoff

- **OQ-1 RESOLVED by validation-lead:** stranger → 404 on EVERY verb (GET, PATCH, POST, DELETE, share, revoke — every action against a list the caller can't read). NEVER 403. Mixed 404/403 reintroduces list-existence enumeration. This is a hard rule for backend-dev's authz implementation.
- **Realtime transport DECIDED by engineering-lead** (documented in ADR `895bd1b`): WebSocket over `/ws/v1/lists/{list_id}` + per-user channel `/ws/v1/user`, fan-out via Postgres LISTEN/NOTIFY inside the backend process. Single-backend-replica ceiling accepted for v1. Channel abstraction to be swap-ready for Redis pub/sub at v2.

---

## Git state — CRITICAL for resume

### Committed to master (pushed to origin)
- `4ab5612` Add RESUME.md (prior save)
- `0f5a521` Add BSD-3
- `21b78fd` Add BSD-2
- `f698c73` Add BSD-1
- `8b06e38` Ignore .claude/
- `5e0a58d` Add PRD-3
- `59a6a9c` Add PRD-1
- `c74ae29` Add PRD-2
- `71aaf67` Initiative memo

### Pushed to `origin/feat/pr1-foundation` (2 commits ahead of master)
- `895bd1b` Add ADR: WebSocket + Postgres NOTIFY for realtime
  - Path: `docs/architecture/realtime-transport-decision.md` (171 lines)
  - Authored by engineering-lead; committed via orchestrator (Option B — eng-lead didn't have Bash yet)
- `c73324e` Add CI: backend + test-quality + security gates
  - Path: `.github/workflows/ci.yml` (181 lines)
  - 3 parallel jobs: backend (ruff/mypy/pytest with real Postgres + mailhog), test-quality (grep-based skip-discipline), security-gate (Semgrep p/default+p/python+p/owasp-top-ten+p/secrets, Gitleaks)
  - Frontend lane deferred until frontend-dev starts
  - Authored by engineering-lead; committed via orchestrator (Option B)

### Remote branches
- `origin/master` @ 2384458 (RESUME.md v2 update — will advance to v3 when this file is re-committed)
- `origin/feat/pr1-foundation` @ c73324e (2 commits ahead of master; first CI run triggered on push)
- No PR open yet — next PR-1 will be opened by engineering-lead or backend-dev once the FastAPI skeleton lands on top of these two commits

---

## Config + agent file changes (persisted; survive restart)

All applied mid-session:

### `~/.claude/hooks/domain-config.yaml`
- **backend-dev**: added `backend/**`, `**/backend/**`, `pyproject.toml`, `**/pyproject.toml`, `uv.lock`, `**/uv.lock`, `.python-version`, `**/.python-version`, `docker-compose.yml`, `**/docker-compose.yml`, `docker-compose.*.yml`, `**/docker-compose.*.yml`
- **frontend-dev**: added `frontend/**`, `**/frontend/**`, `package.json`, `**/package.json`, `package-lock.json`, `**/package-lock.json`, `.nvmrc`, `**/.nvmrc`, `vite.config.ts`, `**/vite.config.ts`, `tsconfig*.json`, `**/tsconfig*.json`
- **engineering-lead**: was memory-only; now has `docs/architecture/**`, `**/docs/architecture/**`, `.github/workflows/**`, `**/.github/workflows/**`

### `~/.claude/hooks/skills-config.yaml`
- Added `commit-discipline` to: product-manager, ux-designer, security-reviewer, pentester, validation-lead, meta-auditor, **engineering-lead**

### `~/.claude/hooks/tools-config.yaml`
- Added `Bash` to: ux-designer, pentester, validation-lead (security-reviewer + meta-auditor already had it; backend-dev/frontend-dev already have it)

### `~/.claude/agents/*.md` — body updates
- All 7 agents (product-manager, ux-designer, security-reviewer, pentester, validation-lead, meta-auditor, **engineering-lead**): added `**Before committing your deliverable:** invoke commit-discipline` trigger line + updated `Your skills:` list.
- **engineering-lead.md**: body expanded with the ownership-exception paragraph (`docs/architecture/**` + `.github/workflows/**` now explicit carve-outs from "you never write code").

### `~/.claude/agents/engineering-lead.md` — FRONTMATTER
- Added `- Bash` to the `tools:` list.
- **This is the change requiring the full session restart** — the harness caches subagent-type tool lists at session start, so this Bash addition only takes effect on a fresh Claude Code session.

---

## Team + agent state — LOST on restart

All teammates will need re-spawn. Their persistent memory (`~/.claude/agent-memory/<agent>/MEMORY.md`) survives.

### At save time (all paused + idle)
| Name | Status at pause | Last notable action |
|------|-----------------|---------------------|
| planning-lead | idle, holding | Acked PAUSE |
| engineering-lead | idle, holding | Authored ADR + ci.yml, blocked on Bash, idled after orchestrator said "go Option B" |
| validation-lead | idle, holding | Orientation done; will fire per-PR validation pipeline when polling loop dispatches |
| meta-auditor | idle, holding | 13 sweeps completed; memory loaded with findings; watching for first real commit |
| backend-dev | idle, holding | Feat branch created, Python 3.12 confirmed, worktree exists; waiting for eng-lead's kickoff |

### Cron jobs lost on restart
Both were running before the pause:
- meta-auditor sweep loop (2-min cadence). Sweep counter was at #13 (next would be #14).
- validate-new-prs polling loop (5-min cadence).

---

## Exact next actions for the resuming agent

1. **Verify prereqs**:
   - `gh auth status`
   - `which semgrep nmap subfinder whatweb schemathesis`
   - `git remote get-url origin`
   - `git log --oneline -3` — should show `4ab5612` at top of master
   - `git branch -a` — should show local `feat/pr1-foundation` pointing at `895bd1b`
   - `ls /home/isaac/Desktop/dev/shared-todos-pr1/.github/workflows/ci.yml` — should exist

2. **Re-create the team** via TeamCreate(team_name: "shared-todos-app", ...).

3. **Re-spawn 5 teammates** (skip PM + UX; their work is done):
   - `planning-lead` — "Respawned after 2nd restart. Phase 4 complete; stand by."
   - `engineering-lead` — "Respawned after 2nd restart. You NOW HAVE `Bash` in your tool surface. Phase 6 in progress: `feat/pr1-foundation` pushed to origin with two commits ahead of master (`895bd1b` ADR + `c73324e` CI). Your first action: verify Bash works via `git status -sb` smoke test. If Bash confirmed, brief backend-dev to add the FastAPI skeleton ON TOP of these two commits (backend/ package layout, pyproject.toml, /health endpoint with integration test that boots the real app). Once backend-dev's work is on the branch with CI green, open PR-1 via `gh pr create`."
   - `validation-lead` — "Respawned. Stand by for per-PR validation dispatch from the polling loop."
   - `meta-auditor` — "Respawned. Read your MEMORY.md for prior findings. Sweep counter was at #13; next is #14. Active sweep mode: orchestrator will restart the 2-min cron."
   - `backend-dev` — "Respawned. Worktree exists at /home/isaac/Desktop/dev/shared-todos-pr1. Branch `feat/pr1-foundation` local. Python 3.12 confirmed. Stand by for engineering-lead's kickoff brief once they push the ADR + CI."

4. **Re-arm both cron loops**:
   - `CronCreate("*/2 * * * *", recurring: true, prompt: "Ping meta-auditor with 'Sweep #N' — N starts at 14 and increments each fire")`
   - `CronCreate("*/5 * * * *", recurring: true, prompt: "validate-new-prs")`

5. **Watch for engineering-lead's first action**: they should invoke `commit-discipline`, then Bash git commands natively. Verify Bash is now actually enabled; if they still report Bash missing, the frontmatter edit didn't take effect and something is wrong — stop and investigate.

6. **Once feat/pr1-foundation is pushed**: polling loop will NOT pick it up (no PR yet — just a branch). That's fine. backend-dev builds on top, then eng-lead or backend-dev opens PR-1.

---

## Drafted CI YAML commit body (engineering-lead's context)

Engineering-lead had drafted the CI YAML and was preparing a COMMIT_REQUEST for it when Bash was discovered missing. After respawn with Bash present, they should compose and commit the CI YAML themselves via their own `commit-discipline` + Bash workflow. No need to pre-draft here — they know what they wrote.

If they need a nudge on format, the template for the ADR commit (commit `895bd1b`) is the exemplar for the CI YAML commit body:
- Subject: `Add CI: <one-line description>` (≤50 chars)
- Why: connect to a PRD/BSD/memo requirement
- Considered: alternatives evaluated (other CI configs, deferring CI, etc.)
- Trade-offs: runtime cost, coverage gaps, flakiness risks, etc.
- `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>` trailer

---

## Task list at save

```
#1 [in_progress] Phase 5: validate-new-prs polling loop
#2 [in_progress] Phase 6: Engineering (backend + frontend)   ← owner: engineering-lead
#3 [pending]     Phase 7: Stop loop + release pentest
#4 [pending]     Phase 8: Final release verdict
#5 [pending]     Phase 9: Meta-audit + cleanup
#6 [completed]   Author realtime-transport-decision.md
#7 [completed]   Author .github/workflows/ci.yml (backend lane + quality gates)
#8 [pending]     Commit + push arch doc and CI workflow to feat/pr1-foundation   ← ADR done (895bd1b), CI pending
#9 [pending]     Brief backend-dev to start FastAPI skeleton
```

Task store on disk: `~/.claude/tasks/shared-todos-app/`. Should survive restart, but verify via TaskList after team re-create.

---

## Watch-outs

- **Bash test first for eng-lead on respawn:** before briefing them on Phase 6, have them verify Bash is actually available (`git status` as a smoke test). If missing still, the frontmatter edit didn't persist — abort and fix the .md before continuing.
- **feat/pr1-foundation has ONE commit ahead of master already** — the ADR `895bd1b`. Don't lose this. Any "reset/rebuild the branch" impulse should be rejected.
- **Stale system prompts won't bite now**: all agents respawning post-restart will load the updated .md files fresh.
- **Sweep counter continuity:** meta-auditor's MEMORY.md has sweeps #1–#13. Tell them #14 is next on respawn.
- **Don't re-do the config changes:** domain/skills/tools configs are all on-disk and correct. Just verify on resume; don't re-edit.

---

## End of resume file (v2).
