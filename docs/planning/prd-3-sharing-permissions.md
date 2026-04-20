# PRD-3: Sharing & Permissions

**Version:** 1.0
**Date:** 2026-04-19
**Status:** Draft
**Author:** product-manager

---

## Problem

A todo list is only as useful as the collaboration it enables. Users who want to coordinate tasks with others — household members, teammates, project partners — have no way to grant another person access to a list, define what they can do with it, or revoke that access. Without a sharing model, the app is single-player only.

Sharing is also the highest-risk feature surface in the product. Incorrect authorization logic — even a single missing row-level check — can allow any user to read, modify, or delete another user's private data (IDOR). This PRD pins the authorization contract explicitly so that engineering and validation work from the same truth.

---

## Users

- **Primary (sharer):** The owner of a list who wants to grant another registered user access to it.
- **Primary (collaborator):** A registered user who has been granted access to another user's list.
- **Secondary (stranger):** Any authenticated user who has no share relationship with a given list — they must be denied all access to it.

---

## Goals

- A list owner can share their list with any other registered user by that user's email or username.
- A list owner can assign one of two roles when sharing: `viewer` (read-only) or `editor` (full item CRUD).
- A list owner can change a collaborator's role after the fact (promote viewer → editor, or demote editor → viewer).
- A list owner can revoke a collaborator's access at any time.
- Authorization is enforced at the row level on every API request — not just at the route level.
- Collaborators see live updates to lists they are currently viewing without requiring a manual refresh (realtime sync — see Realtime Sync Semantics section).
- A collaborator whose access is revoked mid-session loses access immediately — no grace period.

---

## Non-Goals

