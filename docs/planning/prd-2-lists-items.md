# PRD-2: Todo Lists & Items CRUD

**Version:** 1.0
**Date:** 2026-04-19
**Status:** Draft
**Author:** product-manager

---

## Problem

Users who want to organize their tasks have no way to create, manage, or track todo lists and the items within them. Without a structured list-and-item model, the application has no core value unit to share, collaborate on, or act against. This is the central data surface of the product — without it, nothing else ships.

---

## Users

- **Primary:** Any authenticated user who wants to create and manage personal or collaborative todo lists.
- **Secondary:** Collaborators (editor/viewer roles) who interact with lists shared with them — covered in full in PRD-3, but the CRUD surface defined here is the foundation they operate on.

---

## Goals

- An authenticated user can create a named todo list and becomes its owner.
- An authenticated user can rename or delete any list they own.
- An authenticated user can create items inside a list, each with a title, a done/undone state, and optional notes.
- An authenticated user can update any item on a list they have write access to (title, notes, done state).
- An authenticated user can delete any item on a list they have write access to.
- An authenticated user can view all of their own lists from a single dashboard.
- An authenticated user can view all items within a specific list.
- The UI is desktop-first and responsive (mobile is a stretch goal, not a v1 requirement).

---

## Non-Goals

- Subtasks (items nested inside items).
- Labels, tags, or categories on items.
- Due dates on items.
- File attachments on items.
- Comments or mentions on items.
- Sorting or ordering beyond creation order.
- Filtering or search within a list.
- Bulk operations (bulk-complete, bulk-delete).
- List templates or duplication.
- Archived lists.
- Any realtime sync behavior — that is specified in PRD-3 (Sharing & Permissions) and applies only to the shared-list scenario.

---

## User Stories

### US-201: Create a list

**Description:** As an authenticated user, I want to create a new todo list with a name so that I can start organizing tasks.

**Dependencies:** None

**Acceptance Criteria:**
- [ ] A user can submit a list name (1–200 characters, non-blank after trimming) via a create-list action.
- [ ] On success, the new list appears in the user's list dashboard immediately.
- [ ] The authenticated user becomes the owner of the list.
- [ ] An empty list name or a name exceeding 200 characters is rejected with a descriptive validation error; no list is created.

---

### US-202: View all my lists

**Description:** As an authenticated user, I want to see all lists I own or have access to so that I can navigate to the one I want.

**Dependencies:** None

**Acceptance Criteria:**
- [ ] The dashboard displays all lists the user owns.
- [ ] The dashboard also displays lists shared with the user (viewer or editor role) — with a visual indicator distinguishing shared lists from owned lists.
- [ ] Each list entry shows: list name, owner name (if shared), and item count.
- [ ] Lists are ordered by most-recently-updated descending.
- [ ] If the user has no lists, an empty state with a prompt to create one is shown.

---

### US-203: Rename a list

**Description:** As the owner of a list, I want to rename it so that I can keep its name accurate as its purpose evolves.

**Dependencies:** US-201

**Acceptance Criteria:**
- [ ] The owner can submit a new name for a list they own (1–200 characters, non-blank).
- [ ] The updated name is reflected in the dashboard and list detail view immediately after save.
- [ ] A non-owner (editor, viewer, stranger) attempting to rename a list receives a 403 error; the list name is not changed.
- [ ] An empty or >200-character name is rejected with a validation error; the existing name is preserved.

---

### US-204: Delete a list

**Description:** As the owner of a list, I want to delete a list I no longer need.

**Dependencies:** US-201

**Acceptance Criteria:**
- [ ] The owner can permanently delete a list they own.
- [ ] Deleting a list also deletes all items within it (cascade delete) and removes all share relationships associated with it.
- [ ] The deleted list no longer appears in any dashboard, including collaborators' dashboards.
- [ ] A non-owner (editor, viewer, stranger) attempting to delete a list receives a 403 error; the list and its items are not affected.
- [ ] A confirmation step is required before deletion (e.g., confirmation dialog) — to prevent accidental data loss.

