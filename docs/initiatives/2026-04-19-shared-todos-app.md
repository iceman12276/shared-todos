# Initiative: Shared Todos Web App

**Date:** 2026-04-19
**Status:** APPROVED (2026-04-19)
**Slug:** `shared-todos-app`
**Objective (user verbatim):** Build a shared todos web app where users can register, log in, create todo lists and items, and share lists with other users.

---

## Perspectives

### Planning (planning-lead)

**PRDs & BSDs needed:**
- PRD-1: Auth (register, login, session, password reset?) — small
- PRD-2: Todo lists & items CRUD — small/medium
- PRD-3: Sharing & permissions (invite, roles, revoke) — medium, highest ambiguity
- BSD-1: Auth flows (screens, validation, error states)
- BSD-2: Lists dashboard + item interactions
- BSD-3: Sharing UI (invite, member list, permission badges)

**Informing context:** None — greenfield. Anchor on generic conventions (Todoist, Google Keep sharing model).

**Ambiguities blocking planning:**
- Sharing model: invite-by-email to non-users, or registered-users-only?
- Permission levels: view-only vs. edit, or single "shared = edit"?
- Realtime sync across collaborators, or refresh-to-see?
- Mobile-responsive at launch, or desktop-first?
- Auth: email+password only, or OAuth providers?

**Effort:** ~2 days (PM day 1 → 3 PRDs; UX day 2 → 3 BSDs).

**Product risks:** Sharing scope creep (realtime/notifications/comments); auth rabbit hole (OAuth/MFA); team-account vs individual-sharing ambiguity.

### Engineering (engineering-lead)

**Feasibility:** High. Textbook CRUD + auth + sharing; no novel tech. Greenfield is a plus.

**Architecture:** Monorepo with two services:
- `backend/` — Python/FastAPI + SQLAlchemy + Postgres + Alembic
- `frontend/` — TypeScript/React + Vite + TanStack Query
- Auth via httpOnly session cookies (SameSite=Lax, CSRF-safe, simpler than JWT for this scope)

**Effort:** 2–3 weeks end-to-end.
- Backend: 5–7 days
- Frontend: 5–7 days
- CI + E2E: 2–3 days

**Risks:**
- Authorization model (owner/viewer/editor) needs tight row-level checks — easy to leak
- No test infra exists — CI scaffold is day-one work
- User lookup for sharing is a user-enumeration surface (validation will flag)

**External deps:** Postgres (Docker), bcrypt/argon2, std libs. Nothing exotic.

### Validation (validation-lead)

**Test scope:**
- Unit: auth helpers, authz checks, share-permission resolver
- Integration: every route responds (boot-real-app), DB constraints, migration up/down
- E2E: register → login → create list → invite collaborator → collaborator edits → revoke → confirm access gone
- Edge cases: self-share, share to non-existent user, email-enumeration, concurrent edits, revoked sessions, CSRF, pagination IDOR

**Security angles:** Auth (password storage, session, reset flow, rate-limit), authz (IDOR is THE class-of-bug), multi-tenant data isolation, CSRF, XSS on todo content, email injection on invites. **Pentest REQUIRED at release.**

**Release-readiness:** Integration tests cover every route; authz matrix test (owner/collaborator/viewer/stranger × read/write/share/delete); Semgrep + dep-audit clean; pentest report with no High/Critical open; structured logging on auth + share events.

**Validation effort:** ~5–7 days (per-PR reviews continuous; pentest ~1.5 days at release).

**Flag:** Pin the authz matrix (roles × actions) in PRD-3 BEFORE coding. Ambiguity here = IDOR bugs later.

---

## Synthesized Plan

### Scope

**In (v1):**
- User registration + login (email + password; password reset deferred decision)
- Create/read/update/delete todo lists
- Create/read/update/delete todo items within a list (title, done/undone, optional notes)
- Share a list with another registered user by email or username
- Permission roles on shares: decision needed (`viewer`/`editor` or single `collaborator`)
- Revoke a share
- Desktop-first responsive layout (mobile parity is a stretch goal)

