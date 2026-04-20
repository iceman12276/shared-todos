# ADR: Realtime Transport & Fan-Out

**Status:** Accepted
**Date:** 2026-04-19
**Author:** engineering-lead
**Supersedes:** none
**Applies to:** `shared-todos-app` v1
**Informed by:** `docs/planning/prd-3-sharing-permissions.md` (Realtime Sync Semantics), `docs/initiatives/2026-04-19-shared-todos-app.md` (Q5 — realtime as hard v1 requirement)

---

## Context

PRD-3 makes realtime a hard v1 requirement. The contract it pins:

- Event taxonomy — `item.created`, `item.updated`, `item.deleted`, `list.renamed`, `collaborator.role_changed`, `collaborator.access_revoked` broadcast per-list to all active subscribers of that list; `share.granted` delivered to a specific user's personal channel.
- Two scopes — per-list channels and a per-user channel.
- Latency budget — a collaborator receives another user's `item.created` within **2 seconds** (PRD-3 Success Metrics).
- Delivery guarantee — best-effort; missed events during a disconnect are NOT replayed. Client reconciles by re-fetching full list state on reconnect.
- Immediate effect on revocation — the revoked user's UI must clear the list without a reload and subsequent API requests return 403.
- Security — the transport must honor the same authorization model as REST (authz matrix from PRD-3 §Authorization Matrix) and must not leak list existence to strangers (OQ-1 — validation-lead confirmed: stranger → 404 on every verb, including the WebSocket subscribe).

The transport choice is engineering's call. This ADR records that choice.

---

## Decision

**Transport:** WebSocket, one durable connection per browser tab, served by the same FastAPI backend process that serves REST.

**Endpoints:**

- `GET /ws/v1/user` — upgrades to a WebSocket carrying the authenticated user's personal channel (receives `share.granted`, and any future per-user events).
- `GET /ws/v1/lists/{list_id}` — upgrades to a WebSocket scoped to a single list channel. The client opens one of these per list it is currently viewing.

**Fan-out mechanism:** Postgres `LISTEN` / `NOTIFY` inside the same backend process that serves WebSocket connections. When a writer mutates data in a REST handler, the handler emits `NOTIFY <channel>, <json-payload>` **inside the same database transaction** that committed the write. A dedicated asyncio task in the backend holds a `LISTEN` connection, receives notifications, and fans them out to in-process WebSocket subscribers that match the channel.

**Channel naming:**

- `list:{list_id}` — PRD-3 list-channel events.
- `user:{user_id}` — PRD-3 per-user channel events.

**Wire format:** JSON messages shaped `{ "event": "item.created", "list_id": "...", "payload": { ... } }`. The payload schemas are anchored to PRD-3 §Events That Propagate — every event type referenced there MUST be emitted; no additional event types without an ADR update.

---

## Rationale

### Why WebSocket (not SSE, not long-poll)

- **Bidirectional.** The PRD-3 channel model assumes the client manages subscriptions (opens a list channel when it navigates to the list, closes it on navigate-away). That is a subscribe/unsubscribe conversation, which SSE cannot represent cleanly without a second HTTP channel. Keeping a single connection per tab simplifies reconnection handling and avoids double-bookkeeping.
- **Future-proof.** If we later add typing indicators, presence, or optimistic ack (all natural extensions of a collaborative UI), SSE would force us to add a WebSocket later anyway. Paying the cost now avoids a transport migration in v2.
- **Cookie auth works.** The browser sends the httpOnly session cookie on the WebSocket handshake (same-origin, SameSite=Lax, which allows top-level-navigation WS upgrades from the app origin). We get the same auth path as REST without JWTs.

### Why Postgres LISTEN/NOTIFY (not Redis pub/sub, not in-memory broker, not a managed service)

- **No extra infrastructure.** Postgres is already load-bearing. Adding Redis/NATS for v1 would triple the dependency surface, CI boot time, and security review scope for no current benefit.
- **Transactional consistency.** `NOTIFY` fires at transaction commit. If the writing transaction rolls back, no notification is sent. This eliminates the classic dual-write consistency bug where the database and the message broker diverge (item saved, event not emitted, or vice versa). Writers in backend code will always wrap mutation + notify in a single transaction.
- **Latency.** Postgres NOTIFY is sub-millisecond in-process. Fan-out from the LISTEN handler to connected WebSockets is in-process asyncio. The PRD-3 < 2s budget is comfortable.
- **Ordering.** Within a single list channel, NOTIFY preserves commit order. That is sufficient for the per-list event stream semantics PRD-3 assumes (clients reconcile via full re-fetch on reconnect — no cross-list ordering invariants).

