# Resume State — shared-todos-app Initiative

**Saved:** 2026-04-19 23:46 America/New_York
**Reason for save:** User restarting session to enable Semgrep. All teammates + cron jobs will be lost on restart; this file captures everything needed to resume.

---

## One-line summary for the agent that resumes

> Read this file in full, then read `docs/initiatives/2026-04-19-shared-todos-app.md` (the approved memo). Phase 4 (Planning) is complete and committed. Phase 5 (polling loop) and Phase 6 (Engineering) are next — not yet started. Re-spawn the three leads + meta-auditor into a fresh `shared-todos-app` team, re-arm the meta-auditor sweep cron, then dispatch Phase 6 to engineering-lead.

---

## Initiative metadata

| Field | Value |
|-------|-------|
| Slug | `shared-todos-app` |
| Repo | https://github.com/iceman12276/shared-todos (public) |
| Branch | `master` |
| Latest commit at save | `0f5a521` (Add BSD-3) |
| Initiative memo | `docs/initiatives/2026-04-19-shared-todos-app.md` |
| Status | APPROVED (Phase 4 complete, Phase 5+6 pending) |

---

## Phases — state at save

| # | Phase | Status | Notes |
|---|-------|--------|-------|
| 0 | Prereqs + team create | ✅ complete | gh auth ✓, pentest tools ✓ (nmap/subfinder/whatweb/schemathesis), agents ✓ |
| 1 | CEO meeting | ✅ complete | 3 leads' perspectives captured in memo |
| 2 | Synthesize memo | ✅ complete | `docs/initiatives/2026-04-19-shared-todos-app.md` |
| 3 | User approval gate | ✅ complete | APPROVED; Q1–Q6 answered (see memo) |
| 4 | Planning (PRD + BSD) | ✅ complete | All 6 docs committed + pushed |
| 5 | Start polling loop | ⏸ **NOT STARTED** — next up | Was marked in_progress in TaskList but never dispatched |
| 6 | Engineering | ⏸ **NOT STARTED** — next up | Was marked in_progress in TaskList but never dispatched |
| 7 | Stop loop + release pentest | pending | Requires Semgrep (hence the restart) |
| 8 | Final release verdict | pending | - |
| 9 | Meta-audit + cleanup | pending | - |

---

## User's authoritative decisions (from memo — DO NOT re-litigate)

| Q | Decision |
|---|----------|
| Q1. Sharing target | **Registered-users-only.** No email-invite to non-users. |
| Q2. Permission roles | **Two roles: `viewer` (read-only) + `editor` (full CRUD on items).** Explicit in PRD-3 authz matrix. |
| Q3. Auth providers | **Email + password AND Google OAuth.** Both in v1. |
| Q4. Password reset | **IN v1.** Email service via mailhog/mailpit in dev/CI. |
| Q5. Realtime sync | **HARD REQUIREMENT.** Collaborators see live changes. Engineering picks transport (WS/SSE/etc). |
| Q6. GitHub remote | **Done.** Public repo at https://github.com/iceman12276/shared-todos. |

Revised effort estimate (from memo): planning 2–3d, engineering 3–4w (incl. ~1w for realtime), validation 7–10d, total ~4–5 weeks end-to-end.

---

## Phase 4 deliverables — all committed to master

### PRDs (under `docs/planning/`)

| File | Commit | Summary |
|------|--------|---------|
| `prd-1-auth.md` | `59a6a9c` | Auth: register, login (email+pwd, Google OAuth), session cookies, password reset with mailhog/mailpit, rate-limit, CSRF double-submit |
| `prd-2-lists-items.md` | `c74ae29` | Lists & items CRUD: field limits, cascade semantics, pagination |
| `prd-3-sharing-permissions.md` | `5e0a58d` | Sharing & permissions: explicit authz matrix (4 roles × 10 actions), 7 realtime events, per-list + per-user channels, UUID list IDs |

### BSDs (under `docs/planning/`)

| File | Commit | Lines | Summary |
|------|--------|-------|---------|
| `bsd-1-auth.md` | `f698c73` | 725 | Auth screens: register, login, OAuth, forgot/reset password — all states (loading/success/error/edge) + global design tokens |
| `bsd-2-lists-items.md` | `21b78fd` | 681 | Dashboard + list-detail + item interactions: empty/loading/populated/optimistic/conflict-resolved states, realtime-event rendering |
| `bsd-3-sharing-permissions.md` | `0f5a521` | 587 | Invite flow, member management, role badges, realtime presence + "recently updated by X" indicators, access-revoked UX |

### Supporting commits

- `71aaf67` — initial initiative memo
- `8b06e38` — `.gitignore` for `.claude/`

