# PRD-5: Realtime WebSocket Sync

**Version:** 1.0
**Date:** 2026-04-21
**Status:** Draft
**Author:** product-manager

---

## Problem

PRD-3 made a hard commitment: collaborators see each other's edits without a manual refresh. PR-3 shipped the sharing and authorization backend, but no realtime delivery mechanism exists yet. Every mutation a collaborator makes is invisible to other active viewers until they reload the page — breaking the core collaborative promise.

This PRD specifies what the realtime delivery layer means from the user's perspective: which events flow, over which channels, to which users, and how the system behaves on reconnect, revocation, and error. The transport is already decided (WebSocket + Postgres `LISTEN/NOTIFY` — see the ADR at `docs/architecture/realtime-transport-decision.md`). This document specifies the contract above the transport.

---

## Users

- **Primary:** Any user who has an active list detail view open while another user mutates that list — owner, editor, or viewer.
- **Primary:** A collaborator who is on their dashboard when a new list is shared with them.
- **Secondary:** The list owner, who wants confidence that permission changes (role edits, revocations) take effect in real time for active collaborators, not just at next reload.
- **Out of scope:** Unauthenticated users; strangers who have no access relationship with any list.

---

## Goals

- A collaborator viewing a list sees item mutations (`created`, `updated`, `deleted`) made by any other authorized user within 2 seconds of the originating write completing, without refreshing the page.
- A list rename made by the owner propagates to all active subscribers of that list within 2 seconds.
- When the owner revokes a collaborator's access, the revoked user's view of that list is cleared within one realtime message delivery cycle — no reload required.
- When the owner changes a collaborator's role, the affected collaborator's write controls update in-place (editor demoted → controls disabled; viewer promoted → controls enabled) without a reload.
- When a list is shared with a user who is currently on their dashboard, the shared list appears on their dashboard in real time (best-effort — acceptable to appear on next load if user is not connected).
- Presence indicators show which collaborators are currently viewing the same list (BSD-3 `RealtimePresenceIndicator` contract).
- A client that disconnects and reconnects recovers to a consistent state without server-side event replay.
- Unauthorized WebSocket upgrade attempts (stranger, unauthenticated) are rejected with the same opacity as REST — no list-existence signal is leaked.

---

## Non-Goals

- Server-side event replay or durable event queues — a client that reconnects re-fetches full state via REST, not missed events.
- CRDT or operational-transform conflict resolution — last-write-wins per item (by `updated_at`) is sufficient v1.
- Optimistic-edit conflict resolution beyond what PR-3's authz model implies.
- Offline-first editing — the app requires a live connection; no local write queue.
- Cross-list subscription multiplexing on a single WebSocket — one WS connection per list, one WS connection for the user channel, per the ADR.
- Push notifications to mobile or email on realtime events.
- In-app notification bell or persistent notification list — a toast on `share.granted` is sufficient v1 (PRD-3 Non-Goals).
- Presence indicators on dashboard list cards — only shown in the list detail view (BSD-3 §Open Design Decisions, item 2).
- Typing indicators.
- Server-side event coalescing or debouncing — all mutations fan out immediately; debouncing is a client UX concern.

---

## Subscription Model

Two WebSocket endpoints (pinned in the ADR and CLAUDE.md):

| Endpoint | Channel | Purpose |
|----------|---------|---------|
| `GET /ws/v1/lists/{list_id}` | `list:{list_id}` | Per-list events for all authorized subscribers of that list |
| `GET /ws/v1/user` | `user:{user_id}` | Per-user events delivered to a specific authenticated user |

**Authorization on connect:**

- `/ws/v1/user` — valid session cookie required; connection is pinned to the session user. The server ignores any user identity the client attempts to assert.
- `/ws/v1/lists/{list_id}` — valid session cookie required; connecting user must be `owner`, `editor`, or `viewer` of the list (PRD-3 authz matrix). A `stranger` or unauthenticated request is rejected: the WebSocket upgrade is refused and the handshake returns HTTP 404 — identical behavior to the REST stranger → 404 invariant from PRD-3 OQ-1 (confirmed by validation-lead). No 403 variant.