### Authentication & Authorization on connect

The WebSocket handshake MUST enforce the same checks that REST enforces. The implementation contract:

1. **Handshake — session cookie required.** If the request carries no valid session cookie, the handshake is rejected with HTTP 401 (via `WebSocketException(code=1008)` after close). No WebSocket upgrade is completed for unauthenticated requests.
2. **Connect to `/ws/v1/user` — subject pinning.** The connection is pinned to the authenticated user's id. The server ignores any `user_id` the client attempts to send; it uses the session-derived subject.
3. **Connect to `/ws/v1/lists/{list_id}` — authz matrix re-check.** Before accepting the subscription, the server re-evaluates the authz matrix for the connecting user against `list_id`. The rule is: `owner`, `editor`, or `viewer` → accept. **`stranger` → close with code 1008 and the handshake returns HTTP 404** (OQ-1: stranger responses are indistinguishable from not-found; validation-lead confirmed this applies to every verb, including WS subscribe — no 403 variant).
4. **Per-event authz gate on send.** Even after subscribe, every outbound event is re-checked against the recipient's current role. If a user's role changed (or was revoked) between subscribe and event-send, the server emits `collaborator.role_changed` or `collaborator.access_revoked` to that recipient and then either tightens their outbound filter or terminates their subscription (depending on the event). **A revoked user MUST NOT receive any further `item.*` or `list.*` events for that list after revocation commits, even if the WebSocket is still open.**
5. **No cross-list subscription multiplexing in v1.** Each list the client views opens a new WS. This keeps the authz re-check surface tiny — a connection is either valid for its single pinned list_id or it is closed.

### Per-list channel model

The PRD-3 channel scope maps 1:1 to the endpoint scope: one WebSocket == one channel. The server keeps an in-memory registry `{ channel -> set<websocket> }`. The LISTEN handler receives a NOTIFY on `list:<uuid>` or `user:<uuid>`, looks up subscribers, and sends to each with the per-event authz gate from step 4 above.

### Reconnection & state reconciliation

PRD-3 is explicit: **missed events during a disconnect are not replayed.** The client protocol is:

1. Connection drops (network blip, server restart, auth expiry).
2. Client detects close. If the close code indicates an auth failure (1008), it surfaces the "you were signed out" state to the UI and does NOT auto-retry.
3. Otherwise, the client re-fetches the full list state via REST (`GET /api/v1/lists/{list_id}` + `GET /api/v1/lists/{list_id}/items`). This establishes the new post-reconnect baseline.
4. Only after the REST baseline lands, the client re-opens the WebSocket and re-subscribes. Any events that arrive between the REST fetch and the WS re-subscribe are implicitly handled by the REST response (eventual consistency; overlap is acceptable because events are idempotent on the client given a server-authoritative item id + `updated_at`).

Exponential backoff on reconnect: 500 ms → 1 s → 2 s → 5 s → 10 s (cap). Abandon after 5 consecutive failures and surface "disconnected" state to the user.

### Latency budget

PRD-3 §Success Metrics specifies that a collaborator receives an `item.created` within 2 s of another user's create. Breakdown:

| Step | Expected latency |
|---|---|
| Writer's REST handler commits + emits NOTIFY | < 50 ms |
| Postgres LISTEN pickup in backend | < 10 ms |
| In-process fan-out + authz re-check + JSON encode | < 20 ms |
| WebSocket frame over LAN/internet | 20–200 ms |
| Client decode + render | < 100 ms |
| **Total (expected)** | **< 500 ms** — 4× under budget |

The 2 s budget leaves substantial headroom for transient network spikes and multi-hop internet paths.

---

## Alternatives Considered

### Alt 1: Server-Sent Events (SSE)

- **Pros:** Simpler than WS (HTTP/1.1 one-way, built-in auto-reconnect with `EventSource`, works behind more restrictive proxies).
- **Cons:** One-way only. The client can't send subscribe/unsubscribe frames — the server has to infer subscription from the URL, which forces N separate SSE connections (one per list) and duplicates the bookkeeping that WS solves with message types. No second-origin proxy benefit in v1 since app and API are same-origin.
- **Rejected:** PRD-3's channel-subscribe model fits bidirectional better. SSE would need a companion HTTP POST lane for subscribe/unsubscribe — worse of both worlds.

### Alt 2: Short-poll (no realtime transport)

- **Pros:** Zero new protocol surface. REST only.
- **Cons:** Cannot meet the PRD-3 "access revoked takes effect without reload" contract without a polling interval tight enough (< 2 s) to make the server load comparable to a WebSocket anyway. User-perceived latency ranges 0–poll-interval.
- **Rejected:** User explicitly rejected this in Q5. "Realtime sync is a HARD REQUIREMENT."