---

### US-205: Create an item

**Description:** As a user with write access to a list (owner or editor), I want to add an item so I can track a task.

**Dependencies:** US-201

**Acceptance Criteria:**
- [ ] A user with owner or editor access can add an item to a list with a title (1–500 characters, non-blank).
- [ ] Notes field is optional; maximum 2000 characters if provided.
- [ ] New items default to done=false (not completed).
- [ ] The new item appears in the list immediately after creation.
- [ ] A viewer or stranger attempting to create an item receives a 403 error; no item is created.
- [ ] An empty or >500-character title is rejected with a validation error; no item is created.

---

### US-206: View items in a list

**Description:** As a user with at least viewer access to a list, I want to see all items in the list so I can understand what's tracked.

**Dependencies:** US-201, US-205

**Acceptance Criteria:**
- [ ] A user with owner, editor, or viewer access can view the full item list for a given list.
- [ ] Each item displays: title, done state (checked/unchecked), and notes (if present).
- [ ] Items are ordered by creation time ascending (oldest first) by default.
- [ ] A stranger (no access relationship) attempting to view items receives a 403 error.

---

### US-207: Toggle item done state

**Description:** As a user with write access to a list, I want to mark an item as done or undone so I can track completion.

**Dependencies:** US-205

**Acceptance Criteria:**
- [ ] A user with owner or editor access can toggle any item's done state.
- [ ] The updated done state is reflected immediately in the UI.
- [ ] A viewer or stranger attempting this action receives a 403 error; the item state is not changed.

---

### US-208: Edit item title or notes

**Description:** As a user with write access to a list, I want to edit an item's title or notes so I can correct or refine task details.

**Dependencies:** US-205

**Acceptance Criteria:**
- [ ] A user with owner or editor access can update an item's title (1–500 characters, non-blank after trim) or notes (0–2000 characters).
- [ ] The updated values are reflected in the UI immediately after save.
- [ ] A viewer or stranger attempting to edit an item receives a 403 error; the item is not changed.
- [ ] An empty or >500-character title is rejected with a validation error; the existing title is preserved.

---

### US-209: Delete an item

**Description:** As a user with write access to a list, I want to delete an item I no longer need.

**Dependencies:** US-205

**Acceptance Criteria:**
- [ ] A user with owner or editor access can permanently delete an item from a list.
- [ ] The item no longer appears in the list after deletion.
- [ ] A viewer or stranger attempting to delete an item receives a 403 error; the item is not affected.

---

## Success Metrics

- 100% of API routes for list and item CRUD have integration tests hitting the real assembled app (not mocked handlers).
- Authorization matrix for owner/editor/viewer/stranger × all CRUD actions is explicitly tested (aligns with PRD-3 authz matrix).
- A user can complete the full list lifecycle (create list → add 3 items → complete 1 → delete 1 → rename list → delete list) in under 60 seconds via the UI with no errors.
- Zero uncaught server errors (500s) on valid requests in the happy path.

---

## Constraints

- **Auth required:** All list and item endpoints require an authenticated session. Unauthenticated requests receive a 401.
- **Ownership enforcement:** Only the owner may rename or delete a list. Row-level checks at the database query layer, not just middleware.
- **Character limits are enforced on both client and server** — client validation is UX; server validation is the authoritative gate.
- **Desktop-first layout:** The UI must be fully functional on desktop (1280px+). Mobile responsiveness is a stretch goal.
- **No cascade partial failure:** Deleting a list must cascade atomically — if any part of the cascade fails, the whole delete is rolled back and an error is returned.

---

## Open Questions

None. All ambiguous decisions were resolved in the initiative memo (2026-04-19):
- Item metadata scope (no due dates, no labels, no subtasks) — confirmed out of v1.
- Access roles (owner/editor/viewer) — defined; full authz matrix in PRD-3.
- Realtime sync — specified in PRD-3 (items created/updated/deleted by collaborators propagate live).