**Per-event authz gate:** Even after a successful subscribe, the server re-checks the connecting user's role before sending each event. If a user is revoked or demoted between subscribe time and event-send time, the server sends the appropriate `collaborator.access_revoked` or `collaborator.role_changed` event and then closes or tightens the subscription accordingly. A revoked user MUST NOT receive any further `item.*` or `list.*` events after revocation commits.

---

## Event Catalog

All wire-format messages are JSON: `{ "event": "<name>", "list_id": "<uuid>", "payload": { ... } }`. Payload schemas carry only the fields needed for the client to update its local cache — not full resource representations.

### List-channel events (`/ws/v1/lists/{list_id}`)

Broadcast to all currently connected and authorized subscribers of the list channel.

| Event | Trigger | Minimum payload | Audience |
|-------|---------|----------------|---------|
| `item.created` | Any user with write access creates an item | `{ item_id, title, notes, done, created_at, created_by_user_id }` | All subscribers (owner, editors, viewers) |
| `item.updated` | Any user with write access updates an item's title, notes, or done state | `{ item_id, title, notes, done, updated_at, updated_by_user_id }` | All subscribers |
| `item.deleted` | Any user with write access deletes an item | `{ item_id }` | All subscribers |
| `list.renamed` | Owner renames the list | `{ list_id, name, updated_at }` | All subscribers |
| `list.deleted` | Owner deletes the list | `{ list_id }` | All subscribers |
| `collaborator.role_changed` | Owner changes a collaborator's role | `{ list_id, affected_user_id, new_role }` | All subscribers |
| `collaborator.access_revoked` | Owner revokes a collaborator's access | `{ list_id, affected_user_id }` | All subscribers (including the revoked user, as their final event on this channel) |
| `presence.joined` | An authorized user opens the list view (connects to this channel) | `{ user_id }` | All other subscribers already connected |
| `presence.left` | An authorized user closes the list view (disconnects from this channel) | `{ user_id }` | All remaining subscribers |

### Per-user channel events (`/ws/v1/user`)

Delivered to a specific user's personal channel only.

| Event | Trigger | Minimum payload | Audience |
|-------|---------|----------------|---------|
| `share.granted` | Owner shares a list with this user | `{ list_id, list_name, role }` | The newly-added collaborator only |

---

## Behavioral Specifications

### `collaborator.access_revoked` received by the revoked user

The revoked user receives this event as their final event on the list channel. The server closes the revoked user's subscription to `list:{list_id}` after sending. On the client:
- If the user is currently on the list detail page: a full-screen overlay or redirect takes them to their dashboard with the message "Your access to this list has been removed by the owner."
- The list no longer appears on the revoked user's dashboard.
- Any subsequent REST requests for that list return 403 (or 404 per OQ-1 — consistent with the REST layer).

### `collaborator.role_changed` received by the affected collaborator

- Demotion (`editor` → `viewer`): item create/edit/delete controls are disabled in-place, no reload.
- Promotion (`viewer` → `editor`): item create/edit/delete controls become active in-place, no reload.

### `list.deleted` received by subscribers

All current subscribers receive this event. Clients redirect to the dashboard with a message "This list has been deleted." The server closes all subscriptions for this channel.

### `share.granted` received on the user channel

The shared list is added to the recipient's dashboard if they are currently viewing it. This is best-effort — if the user is not connected to `/ws/v1/user`, they see the new list on their next dashboard load.

### Presence events

When a user connects to `/ws/v1/lists/{list_id}`, a `presence.joined` event is emitted to all other currently connected subscribers. When they disconnect, a `presence.left` event is emitted. The server does not maintain a durable presence roster — the client builds its local presence set by tracking `joined`/`left` events since its own connect, and reconciles on reconnect by re-fetching current subscribers (see Reconnection Semantics).

---

## Reconnection Semantics

1. Connection drops (network blip, server restart, session expiry, or explicit close by server).
2. Client inspects the WebSocket close code:
   - Close code `1008` (policy violation) or HTTP 401 on the upgrade handshake: auth failure. Surface "You have been signed out" state to the UI. Do NOT auto-retry.
   - Close code `1008` on a list channel with HTTP 404 on the upgrade: access revoked or list deleted. Surface the appropriate message (see above). Do NOT auto-retry.
   - Any other close: transient disconnection. Proceed to step 3.