- Sharing with users who are not yet registered (no pending/invite-by-email-to-stranger flow).
- Public/link-based sharing (no "share a link, anyone with the link can view").
- Team or group sharing (sharing with a group of users in one action).
- Transferring list ownership.
- Nested or inherited permissions (permissions apply to the list as a whole, not to individual items).
- Notifications (in-app or email) when a list is shared with you.
- Realtime notifications of a new share arriving (polling-based share discovery is acceptable v1 — the shared list appears on the collaborator's dashboard on next load or refresh of the dashboard).

---

## Roles

| Role | Definition |
|------|------------|
| `owner` | The user who created the list. There is exactly one owner per list at all times. Ownership is not transferable in v1. |
| `editor` | A user who has been granted editor access by the owner. Can read the list and perform full CRUD on items. Cannot manage shares or delete the list. |
| `viewer` | A user who has been granted viewer access by the owner. Can read the list and its items. Cannot create, update, or delete items. Cannot manage shares or delete the list. |
| `stranger` | Any authenticated user with no share relationship with the list. Has no access to the list whatsoever. |

---

## Authorization Matrix

This table is the authoritative contract for row-level enforcement. Every cell must be implemented and tested. "ALLOW" means the request succeeds. "DENY" means a 403 Forbidden is returned and no data is modified.

| Action | `owner` | `editor` | `viewer` | `stranger` |
|--------|---------|----------|----------|------------|
| `read_list` (view list metadata, e.g., name) | ALLOW | ALLOW | ALLOW | DENY |
| `list_items` (view items in the list) | ALLOW | ALLOW | ALLOW | DENY |
| `create_item` | ALLOW | ALLOW | DENY | DENY |
| `update_item` (title, notes, done state) | ALLOW | ALLOW | DENY | DENY |
| `delete_item` | ALLOW | ALLOW | DENY | DENY |
| `rename_list` | ALLOW | DENY | DENY | DENY |
| `share_list` (grant access to a new collaborator) | ALLOW | DENY | DENY | DENY |
| `change_collaborator_role` | ALLOW | DENY | DENY | DENY |
| `revoke_share` | ALLOW | DENY | DENY | DENY |
| `delete_list` | ALLOW | DENY | DENY | DENY |

**Notes on the matrix:**
- Unauthenticated requests (no valid session) receive 401, not 403, and are not represented in this table.
- The owner cannot be removed from their own list via the revoke_share action — attempting to revoke the owner's access is a no-op or returns a descriptive error.
- An editor cannot escalate their own role. Only the owner can change roles.
- All DENY cells must be tested by the authz matrix test suite in QA (see Success Metrics).

---

## User Stories

### US-301: Share a list with another registered user

**Description:** As the owner of a list, I want to share it with another registered user by their email or username, assigning them a role, so they can collaborate with me.

**Dependencies:** US-201 (list exists), US-101 (recipient account exists)

**Acceptance Criteria:**
- [ ] The owner can enter another user's email address or username in a share dialog.
- [ ] If the email/username matches exactly one registered account, a share relationship is created with the specified role (`viewer` or `editor`).
- [ ] If the email/username matches no registered account, a generic error is shown: "No account found." The response must not distinguish "no account" from "found but can't share" — avoid leaking user enumeration signal.
- [ ] The shared list appears on the collaborator's dashboard the next time they load or refresh it.
- [ ] The owner cannot share the list with themselves — self-share is rejected with a descriptive error.
- [ ] A list cannot be shared with the same user twice. If a share relationship already exists for that user, the request is rejected with a descriptive error prompting the owner to use "change role" instead.
- [ ] A non-owner attempting to share a list receives a 403; no share is created.

---

### US-302: View collaborators on a list

**Description:** As the owner of a list, I want to see who has access to it and what their roles are.

**Dependencies:** US-301

**Acceptance Criteria:**
- [ ] The owner can view a list of current collaborators showing: display name/email and role (`viewer` or `editor`).
- [ ] A non-owner (editor, viewer, stranger) cannot view the collaborator list for a list they do not own — returns 403.

---

### US-303: Change a collaborator's role

**Description:** As the owner, I want to promote or demote a collaborator's role so I can adjust their access as the project evolves.

**Dependencies:** US-301

**Acceptance Criteria:**
- [ ] The owner can change an existing collaborator's role from `viewer` to `editor` or from `editor` to `viewer`.
- [ ] The role change takes effect immediately — the collaborator's next API request reflects the new role.
- [ ] If the collaborator is currently in an active session, their realtime channel subscription is updated to reflect the new role without requiring them to reload (see Realtime Sync Semantics).
- [ ] A non-owner attempting a role change receives a 403; the role is not changed.

---

### US-304: Revoke a collaborator's access

**Description:** As the owner, I want to remove a collaborator's access to my list so I can control who can see or edit it.

**Dependencies:** US-301

**Acceptance Criteria:**
- [ ] The owner can revoke any collaborator's access.
- [ ] Revocation takes effect immediately server-side: the revoked user's next API request to that list returns 403.
- [ ] If the revoked collaborator is currently viewing the list in an active session, they receive a real-time "access revoked" event that removes the list from their view without requiring a reload (see Realtime Sync Semantics).
- [ ] The list no longer appears on the revoked collaborator's dashboard.
- [ ] A non-owner attempting to revoke access receives a 403.

---

### US-305: Access a shared list as a collaborator

**Description:** As a collaborator (editor or viewer), I want to access a list that has been shared with me so I can view or edit it according to my role.

**Dependencies:** US-301

**Acceptance Criteria:**
- [ ] A collaborator can navigate to a shared list and view its items.
- [ ] An editor can perform all item CRUD operations (US-205 through US-209).
- [ ] A viewer can view items but all create/update/delete item actions are disabled in the UI and rejected with 403 at the API level.
- [ ] A stranger navigating to any list URL receives a 403 (not a 404 — list existence must not be leaked via 404 vs 403 divergence). **Note:** See Open Questions — whether to use 404 everywhere to avoid leaking list existence is a deliberate security trade-off for validation-lead to weigh in on.

---

### US-306: Stranger cannot discover lists they don't have access to

**Description:** As the system, no authenticated user should be able to infer the existence of a list they have no access to.

**Dependencies:** None

**Acceptance Criteria:**
- [ ] A stranger's list endpoint (GET /lists/:id) returns the same response whether the list ID exists-but-is-inaccessible or does not exist at all (no divergence between "forbidden" and "not found" that leaks list existence).
- [ ] List IDs use non-sequential identifiers (UUIDs or equivalent) to prevent enumeration by incrementing IDs.

---

## Realtime Sync Semantics

Realtime sync is a hard v1 requirement. This section defines **what** propagates and **when** — transport mechanism (WebSocket, SSE, etc.) is engineering's decision.

### Channel Scope

Realtime events are scoped **per-list**. Each list has its own channel. A user subscribes to a list's channel when they open that list in the UI and unsubscribes when they navigate away or close the tab.

A per-user global channel (for dashboard-level events) is also defined for share-related events (see below).

### Events That Propagate

#### List-channel events (broadcast to all current subscribers of a list: owner + active editors + active viewers)

| Event | Trigger | Payload (minimum) | Who receives it |
|-------|---------|-------------------|-----------------|
| `item.created` | Any user with write access creates an item | item id, title, notes, done, created_at | All subscribers on that list's channel |
| `item.updated` | Any user with write access updates an item's title, notes, or done state | item id, updated fields, updated_at | All subscribers on that list's channel |
| `item.deleted` | Any user with write access deletes an item | item id | All subscribers on that list's channel |
| `list.renamed` | Owner renames the list | list id, new name, updated_at | All subscribers on that list's channel |
| `collaborator.role_changed` | Owner changes a collaborator's role | list id, affected user id, new role | All subscribers on that list's channel (so editors can observe they were demoted) |
| `collaborator.access_revoked` | Owner revokes a collaborator's access | list id, affected user id | All subscribers on that list's channel |

#### Per-user channel events (delivered to a specific user's personal channel)

| Event | Trigger | Payload (minimum) | Who receives it |
|-------|---------|-------------------|-----------------|
| `share.granted` | Owner shares a list with this user | list id, list name, role | The newly-added collaborator |

**Note:** `share.granted` allows the collaborator's dashboard to update live if they happen to be online when the share is created. This is a best-effort delivery — if the collaborator is not connected, they see the new list on their next dashboard load.

### Behavioral Specifications for Key Events

**`collaborator.access_revoked` received by the revoked user:**
- The list is immediately removed from their dashboard view.
- If they are currently on the list detail page, they are redirected to the dashboard with a message: "Your access to this list has been removed."
- Subsequent API requests for that list return 403.

**`collaborator.role_changed` received by the affected collaborator:**
- If demoted from `editor` to `viewer`: item create/edit/delete controls are disabled without requiring a reload.
- If promoted from `viewer` to `editor`: item create/edit/delete controls become active without requiring a reload.

**`item.created` / `item.updated` / `item.deleted`:**
- The list item view updates in place — no full-page reload required.
- The originating user's own UI may update optimistically before the event arrives; the event serves as confirmation and synchronization for other subscribers.

**`list.renamed`:**
- The list name updates in the list detail header and in all subscribers' dashboards.

### What Does NOT Propagate via Realtime

- Password reset or auth events (scoped to the individual user's session, not a list channel).
- Share-list-granted events to the owner (owner already knows they shared it).
- Dashboard-level list ordering changes (full dashboard refresh on reconnect is acceptable).

### Disconnect and Reconnect

- On reconnect after a network interruption, the client must re-fetch the full current state of the list (not rely on missed events) before re-subscribing to the channel.
- Missed events during a disconnect are not replayed. State is reconciled via a full fetch on reconnect.

---

## Success Metrics

- The authz matrix table above is implemented as a literal test matrix in QA: every role × action cell has an automated test that asserts ALLOW or DENY against the real assembled API.
- Zero strangers can access any data from a list they have no share relationship with (verified by the authz matrix tests).
- Revocation takes effect within one realtime message delivery cycle — the revoked user's active session receives the `collaborator.access_revoked` event and their UI removes the list without a reload.
- A collaborator receives a live `item.created` event within 2 seconds of another user creating an item on a list they are both viewing (measured in E2E test with two browser contexts).
- List IDs use non-sequential identifiers in all API responses.

---

## Constraints

- **Registered-users-only sharing:** Sharing requires the recipient's account to already exist. No invite-by-email-to-non-users, no pending invite queue.
- **Row-level enforcement:** Authorization checks must be performed at the data layer (in queries), not solely at the route/middleware layer. A route-level check is insufficient — engineering must verify per-row ownership/share on every list and item operation.
- **Non-sequential list IDs:** List (and item) IDs must be UUIDs or equivalent — not auto-incrementing integers — to prevent enumeration.
- **Revocation is immediate:** There is no grace period. The server-side share record is deleted synchronously; the realtime event is best-effort.
- **Self-share is prohibited:** A user cannot share a list with themselves. Enforced server-side.
- **Single owner per list:** Ownership is not shared or transferable in v1.

---

## Open Questions

**OQ-1: 404 vs. 403 for stranger access to a list.**
US-306 specifies that a stranger gets the same response whether a list ID exists-but-inaccessible or does not exist, to avoid leaking list existence. This implies returning 404 in both cases. However, 404 on a valid-but-inaccessible list is semantically incorrect and could confuse debugging. **Decision needed from validation-lead:** Should the API always return 404 for non-owned/non-shared lists (maximally opaque, recommended security posture), or 403 with list existence implied (semantically cleaner but leaks existence)? The authz matrix tests need to know the expected status code.

*Recommended default: return 404 for all stranger access to prevent list-existence enumeration. Mark as the intended behavior unless validation-lead overrides.*