---

## Open questions carried forward

### OQ-1: 404 vs 403 for stranger access to a list (from PRD-3)

PM recommends **404** to prevent list-existence enumeration. Needs validation-lead confirmation in Phase 6. **Do not block engineering on this** — it's a response-code detail, not a spec-shaping question. Validation-lead should confirm during per-PR review of the first endpoint that returns this status.

---

## Team + agent state — everything below is LOST on restart, must be recreated

### Team
- Team name: `shared-todos-app`
- Config: `~/.claude/teams/shared-todos-app/config.json` (file may persist, but agents are dead)

### Teammates alive at save (all need re-spawn if work resumes with them)

| Name | Type | Role | Work done in prior session |
|------|------|------|----------------------------|
| planning-lead | planning-lead | Planning team lead | Drove PRDs + BSDs; PM ran into stale-resend loop late but was harmless |
| engineering-lead | engineering-lead | Engineering team lead | Gave CEO perspective; never actually kicked off implementation |
| validation-lead | validation-lead | Validation team lead | Gave CEO perspective; never activated |
| product-manager | product-manager | Wrote PRD-1/2/3 | Done. Phase 4 complete for PM. Probably don't re-spawn unless revisions needed. |
| ux-designer | ux-designer | Wrote BSD-1/2/3 + Figma wireframes | Done. Phase 4 complete for UX. Probably don't re-spawn unless revisions needed. |
| meta-auditor | meta-auditor | Roaming observer | Produced Sweep 1 (1 HIGH, 1 MED, 1 LOW) + Sweep 2 (1 MED). Findings are in their MEMORY.md — persists across sessions. |

### Cron jobs lost on restart

- `e2adfa09` (now cancelled) — meta-auditor sweep loop, fired every 2 min. **Re-arm after restart** if you want active sweeps again. The resume agent should decide whether to restart this.

---

## Task list (for reconstruction if TaskList state is lost)

```
#1  [completed]   Phase 1: CEO meeting with three leads
#2  [completed]   Phase 2: Synthesize CEO memo
#3  [completed]   Phase 3: User approval gate
#4  [completed]   Phase 4: Planning (PRD + BSD)
#5  [in_progress] Phase 5: Start validate-new-prs polling loop   ← resume HERE
#6  [in_progress] Phase 6: Engineering (backend + frontend)       ← resume HERE
#7  [pending]     Phase 7: Stop loop + release pentest
#8  [pending]     Phase 8: Final release verdict
#9  [pending]     Phase 9: Meta-audit + cleanup
#10 [completed]   Write PRD-2: Lists & Items CRUD
#11 [completed]   Write PRD-1: Auth
#12 [completed]   Write PRD-3: Sharing & Permissions
#13 [completed]   Write BSD-1: Auth flows
#14 [completed]   Write BSD-2: Lists dashboard + item interactions
#15 [completed]   Write BSD-3: Sharing UI + realtime indicators
```

Task store on disk (may persist across restart): `~/.claude/tasks/shared-todos-app/`

---

## Meta-auditor findings so far (from their session replies)

Full details in meta-auditor's MEMORY.md, but the high-level items to carry forward:

1. **[HIGH]** Planning-lead's briefing to PM told PM to commit/push, but PM allowlist doesn't allow Bash/git. Resolved by orchestrator committing on PM's behalf. **Action item for post-init:** either update PM/UX agent-file briefings to say "orchestrator will commit" OR update the allowlist. Documenting — don't mid-flight change.
2. **[MED]** Session churn — planning-lead + PM each had 10+ sessions re-doing spawn protocol. Token-expensive. Not blocking.
3. **[MED]** UX wrote BSDs to `bsd/` at repo root instead of `docs/planning/`. Orchestrator moved them pre-commit. Worth pinning explicit save-path in BSD briefing template.
4. **[LOW]** planning-lead doesn't invoke `mental-model` skill on spawn (engineering-lead + validation-lead do). Agent-file inconsistency.
5. **[LOW]** product-manager doesn't invoke `follow-the-plan` on spawn despite receiving directives. Agent-file tuning opportunity.

---

## Exact next actions for the resuming agent

When the user says "resume" or similar after restart:

1. **Verify prereqs again** (clean slate):
   - `gh auth status`
   - `which nmap subfinder whatweb schemathesis semgrep`  ← semgrep must now be present (that's why they restarted)
   - Verify `git remote get-url origin` returns the GitHub URL
   - `git log --oneline -3` should show the BSD-3 commit `0f5a521` at top

2. **Re-spawn the team:**
   ```
   TeamCreate(team_name: "shared-todos-app", agent_type: "orchestrator", ...)
   Agent(team_name: "shared-todos-app", name: "planning-lead",    subagent_type: "planning-lead",    run_in_background: true, prompt: "Respawned mid-initiative after a restart. Phase 4 complete. Stand by, no new work yet.")
   Agent(team_name: "shared-todos-app", name: "engineering-lead", subagent_type: "engineering-lead", run_in_background: true, prompt: "Respawned after restart. Initiative memo at docs/initiatives/2026-04-19-shared-todos-app.md, resume state at docs/initiatives/RESUME.md. Stand by for Phase 6 kickoff directive.")
   Agent(team_name: "shared-todos-app", name: "validation-lead",  subagent_type: "validation-lead",  run_in_background: true, prompt: "Respawned after restart. Stand by.")
   Agent(team_name: "shared-todos-app", name: "meta-auditor",     subagent_type: "meta-auditor",     run_in_background: true, prompt: "Respawned after restart. Your MEMORY.md has findings from the prior session — read it. Active sweep mode still applies (every 2 min, ≤80 word reports). Resume sweep loop when orchestrator tells you.")
   ```

3. **Skip Phase 5 skill auto-invoke** — the `validate-new-prs` polling loop skill needs to be re-started separately. Orchestrator should invoke:
   ```
   Skill(skill: "loop", args: "5m validate-new-prs")
   ```

4. **Re-arm the meta-auditor sweep cron** (optional — only if user wants active sweeps):
   ```
   CronCreate(cron: "*/2 * * * *", recurring: true, prompt: "Ping meta-auditor via SendMessage with 'Sweep #N — run the active-sweep checklist and reply with ≤80 word status' prompt (increment N each time)...")
   ```

5. **Dispatch Phase 6 to engineering-lead** (the meat of the resume):
   ```
   SendMessage(to: "engineering-lead", message: <full Phase 6 directive — memo path, PRD paths, BSD paths, implementation order backend-first then frontend, commit-discipline, OQ-1 flag>)
   ```

6. **Mark task #5 + #6 status accordingly** once polling loop + engineering are in flight.

---

## Phase 6 directive template (paste into engineering-lead brief on resume)

```
Initiative approved — begin engineering phase. Planning is complete.

**Memo:** docs/initiatives/2026-04-19-shared-todos-app.md
**PRDs:** docs/planning/prd-1-auth.md, prd-2-lists-items.md, prd-3-sharing-permissions.md
**BSDs:** docs/planning/bsd-1-auth.md, bsd-2-lists-items.md, bsd-3-sharing-permissions.md
**Repo:** https://github.com/iceman12276/shared-todos (master)

**Scope reminders from user decisions:**
- Registered-users-only sharing; viewer/editor roles; email+password + Google OAuth; password reset in v1; realtime sync HARD REQUIREMENT.
- Stack (from your CEO perspective): FastAPI/SQLAlchemy/Postgres backend, React/Vite/TanStack Query frontend, httpOnly SameSite=Lax session cookies.

**Your phase:**
1. Use `zero-micromanagement` before delegating.
2. Order: backend-first (API contract, CI scaffold in the first PR — do NOT defer CI), then frontend against BSDs + API contract.
3. Request spawn of backend-dev; delegate backend implementation per PRDs. Insist on TDD, commit-discipline, integration tests that boot the real app (from user's rules/coding-principles.md), per-endpoint authz matrix test covering {owner, editor, viewer, stranger} × {read, write, share, delete}.
4. When backend PRs are green + merged via polling-loop validation, spawn frontend-dev.
5. Carry forward OQ-1 (404 vs 403 for stranger access — validation-lead to confirm; don't block on it).
6. Polling loop is running in the background — every PR is auto-validated. Your job is implementation.
7. Report back when all PRs merged + feature-complete.

Use the spawn-request protocol — do not spawn workers yourself.
```

---

## Watch-outs for the resuming agent

- **Don't commit on behalf of planning workers again** — Phase 4 is done, so this shouldn't recur. If engineering workers hit a similar block, escalate — they should have Bash + git access per their agent files.
- **Stale-resend loop pattern** — planning-lead and PM both exhibited it; expect engineering workers might too. If a teammate re-sends the same "done" summary 3+ times, send them a direct "acknowledged, you're done, go idle" message; don't just wait it out.
- **Realtime is the highest-risk piece** of engineering. Insist on engineering-lead picking the transport (WS vs SSE vs Pusher-equivalent) and documenting the choice in a decision doc before implementation starts.
- **Authz matrix test is non-negotiable** — all three leads flagged IDOR as top risk.

---

## End of resume file.