3. Client re-fetches full current state via REST (`GET /api/v1/lists/{list_id}` and `GET /api/v1/lists/{list_id}/items` for a list channel; dashboard list for the user channel). This is the new post-reconnect baseline.
4. Client re-opens the WebSocket with exponential backoff: 500 ms → 1 s → 2 s → 5 s → 10 s (cap at 10 s). Abandon after 5 consecutive failures; surface "Disconnected — trying to reconnect" state to the user.
5. Only after the REST baseline lands and the WS re-opens does the client re-subscribe. Events that arrive during the gap between the REST fetch and WS subscribe are covered by the REST baseline (idempotent last-write-wins on `updated_at`).

Missed events during a disconnect are NOT replayed by the server. The REST re-fetch is the reconciliation mechanism.

---

## Event Ordering

Events on a single list channel preserve Postgres commit order (enforced by the `LISTEN/NOTIFY` mechanism — within one channel, notifications are delivered in commit order). The client applies:

- **Item state: last-write-wins by `updated_at`.** If an `item.updated` event arrives with an `updated_at` older than the client's current state for that item, the client discards it.
- **Item existence: last-event-wins for created/deleted.** `item.deleted` takes precedence over any preceding `item.updated` for the same `item_id`.
- **No cross-item ordering guarantee.** Two simultaneous edits to two different items may arrive in any order; that is acceptable.

---

## Back-Pressure Policy

The server fans out all mutations immediately — no server-side coalescing or debouncing. If a user makes 10 rapid edits to the same item, 10 `item.updated` events are fanned out. The client's last-write-wins rule on `updated_at` ensures only the final state is applied; intermediate events are safe to apply in order or discard if stale.

Debouncing rapid keystrokes before emitting a save is a client UX concern (handled in the frontend layer), not a server contract specified here.

---

## Revocation Race Invariant

A user mid-session with an open WS subscription to a list channel has their access revoked by the owner. The sequence must be:

1. Owner's `POST /api/v1/lists/{list_id}/shares/{user_id}` (revoke) commits to the database.
2. Within the same transaction commit, a `NOTIFY list:{list_id}` fires with the `collaborator.access_revoked` payload.
3. The LISTEN handler fans the event to all subscribers, including the revoked user.
4. The per-event authz gate, on sending to the revoked user, confirms they are revoked — sends the event — then closes their subscription.
5. All subsequent events on this channel skip the revoked user (their subscription is closed).

There is no window in which the revoked user can receive `item.*` or `list.*` events after step 1 commits.

---

## User Stories

### US-501: Receive live item mutations on a list I am viewing

**Description:** As a collaborator viewing a list, I want to see items created, updated, and deleted by other authorized users without refreshing the page.

**Dependencies:** US-301 (share exists), US-401 (session exists)

**Acceptance Criteria:**
- [ ] Two simultaneous clients subscribed to `/ws/v1/lists/{list_id}` both receive `item.created` within 2 seconds of the originating POST request completing.
- [ ] An `item.updated` event updates the corresponding item in the client's view in-place — no full list re-render.
- [ ] An `item.deleted` event removes the item from the client's view in-place.
- [ ] Events originating from the receiving client's own session are handled idempotently (no duplicate rendering if the client updated optimistically).

---

### US-502: See a list rename propagate in real time

**Description:** As a collaborator viewing a list, I want to see the list's name update when the owner renames it, without refreshing.

**Dependencies:** US-501

**Acceptance Criteria:**
- [ ] A `list.renamed` event updates the list name in the detail header and in any dashboard instances visible in the same tab without a reload.
- [ ] The rename propagates to all active list-channel subscribers within 2 seconds.

---

### US-503: Lose access in real time when revoked

**Description:** As a collaborator whose access to a list has just been revoked by the owner, I want my view to update immediately so I am not left viewing data I no longer have permission to see.

**Dependencies:** US-304, US-501

**Acceptance Criteria:**
- [ ] A revoked collaborator who is currently on the list detail page receives `collaborator.access_revoked` and is redirected to their dashboard within one message-delivery cycle — no reload required.
- [ ] After revocation, any REST request to that list from the revoked user returns 403 (or 404 per OQ-1).
- [ ] The revoked user's WebSocket subscription to the list channel is closed by the server after the revocation event is sent.
- [ ] The revoked user does not receive any further `item.*` or `list.*` events for that list after the revocation commits.