**Out (v1):**
- Realtime sync / websockets (refresh-to-see-changes is acceptable v1)
- OAuth providers
- MFA
- Comments, mentions, notifications
- File attachments
- Subtasks, labels, due dates (unless resolved in PRD)
- Mobile apps

### Phases

1. **Planning (~2 days)** — product-manager writes PRD-1/2/3; ux-designer writes BSD-1/2/3. Authz matrix locked in PRD-3.
2. **Engineering (~2–3 weeks)** — backend-dev builds API against PRD (FastAPI + Postgres), then frontend-dev builds UI against BSD + API contract.
3. **Validation (continuous)** — per-PR polling loop dispatches pr-review-toolkit + security-reviewer + qa-engineer as PRs open. Shannon-pentest at release.

### Consolidated Risks

1. **Authorization/IDOR** (all three leads flagged) — tight row-level checks + authz matrix tests are non-negotiable
2. **Sharing scope creep** (planning, engineering) — cap ambition at v1 roles + invite + revoke; defer realtime
3. **User enumeration** on share-by-email lookup (engineering, validation) — needs deliberate countermeasure
4. **No GitHub remote configured** (infrastructure) — engineering needs a remote before PRs can flow through the validation polling loop
5. **No test infrastructure exists** (engineering) — CI scaffold must ship in the first backend PR, not deferred

### Success Criteria

- All three PRDs + BSDs approved before engineering starts
- Every API route has an integration test hitting the real app
- Authz matrix test covers {owner, editor, viewer, stranger} × {read, write, share, delete}
- Pentest report at release has zero High/Critical findings open
- A user can execute the full happy path (register → list → invite → collaborate → revoke) in a Playwright E2E test without manual fixup

### Open Questions For The User (MUST resolve before Phase 4)

**Q1. Sharing target.** Share by email to *anyone* (auto-create pending invite if recipient not registered), OR registered-users-only (share requires recipient's account to already exist)?

**Q2. Permission roles.** Two roles (`viewer` = read-only, `editor` = full CRUD on items), OR single `collaborator` role = full edit?

**Q3. Auth providers.** Email + password only for v1, OR include Google OAuth?

**Q4. Password reset.** Include in v1 (needs email service), OR defer to v2?

**Q5. Realtime sync.** Confirm OK to defer (refresh-to-see), OR is realtime a hard requirement?

**Q6. GitHub remote.** Do you want me to create a GitHub repo + push `master` as part of Phase 6 setup, or will you create the remote manually before engineering begins? (Required for the per-PR validation polling loop.)

---

## User Decision

- [x] **APPROVED** — proceed with pipeline (2026-04-19)

### Answers to open questions (authoritative for planning + engineering)

- **Q1. Sharing target** → **Registered users only.** No invite-by-email for non-users. Share requires the recipient's account to already exist.
- **Q2. Permission roles** → **Two roles: `viewer` (read-only) and `editor` (full CRUD on items).** Authz matrix in PRD-3 must enumerate roles × actions explicitly.
- **Q3. Auth providers** → **Email + password AND Google OAuth.** Both in v1.
- **Q4. Password reset** → **In v1.** Needs email service (mailhog/mailpit for local/CI; real provider for prod).
- **Q5. Realtime sync** → **HARD REQUIREMENT.** Collaborators see each other's edits without manual refresh. Engineering must select a sync mechanism (websockets / SSE / channel-based broadcast) and document trade-offs. **This is a scope expansion from the original estimate — planning + engineering should revise effort upward.**
- **Q6. GitHub remote** → Orchestrator creates the repo + pushes `master` now, before engineering begins. No dependency on user.

### Scope adjustments from user answers

**Added to v1:**
- Google OAuth (in addition to email + password)
- Password reset flow (requires email service)
- **Realtime sync** (collaborators see each other's changes live)

**Revised effort estimate (rough):**
- Planning: 2–3 days (PRDs now cover OAuth + reset + realtime design; authz matrix pinned in PRD-3)
- Engineering: 3–4 weeks (realtime adds ~5–7 days: channels, WS/SSE server, client integration, reconnection, per-list subscription scoping)
- Validation: 7–10 days (adds realtime race-condition testing, OAuth flow verification, email-sink E2E for reset, websocket security review)
- Total: ~4–5 weeks end-to-end