### Alt 3: Redis pub/sub as the broker

- **Pros:** Horizontally scalable — multiple backend replicas can all fan out from the same Redis. Clean abstraction boundary.
- **Cons:** Adds Redis to the CI + prod infra stack for v1. No transactional consistency with Postgres (dual-write problem — write lands in Postgres but Redis publish fails, or vice versa). Requires an outbox pattern to be correct, which adds complexity.
- **Rejected for v1, retained as v2 path:** If we scale to >1 backend replica, the correct move is to introduce Redis pub/sub behind the same `Channel` abstraction our in-process fan-out will define. The public API of our fan-out (`publish(channel, event)` / `subscribe(channel) -> async iterator`) will be written to be substitutable.

### Alt 4: Managed realtime (Pusher, Ably, Supabase Realtime, etc.)

- **Pros:** Offload the transport entirely. Built-in auth, presence, and horizontal scaling.
- **Cons:** Vendor lock-in. Additional cost center. Authz enforcement happens in webhook/presence rules — a new policy surface distinct from our REST authz, which means two places to keep the authz matrix honest. Adds an external dependency that security review has to cover.
- **Rejected:** The authz matrix in PRD-3 is THE risk surface; we want it in one code path (our FastAPI app), not split between our app and a vendor's rule language. Reconsider in v2+ if operational load on the in-process fan-out becomes real.

### Alt 5: Postgres logical replication / CDC (Debezium or similar)

- **Pros:** Events derived from the write-ahead log — zero chance of write/emit divergence.
- **Cons:** Wildly over-engineered for v1. Heavyweight infra (Kafka or equivalent), complex event schema derivation, and the payload shape is table-row-shaped, not PRD-3-event-shaped.
- **Rejected:** Revisit only if we grow into a general event-sourcing architecture.

---

## Trade-offs (Accepted)

- **Single-backend-replica ceiling.** Postgres LISTEN/NOTIFY + in-process fan-out does not span across backend processes. If we run more than one backend replica, events emitted from replica A are NOT seen by subscribers on replica B. Acceptable for v1 (single replica). The `Channel` abstraction is designed so that swapping the LISTEN/NOTIFY backend for a Redis pub/sub backend is a local change, not a rewrite.
- **NOTIFY payload size limit — 8000 bytes.** Postgres NOTIFY payloads cap at ~8KB. Our events carry only ids + small field diffs, comfortably under the limit. If we ever need large payloads (not foreseen), the pattern is to NOTIFY with just an id and let subscribers fetch — we'll cross that bridge then.
- **No event replay, no durable queue.** A client that was disconnected and then reconnects does NOT receive missed events. It reconciles via full-state REST fetch. This is a PRD-3 contract, not a compromise — it keeps the server stateless w.r.t. per-client event history.
- **Authz re-check on every outbound event.** Higher CPU than a "trust at subscribe" design. Necessary for the PRD-3 "revocation takes effect immediately" contract. The re-check is a single indexed row lookup against the `shares` table (or equivalent) — cheap.
- **LISTEN connection is a long-held, dedicated connection.** One connection to Postgres is pinned to the LISTEN handler for the life of the backend process. Acceptable overhead.

---

## Implementation Hand-off to backend-dev

The backend implementation must expose a `Channel` service with the following minimum API. Treat this as the contract; the concrete module path is backend-dev's call.

```python
class Channel:
    async def publish(self, channel: str, event: dict) -> None:
        """Emit NOTIFY <channel> inside the caller's DB transaction."""
    async def subscribe(self, channel: str) -> AsyncIterator[dict]:
        """Yield events as they arrive. Caller decides when to stop."""
```

- `publish` MUST be called inside the same DB transaction that committed the underlying mutation. A helper to enforce this is preferable to relying on discipline.
- `subscribe` MUST be per-connection (one async iterator per WebSocket). The underlying LISTEN connection is shared across subscribers via in-process fan-out.
- WebSocket endpoints MUST apply per-event authz gating (see §Authentication & Authorization on connect, step 4) before sending any event to the client.

---

## References

- `docs/planning/prd-3-sharing-permissions.md` §Authorization Matrix, §Realtime Sync Semantics, §Success Metrics
- `docs/planning/prd-1-auth.md` §US-104 (session semantics that the WS handshake inherits)
- `docs/initiatives/2026-04-19-shared-todos-app.md` §User Decision Q5, Q1 (registered-users-only constrains who can ever subscribe)
- Postgres docs: `NOTIFY`, `LISTEN`, async notification delivery