---

### US-504: Have my role change take effect in real time

**Description:** As a collaborator whose role has just been changed by the owner, I want my write controls to update in-place so I know immediately what I can and cannot do.

**Dependencies:** US-303, US-501

**Acceptance Criteria:**
- [ ] A collaborator demoted from `editor` to `viewer` sees item create/edit/delete controls disabled in the UI without a reload, upon receiving `collaborator.role_changed`.
- [ ] A collaborator promoted from `viewer` to `editor` sees item create/edit/delete controls enabled in the UI without a reload.
- [ ] The role change takes effect at the server level (authz re-check) within the same request that committed the change — the affected user cannot perform a write between role-change commit and event delivery.

---

### US-505: See a new shared list appear on my dashboard in real time

**Description:** As a registered user who is online when a list is shared with me, I want the new list to appear on my dashboard without refreshing.

**Dependencies:** US-301, US-501

**Acceptance Criteria:**
- [ ] A `share.granted` event delivered to the user's personal channel (`/ws/v1/user`) adds the shared list to the dashboard view without a reload.
- [ ] If the user is not connected to `/ws/v1/user` at the time of sharing, the list appears on their next dashboard load (best-effort delivery).

---

### US-506: See who else is viewing the list I am on

**Description:** As a collaborator viewing a list, I want to see presence indicators for other users currently viewing the same list so I know live collaboration is active.

**Dependencies:** US-501

**Acceptance Criteria:**
- [ ] When a remote collaborator connects to the same list channel, a `presence.joined` event causes their avatar (or a count indicator) to appear in the list header per the BSD-3 `RealtimePresenceIndicator` spec.
- [ ] When a remote collaborator disconnects from the list channel, a `presence.left` event removes their indicator.
- [ ] If the connection drops, presence indicators are hidden until the client reconnects and re-establishes the presence set.
- [ ] A user does not see themselves in the presence indicator (the indicator shows remote collaborators only).
- [ ] Presence indicators appear only in the list detail view — not on dashboard list cards.

---

### US-507: Recover gracefully from a dropped WebSocket connection

**Description:** As a user whose WebSocket connection dropped, I want the client to reconnect and restore a consistent view automatically, without data loss.

**Dependencies:** US-501

**Acceptance Criteria:**
- [ ] On a transient disconnect, the client attempts reconnect with exponential backoff starting at 500 ms (500 ms → 1 s → 2 s → 5 s → 10 s).
- [ ] Before re-subscribing, the client re-fetches full list state via REST to establish a post-reconnect baseline.
- [ ] After 5 consecutive failed reconnect attempts, the client surfaces a "Disconnected" state to the user and stops retrying.
- [ ] On an auth-failure close (code 1008 from a failed session), the client does NOT auto-retry and surfaces "You have been signed out."
- [ ] A reconnected client receives new events correctly — no duplicates from before the disconnect, no gaps visible to the user (because the REST re-fetch covers the gap).

---

### US-508: Stranger cannot subscribe to a list channel

**Description:** As the system, I must reject WebSocket upgrade attempts from users who have no access to the list — without leaking whether the list exists.

**Dependencies:** US-306 (OQ-1 invariant)

**Acceptance Criteria:**
- [ ] A stranger's WebSocket upgrade to `/ws/v1/lists/{list_id}` is rejected with HTTP 404 — identical to the REST stranger response.
- [ ] The 404 response for a stranger is indistinguishable from the response for a list that does not exist — no signal about list existence.
- [ ] An unauthenticated request (no valid session cookie) is rejected with HTTP 401 before the WebSocket upgrade completes.

---

## Invariants

1. **OQ-1 carryover — stranger opacity on WS upgrade.** A stranger's WebSocket upgrade to any list channel returns HTTP 404. The response is indistinguishable from a request for a non-existent list. No 403 variant. This is an inherited invariant from PRD-3 OQ-1 (confirmed by validation-lead), applied to every verb including WS subscribe.

2. **Revocation is atomic and immediately enforced.** A user whose share is revoked MUST NOT receive any `item.*` or `list.*` events after the revocation transaction commits. The server closes the revoked user's list-channel subscription synchronously with event delivery — no grace period.

3. **Per-event authz gate is always applied.** No event is sent to a subscriber whose current role does not authorize receiving it. The authz re-check at send-time is mandatory — subscribe-time authorization alone is not sufficient.

4. **NOTIFY fires within the writing transaction.** The `NOTIFY list:{list_id}` call that fans an event MUST be emitted inside the same database transaction that committed the underlying mutation. If the transaction rolls back, no event is emitted. This eliminates write/emit divergence.

5. **Last-write-wins by `updated_at` for item state.** The client applies item events in the order received but discards any `item.updated` whose `updated_at` is older than the client's current state for that item. This is the conflict resolution rule — no CRDT, no OT.

6. **No token material or internal IDs beyond what the authz model exposes.** Events must not carry fields that would allow a subscriber to infer the existence or content of data they are not authorized to see (e.g., no `revoked_user_email` in a `collaborator.access_revoked` broadcast to all subscribers — only the `affected_user_id`).

---

## Constraints

- **Transport is fixed.** WebSocket + Postgres `LISTEN/NOTIFY` as specified in the ADR. No SSE, long-poll, or third-party broker in v1.
- **Single backend replica in v1.** In-process fan-out is only correct with one backend process. If a second replica is added, the fan-out mechanism must be replaced with a Redis pub/sub backend behind the same `Channel` abstraction (ADR §Trade-offs).
- **NOTIFY payload ≤ 8 KB.** Postgres `NOTIFY` payloads are capped at ~8 KB. Event payloads carry only IDs and small field diffs — never full resource bodies. If a payload would exceed this limit, the approach is to NOTIFY with only the resource ID and let subscribers re-fetch.
- **Cookie-based auth only.** The WebSocket handshake authenticates via the httpOnly session cookie. No token-in-query-string, no Authorization header on the upgrade.
- **No cross-list multiplexing.** One WebSocket connection per list per browser tab. The server does not support a single WS that multiplexes events for multiple lists.

---

## Success Metrics

- Two simultaneous authenticated clients subscribed to the same `/ws/v1/lists/{list_id}` both receive `item.created` within 2 seconds of the originating POST completing (measured by E2E test with two browser contexts).
- A revoked collaborator's list-channel subscription is closed by the server within one event delivery cycle — the next `item.*` event after revocation commits is NOT delivered to the revoked user (verified by integration test).
- A stranger's WebSocket upgrade to `/ws/v1/lists/{list_id}` returns HTTP 404 — same status as a request for a non-existent list (verified by parameterized integration test covering: stranger, non-existent list ID, unauthenticated).
- On reconnect after a simulated network drop, the client re-fetches list state via REST before re-subscribing — no stale pre-disconnect item state is visible after reconnect (verified by E2E test).
- 100% of events in the event catalog have integration tests confirming correct fan-out to authorized subscribers and non-delivery to unauthorized users.
- Presence join/leave events are delivered to all other active subscribers on the same list channel within 2 seconds (verified by E2E test with two concurrent browser contexts).

---

## Open Questions

**OQ-5a: Presence fan-out — in PR-5 scope or deferred?**

BSD-3 already commits to `RealtimePresenceIndicator` with `presence.joined` and `presence.left` events, and this PRD recommends including presence in v1 to honor that BSD-3 contract. However, presence adds server-side subscriber registry overhead (tracking who is currently connected to each list channel) and requires the server to emit `presence.joined`/`presence.left` on connect and disconnect. This is not complex, but it is additional surface area for PR-5.

*Recommendation:* Include presence in PR-5 scope — BSD-3 already exposed this to the user and deferring it would leave the BSD spec in a broken state.

*Needs user confirmation if they prefer to defer:* If presence is deferred to PR-6+, BSD-3 must be updated to remove the `RealtimePresenceIndicator` component spec, and the PRD-5 event catalog must remove `presence.joined` / `presence.left`. Flag for user decision only if the team lead wants to slim PR-5 scope.

**Who resolves:** User decision (scope), with ux-designer's input if BSD-3 amendment is required.
