# BSD-5: Realtime WebSocket Sync UX

**Version:** 1.0
**Date:** 2026-04-21
**Status:** Draft
**Author:** ux-designer
**PRD Reference:** PRD-5: Realtime WebSocket Sync

---

## Overview

This BSD specifies the user-visible surface of the realtime WebSocket layer introduced in PR-5. The transport engine (WebSocket + Postgres `LISTEN/NOTIFY`, two channels per the ADR) is fixed — this document covers what users see and experience as a result of that engine.

**Scope principle:** Most of PR-5 is invisible. The happy path — remote collaborators' mutations appearing within 2 seconds — produces visual effects already anchored in BSD-2 (`realtime-pulse` token, `LiveUpdateAnimator` animations) and BSD-3 (`RealtimePresenceIndicator` scaffold, `RevocationBlockingOverlay`, `LiveUpdateAnimator` full spec). BSD-5 graduates those scaffolds to implementation-ready, adds the connection-lifecycle UX (connecting / disconnected / reconnecting / reconnect-abandoned), and specifies the 14 flows enumerated below.

**Cross-references (do not duplicate):**
- BSD-3 `LiveUpdateAnimator` — owns animation specs for `item.*`, `list.renamed`, `collaborator.role_changed`, `collaborator.access_revoked`, `share.granted`. BSD-5 extends with WS-trigger path and reconnection context.
- BSD-3 `RevocationBlockingOverlay` — owns the full non-dismissible overlay spec for revocation. BSD-5 adds the WS close sequence that follows.
- BSD-3 `RealtimePresenceIndicator` — scaffolded. BSD-5 graduates it to implementation-ready.
- BSD-4 `ForcedLogoutHandler` — owns the auth-failure redirect path. BSD-5 defers to it on WS close code 1008.

---

## Design Token Reference

Inherits all tokens from BSD-1, BSD-2, BSD-3, and BSD-4. New tokens introduced in BSD-5:

```
COLOR:
  warning-600: #D97706   -- amber-600, used for stale-data banner icon + border
  warning-50:  #FFFBEB   -- amber-50, stale-data banner background
  warning-200: #FDE68A   -- amber-200, stale-data banner border
  disconnected-dot: #9CA3AF  -- neutral-400, offline presence dot (replaces realtime-pulse)

MOTION:
  presence-enter: opacity 0 + translateX(8px) -> opacity 1 + translateX(0), 200ms ease-out
  presence-exit:  opacity 1 -> opacity 0, 150ms ease-in
  reconnect-banner-enter: translateY(-100%) -> translateY(0), 200ms ease-out
  reconnect-banner-exit:  translateY(0) -> translateY(-100%), 150ms ease-in
  control-fade-in:  opacity 0 -> 1, 200ms ease-out
  control-fade-out: opacity 1 -> 0, 150ms ease-in
```

---

## Flow 1: Connection Lifecycle States

### Component Specification
```
COMPONENT: WSConnectionManager
PURPOSE: Manage the lifecycle of both WebSocket channels (list-channel and user-channel),
         surface connection state to the UI, and coordinate reconnection with REST re-fetch.
LOCATION: App-level singleton (not tied to any single page or component). Exposes a
          connection state value consumed by the DisconnectBanner and PresenceIndicator.
```

### State Machine

```
                    ┌─────────────┐
           page     │             │
           load ──> │  CONNECTING │
                    │             │
                    └──────┬──────┘
                           │ WS handshake succeeds
                           │ (HTTP 101 Switching Protocols)
                           ▼
                    ┌─────────────┐   remote mutation
                    │             │ ──────────────────> LiveUpdateAnimator fires
                    │  CONNECTED  │
                    │  (invisible)│ <────────────────── server pings / no-op
                    └──────┬──────┘
                           │ WS closes (any code except 1008/1011)
                           ▼
                    ┌─────────────┐
                    │ RECONNECTING│ ── shows DisconnectBanner (retrying variant)
                    │ (backoff)   │    attempt 1: 500ms
                    │             │    attempt 2: 1,000ms
                    └──────┬──────┘   attempt 3: 2,000ms
                     /     │ \        attempt 4: 5,000ms
      success /      │     │  \ 5th   attempt 5: 10,000ms
             /       │     │   \ fail
            ▼        │     │    ▼
     ┌──────────┐    │     │  ┌──────────────────┐
     │CONNECTED │    │     │  │ RECONNECT_FAILED  │ ── DisconnectBanner (failed variant)
     │(invisible)│   │     │  │ (manual retry)   │    + StaleDataBanner
     └──────────┘    │     │  └──────────┬───────┘
                     │     │             │ user clicks "Reconnect"
                     │     │             └──────> RECONNECTING (resets attempt count)
                     │     │
                     │     │ WS closes with code 1008 (policy violation / auth failure)
                     │     ▼
                     │  ┌──────────────┐
                     │  │  AUTH_FAILED  │ ── delegates entirely to BSD-4 ForcedLogoutHandler
                     │  │  (no WS UI)  │    (see Integration Note 1)
                     │  └──────────────┘
                     │
                     │ WS closes with code 1008 AND list-channel upgrade returns HTTP 404
                     ▼
                  ┌──────────────┐
                  │ ACCESS_LOST  │ ── delegates to BSD-3 RevocationBlockingOverlay
                  │ (no WS UI)  │    OR list.deleted redirect (see Flows 6, 7)
                  └──────────────┘
```

### Per-State Visual Treatment

```
CONNECTING:
  No visible indicator. Page shows skeleton/loading state per BSD-2 (data arrives via
  REST before WS connects; WS connection is additive, not blocking).

CONNECTED:
  No visible indicator. This is the happy path. The RealtimePresenceIndicator is the
  only persistent visual artifact of a live connection, and it is content-driven
  (shows remote collaborators, not connection state).

RECONNECTING (attempt 1–4):
  DisconnectBanner appears at top of list view (retrying variant).
  See Component: DisconnectBanner below.

RECONNECTING (attempt 5, the final attempt):
  DisconnectBanner remains (retrying variant) until attempt 5 resolves.
  On failure: transitions to RECONNECT_FAILED state.

RECONNECT_FAILED:
  DisconnectBanner switches to failed variant.
  StaleDataBanner appears below DisconnectBanner.
  Both persist until manual reconnect succeeds or user navigates away.

AUTH_FAILED (close code 1008):
  No WS-specific UI. BSD-4 ForcedLogoutHandler fires.
  DisconnectBanner does NOT appear.

ACCESS_LOST (close code 1008 + HTTP 404 on list-channel):
  No WS-specific UI. BSD-3 RevocationBlockingOverlay or list.deleted redirect fires.
```

### Edge Cases
```
- WS not supported by browser: treat as RECONNECT_FAILED immediately. Show failed variant
  DisconnectBanner. Engineering: check via feature detection before attempting connect.
- Both channels (list + user) disconnect simultaneously: single DisconnectBanner shown
  (not two). Reconnect attempts cover both channels in parallel.
- Page navigates away during RECONNECTING: cancel backoff timer, close any pending WS,
  no UI needed (user left the page).
- Server restart (close code 1001 Going Away): treat as transient disconnect → RECONNECTING.
- Server sends close code 1011 (Internal Error): treat as transient disconnect → RECONNECTING.
```

---

## Component: DisconnectBanner

### Component Specification
```
COMPONENT: DisconnectBanner
PURPOSE: Persistent status indicator shown during active reconnection attempts and after
         reconnect failure. Replaces the per-attempt toast pattern — this is an ongoing
         state, not a transient event.
LOCATION: Top of list detail view, below the fixed navigation bar (56px from top), above
          list content. Full-width within the list content column (max-width 960px, centered).
          NOT shown on /dashboard (user-channel disconnect is silent on dashboard —
          the stale-data risk there is low; next dashboard load restores state).
```

### Visual Specification — Retrying Variant
```
LAYOUT:
  - Full content-column width, height 40px
  - Padding: 0 16px
  - Background: info-50 (#EFF6FF)
  - Border-bottom: 1px info-600 (#2563EB)
  - Flex row: spinner (14px, info-600) + gap 8px + message text + auto spacer + attempt counter

TYPOGRAPHY:
  - "Reconnecting..." — body-sm (12px/400), neutral-700
  - Attempt counter: "Attempt N of 5" — body-sm (12px/400), neutral-500, right-aligned

ANIMATION:
  - Appear: reconnect-banner-enter (slide down from top, 200ms ease-out)
  - Dismiss on success: reconnect-banner-exit (slide up, 150ms ease-in)
```

### Visual Specification — Failed Variant
```
LAYOUT: same dimensions and position as retrying variant
CHANGES:
  - Background: warning-50 (#FFFBEB)
  - Border-bottom: 1px warning-600 (#D97706)
  - No spinner
  - Message: "Live updates unavailable."
  - Right side: "Reconnect" text button (brand-600, body-sm/500, underline on hover)

TRANSITION from retrying to failed variant:
  - Cross-fade content in place (no position change): 200ms ease
  - Spinner fades out, text updates, Reconnect button fades in
```

### Interaction Specification
```
ELEMENT: DisconnectBanner (retrying variant)
TRIGGER: WSConnectionManager enters RECONNECTING state
EXPECTED BEHAVIOR:
  1. Banner slides down from top (reconnect-banner-enter, 200ms).
  2. Spinner animates continuously.
  3. Attempt counter updates each time a new attempt begins (1 of 5 → 2 of 5 → ...).
  4. On successful reconnect (any attempt): banner slides up (reconnect-banner-exit, 150ms),
     then is removed from DOM. RealtimePresenceIndicator resumes normally.
  5. On 5th failure: transition to failed variant (cross-fade, 200ms).
LOADING STATE: the banner IS the loading state
SUCCESS STATE: banner dismissed
ERROR STATE: transition to failed variant
EDGE CASES:
  - User scrolls down while banner is showing: banner stays fixed at top of content column
    (position: sticky, top: 56px — below the nav bar). Does NOT float over content.
  - User starts typing in an item input while disconnected: input remains usable. Banner
    coexists with the normal item edit flow. Submitted changes may fail (POST 401/503);
    component-level error handling from BSD-2 covers those.

ELEMENT: "Reconnect" button (failed variant)
TRIGGER: click
EXPECTED BEHAVIOR:
  1. Switch banner back to retrying variant (cross-fade 200ms).
  2. Reset attempt counter to 1 of 5.
  3. WSConnectionManager begins a new RECONNECTING cycle (REST re-fetch first, then WS).
  4. On success: banner slides up and is dismissed.
  5. On 5 more failures: return to failed variant.
LOADING STATE: retrying variant with attempt counter
SUCCESS STATE: banner dismissed
ERROR STATE: failed variant again (user can try again indefinitely)
```

### Accessibility Specification
```
KEYBOARD:
  - Failed variant "Reconnect" button: focusable, Enter/Space triggers reconnect
  - Tab order: Reconnect button comes after list header elements, before list content

SCREEN READER:
  - Banner container: role="status", aria-live="polite", aria-atomic="false"
  - Retrying variant text: announced once on appear; attempt counter updates are announced
    on each change (aria-live="polite" on counter span)
  - Failed variant: role="alert", aria-live="assertive" — the failure state warrants
    assertive announcement since it changes the user's ability to collaborate
  - "Reconnect" button: aria-label="Retry WebSocket connection"

FOCUS MANAGEMENT:
  - Banner appears/disappears without stealing focus
  - On failed variant appear: no focus change (role="alert" announces without focus move)
  - After successful reconnect and banner dismiss: no focus change
```

### Responsive Specification
```
DESKTOP (>=1024px): full 960px content column, 40px height, sticky below nav
TABLET (768-1023px): full content width (100% - 48px), 40px height
MOBILE (<768px):    full width (100% - 32px), height 48px (taller for touch target on Reconnect)
                    attempt counter hidden on mobile (space constrained);
                    "Reconnecting..." / "Live updates unavailable. Reconnect?" only
```

---

## Component: StaleDataBanner

### Component Specification
```
COMPONENT: StaleDataBanner
PURPOSE: Inform the user that the data they are viewing may be out of date, because live
         updates have stopped and 5 reconnect attempts have failed.
LOCATION: Below DisconnectBanner (failed variant), above list content. Same column width.
```

### Visual Specification
```
LAYOUT:
  - Full content-column width, height 36px
  - Padding: 0 16px
  - Background: warning-50 (#FFFBEB)
  - Border-bottom: 1px warning-200 (#FDE68A)
  - Flex row: warning icon (14px, warning-600 #D97706) + gap 8px + message text

TYPOGRAPHY:
  - "You may be viewing outdated data. Reload to see the latest." — body-sm (12px/400), neutral-700

ANIMATION:
  - Appear: fade-in 200ms (no translate — appears beneath the DisconnectBanner which already
    slid in; a second slide would be visually noisy)
  - Dismiss: fade-out 200ms, on successful reconnect (both banners dismiss together)

CONTENT DEGRADATION (optional, engineering call):
  - List item rows MAY be visually dimmed (opacity 0.75) to signal stale data.
  - This is an engineering implementation option — it must NOT break readability.
  - If implemented: dimming applies to item rows only, not to the list header or controls.
  - Under prefers-reduced-motion: skip dimming entirely (opacity stays at 1.0).
  - Decision: engineering call, no product sign-off needed. Flag as Open Design Decision 1.
```

### Interaction Specification
```
TRIGGER: WSConnectionManager enters RECONNECT_FAILED state
EXPECTED BEHAVIOR:
  1. Appears immediately after DisconnectBanner transitions to failed variant (200ms delay).
  2. Persists until WSConnectionManager returns to CONNECTED state (user clicked Reconnect
     and it succeeded, or user navigated away).
  3. No manual dismiss. Cleared only by successful reconnect or navigation.
EDGE CASES:
  - User reloads the page: normal page load restores REST data; WS reconnects; banners gone.
  - Both banners showing and user navigates to /dashboard: banners dismissed; dashboard
    has no DisconnectBanner (user-channel disconnect is silent on dashboard).
```

### Accessibility Specification
```
SCREEN READER:
  role="status", aria-live="polite"
  Announced once on appear. Not re-announced while persisting.
KEYBOARD: No interactive elements.
MOTION: prefers-reduced-motion: skip item-row dimming.
```

---

## Flow 2: Reconnecting State (Visual Detail)

See Component: DisconnectBanner (retrying variant) above. Summary:

```
WHAT USER SEES DURING RECONNECTION WINDOW:
  - Attempt 1 (t=0ms): DisconnectBanner appears immediately on disconnect, "Reconnecting...
    Attempt 1 of 5"
  - First retry fires after 500ms. If it succeeds: banner gone.
  - If it fails: attempt counter increments. Next retry in 1,000ms.
  - Pattern: 500ms / 1s / 2s / 5s / 10s. Total max wait: ~18.5s before RECONNECT_FAILED.
  - User can continue to use the UI (read items, view list). Write attempts may fail at
    the API layer; BSD-2 component-level error handling covers those.
  - User cannot force-retry during RECONNECTING (no button until RECONNECT_FAILED).
    Rationale: showing a "Reconnect" button during active retries is confusing when the
    client is already trying. Button appears only when retries are exhausted.
```

---

## Flow 3: Reconnect-Failed State (Visual Detail)

See Component: DisconnectBanner (failed variant) and Component: StaleDataBanner above. Summary:

```
WHAT USER SEES AFTER 5 FAILURES:
  1. DisconnectBanner cross-fades to failed variant: warning-50 bg, "Live updates
     unavailable." + "Reconnect" button.
  2. StaleDataBanner fades in below: "You may be viewing outdated data. Reload..."
  3. [Optional] Item rows dimmed to opacity 0.75.
  4. User can: (a) click "Reconnect" to retry; (b) reload the page; (c) continue
     reading stale data; (d) navigate away.
  5. No modal, no blocking overlay. The user retains full control of the page.
     Rationale: reconnect failure is not a security event and should not disrupt
     the user's workflow beyond informing them of the limitation.
```

---

## Flow 4: Remote Mutation Animations (Extending BSD-2)

### Reference
BSD-3 `LiveUpdateAnimator` already specifies the full animation set for remote events:
- `item.created` (from remote): slide-in + brand-50 highlight + avatar badge
- `item.updated` (from remote): brand-50 highlight flash
- `item.deleted` (from remote): collapse + toast
- `list.renamed`: in-place text update + brand-600 color flash

BSD-5 adds the following behavioral rules on top of those animations:

### LWW Stale-Event Suppression
```
RULE: If an incoming item.updated event has an updated_at older than the client's
current cached updated_at for that item_id, the event is DISCARDED.

VISUAL BEHAVIOR ON DISCARD:
  No animation. The item row does not react. No toast, no flash, nothing.
  Rationale: showing a flash for a discarded event would confuse the user into thinking
  their current view changed when it did not.

SCREEN READER: No announcement for discarded events.
```

### Own-Event Idempotency
```
RULE: Events originating from the current user's own session must not produce duplicate
visual feedback. The client identifies its own events by comparing event payload fields
(e.g., created_by_user_id or updated_by_user_id) against the current session user ID.

VISUAL BEHAVIOR:
  - If event originated from THIS client's session: apply the optimistic update already
    shown (no additional animation). The event confirms the optimistic state — no flash,
    no badge, no toast.
  - If event originated from a DIFFERENT user: apply full LiveUpdateAnimator treatment
    from BSD-3.

EDGE CASE — own event arrives AFTER optimistic rollback:
  If the user's write failed (network error) and the optimistic state was rolled back,
  but the server-side write actually succeeded and the event arrives: the item row will
  animate as if it were a remote event (brand-50 flash, BSD-3 item.updated treatment).
  This is correct behavior — the item's true state is being restored. No special case.
```

---

## Flow 5: `list.renamed` Live Update

BSD-3 `LiveUpdateAnimator` specifies the animation (in-place text + brand-600 color flash 1s).
BSD-5 adds:

```
TRIGGER: list.renamed event arrives on list-channel
EXPECTED BEHAVIOR:
  1. List name heading in detail header: text swaps in-place, brand-600 color for 1s,
     then transitions to neutral-900 (per BSD-3).
  2. Browser tab title (document.title): updates to "[new name] — Shared Todos"
     immediately (no animation possible on tab title).
  3. If user has this list open on /dashboard in another tab: that tab's list card name
     updates on its next REST fetch (no live dashboard card update for renaming — dashboard
     is not subscribed to the list channel, only the user channel).
  4. Breadcrumb (if present in the header): updates in sync with the heading.

SCREEN READER:
  - List heading element: aria-live="polite" on the heading element, or use a visually-
    hidden aria-live region that announces "List renamed to [new name]".
  - Recommendation: visually-hidden live region (separate from the heading) so the
    announcement does not interfere with normal heading navigation.
  - Announcement: "List renamed to [new name]."

OWN-EVENT RULE: If the rename originated from this user (e.g., they just saved a rename
and the WS event echoes back), no additional animation (per Flow 4 own-event idempotency).
```

---

## Flow 6: `list.deleted` Redirect

### Component Specification
```
COMPONENT: ListDeletedRedirect
PURPOSE: Immediately remove a deleted list from a viewer's active session and return them
         to the dashboard with a one-time informational message.
LOCATION: Triggered by list.deleted event on the list-channel while user is on /lists/[id].
```

### Interaction Specification
```
TRIGGER: list.deleted event received on list-channel
EXPECTED BEHAVIOR:
  1. No confirmation dialog shown to the viewer (deletion is the owner's action, not theirs).
  2. All realtime subscriptions for this list-channel are immediately closed
     (WSConnectionManager unsubscribes list:{list_id}).
  3. Client navigates to /dashboard immediately (client-side routing, no page reload).
  4. On /dashboard arrival: a one-time toast appears:
     "The list [list name] has been deleted."
     Toast uses the existing toast component pattern from BSD-2/3 (auto-dismiss 4s).
  5. The deleted list card is NOT shown in the dashboard. If it was previously in the
     "Shared with me" section, it is absent. If this is the owner's own list, it is also
     absent (the owner triggered the deletion themselves, and their dashboard updates
     optimistically at the time of the DELETE request per BSD-2).

LOADING STATE: navigation is immediate; no loading indicator between event and redirect
SUCCESS STATE: /dashboard with toast
ERROR STATE: if navigation fails (abnormal), reload page; /dashboard will not show deleted list
EDGE CASES:
  - User is offline when deletion fires, reconnects: on reconnect, REST re-fetch shows
    list is gone; redirect fires. Toast may not show list name (name not in close payload);
    fallback toast: "A list you were viewing has been deleted."
  - Multiple tabs with same list open: each tab receives the list.deleted event and
    redirects independently. Multiple toasts may appear on dashboard if tabs reconverge.
    Acceptable in v1.
  - Owner deletes their own list while viewing it: deletion is triggered by the owner's
    own action (DELETE /api/v1/lists/[id]). The optimistic UI in BSD-2 already handles
    this (redirect fires at DELETE confirmation). The list.deleted WS event arrives as
    an echo — discard it (own-event idempotency rule from Flow 4).
  - list.deleted arrives for a list the user is not currently viewing (background tab):
    the user-channel does NOT carry list.deleted events; only list-channel subscribers
    receive it. A background tab that is not subscribed to that list-channel will not
    receive the event. On next navigation to /lists/[id]: server returns 404.

SCREEN READER:
  Toast ("The list [name] has been deleted.") is announced via the existing toast
  aria-live="polite" region from BSD-2/3.
```

---

## Flow 7: `collaborator.access_revoked` (WS-Trigger Path)

BSD-3 fully specifies the `RevocationBlockingOverlay` component (non-dismissible,
role="alertdialog", focus-trapped on CTA, "Back to My Lists" → /dashboard).

BSD-5 adds the WS close sequence:

```
TRIGGER: collaborator.access_revoked event received, targeting this user's affected_user_id
SEQUENCE (extending BSD-3):
  1. BSD-3 RevocationBlockingOverlay renders immediately (existing spec).
  2. WSConnectionManager closes the list-channel subscription for this list_id.
     The server closes it simultaneously (per PRD-5 revocation race invariant).
  3. The user-channel (/ws/v1/user) remains open (the user is still authenticated;
     only list-channel access is revoked).
  4. On "Back to My Lists" click: navigate to /dashboard (existing BSD-3 spec).
  5. /dashboard: the revoked list is absent from "Shared with me" section.

OFFLINE-REVOCATION EDGE CASE (from BSD-3):
  User is offline when revoked. On reconnect:
  - WS upgrade to list-channel returns HTTP 404 (stranger access, per PRD-5 invariant).
  - WSConnectionManager receives HTTP 404 on upgrade → ACCESS_LOST state.
  - RevocationBlockingOverlay renders.
  - Flow continues as above.

SCREEN READER: per BSD-3 RevocationBlockingOverlay spec (role="alertdialog", announces heading+body).
```

---

## Flow 8: `collaborator.role_changed` In-Place Control Swap

BSD-3 `LiveUpdateAnimator` specifies the animations (add-item bar collapse/expand, icon
fade, checkbox interactivity, toast copy). BSD-5 adds:

```
TRIGGER: collaborator.role_changed event received, targeting this user's affected_user_id
ANIMATION TIMING BUDGET:
  - Add-item bar height collapse/expand: 200ms (per BSD-3)
  - Item row icon fade in/out: 150ms (per BSD-3)
  - Toast appears: immediately after animations begin (do not wait for animations to finish)

TOAST SPECIFICATION:
  DEMOTED (editor -> viewer):
    Text: "Your access level has changed. You now have view-only access."
    Auto-dismiss: 5,000ms (longer than standard 3s — role change is significant)
    Type: standard info toast (not error — this is a permission change, not an error)

  PROMOTED (viewer -> editor):
    Text: "Your access level has changed. You can now edit this list."
    Auto-dismiss: 5,000ms

RATIONALE FOR TOAST (vs silent swap):
  A silent UI change looks like a rendering bug. The user needs explicit acknowledgment
  that their permissions changed, not just a visual diff they might miss.

OWN-EVENT RULE: role_changed events target a specific affected_user_id. If the current
user is NOT the affected_user_id, no UI change occurs for them (they are not affected).
If the current user IS the affected_user_id, the full animation + toast fires.

SCREEN READER:
  - Toast: role="status", aria-live="polite"
  - The toast text IS the announcement; no additional aria-live region needed.
  - After demotion: the add-item bar's removal should be reflected in aria-hidden
    updates on the collapsed element.
  - After promotion: the add-item bar's appearance should announce via aria-live="polite":
    "You can now add and edit items in this list."

EDGE CASE — role changed while user is mid-edit:
  If user is typing in an item input at the moment of demotion:
  - The add-item bar collapses animation fires.
  - The currently-active input loses interactivity (pointer-events: none + aria-disabled).
  - Any unsaved text in the input is lost (same as BSD-4 forced-logout in-flight edit rule —
    v1 accepts this; draft recovery is out of scope).
  - Toast still fires. The user understands why their input stopped responding.
```

---

## Flow 9: `share.granted` Dashboard Live Append

BSD-3 `LiveUpdateAnimator` specifies: new list card slides into "Shared with me" section +
toast "[Owner] shared [list name] with you as [Viewer|Editor]."

BSD-5 adds the WS channel lifecycle context:

```
TRIGGER: share.granted event received on user-channel (/ws/v1/user)
EXPECTED BEHAVIOR:
  1. Client receives { list_id, list_name, role } payload.
  2. If user is currently on /dashboard:
     a. New list card is constructed from the payload and inserted at the top of
        "Shared with me" section with the standard card enter animation (fade 150ms
        per BSD-2 dashboard loading pattern).
     b. If "Shared with me" section was previously hidden (no shared lists): section
        header animates in alongside the first card (fade 150ms).
     c. Toast: "[Owner display name] shared [list name] with you as [Viewer|Editor]."
        Auto-dismiss: 4,000ms (per BSD-3).
  3. If user is NOT on /dashboard (on a list detail page or elsewhere):
     Toast appears on whatever screen they're on (same text, 4,000ms).
     On next dashboard load: the new list is present (REST response includes it).
  4. If user-channel is not connected (user navigated before connecting):
     List appears on next dashboard load only (best-effort per PRD-5).

SCREEN READER:
  - Toast: role="status", aria-live="polite". Announces: "[Owner] shared [list name]
    with you as [role]."
  - If on dashboard: aria-live="polite" region also announces new card addition:
    "[list name] added to Shared with me."
  - Two consecutive aria-live announcements (card + toast) are acceptable; both are
    polite priority, so they queue.

EDGE CASE — share.granted arrives while "Shared with me" section is loading (skeleton):
  Hold the new card; insert when skeleton resolves to real content (merge into REST response).

EDGE CASE — share.granted for a list already in the user's view (duplicate event):
  Discard silently. Idempotency check: if list_id already exists in the dashboard list,
  no animation, no toast.
```

---

## Flow 10: RealtimePresenceIndicator (Full Specification)

BSD-3 scaffolded this component. BSD-5 graduates it to implementation-ready.

### Component Specification
```
COMPONENT: RealtimePresenceIndicator
PURPOSE: Show which remote collaborators are currently viewing the same list, enabling
         users to know when live collaboration is active.
LOCATION: List detail header. Specifically: right of the list name + rename affordance,
          left of the CollaboratorAvatarStack from BSD-3. Same horizontal row.
VISIBILITY: List detail view (/lists/[id]) only. Never on /dashboard list cards (per
            PRD-5 Non-Goals and BSD-3 Open Design Decision 2).
```

### Visual Specification
```
LAYOUT — presence active (≥1 remote collaborator viewing):
  Flex row, gap 8px, vertically centered with the list name heading.

  [pulse dot 8px] [avatars] ["N viewing"]

  pulse dot:
    - 8px circle, realtime-pulse (#22C55E)
    - Pulse animation: scale 1.0 -> 1.4 -> 1.0 + opacity 0.6 -> 1.0 -> 0.6, 2s infinite ease-in-out
    - Positioned left of the avatar group

  avatars (presence group, distinct from BSD-3 CollaboratorAvatarStack):
    - Show max 3 avatars from those currently present (most recently joined first)
    - Avatar size: 24px (smaller than the BSD-3 CollaboratorAvatarStack's 32px —
      presence is secondary information)
    - Overlap: each avatar offset 10px left of previous, border 1.5px white
    - If more than 3 present: "+N" bubble (24px, neutral-200 bg, neutral-600 text, body-sm)
    - No click affordance on presence avatars (click on BSD-3 CollaboratorAvatarStack opens
      Share Dialog; presence group is separate and non-interactive)

  "N viewing" label:
    - body-sm (12px/400), success-600 (#16A34A)
    - Text: "1 viewing" / "N viewing" (always spelled out; no abbreviation)
    - Tooltip on hover over the entire PresenceIndicator group:
      List of display names: "[Name1], [Name2], [Name3] viewing now"
      Max 5 names shown; if more: "[Name1], [Name2], and N others viewing now"

LAYOUT — no remote collaborators (only current user):
  Component is NOT rendered (hidden, not greyed out). Zero DOM footprint.
  Rationale: showing an empty presence indicator is noise.

OVERFLOW THRESHOLDS:
  DESKTOP (>=1024px): max 3 avatars before "+N"
  MOBILE (<768px):    max 2 avatars before "+N" (space constrained in header)
```

### Interaction Specification
```
TRIGGER: presence.joined event received on list-channel
EXPECTED BEHAVIOR:
  1. If PresenceIndicator was hidden (no remote collaborators): component fades in
     (opacity 0 -> 1, 300ms, per BSD-3 scaffold spec). Pulse dot appears.
  2. New avatar enters from the right (presence-enter: translateX(8px) + opacity 0 -> 1,
     200ms ease-out).
  3. Avatar is prepended to the group (most recently joined first).
  4. If adding the avatar would exceed the visible threshold (3 desktop / 2 mobile):
     leftmost avatar transitions to "+N" bubble, or "+N" increments.
  5. "N viewing" label updates to new count.
  6. Tooltip content updates (available on hover).

TRIGGER: presence.left event received on list-channel
EXPECTED BEHAVIOR:
  1. Avatar exits (presence-exit: opacity 1 -> 0, 150ms ease-in).
  2. Remaining avatars re-order (no animation on re-order — just instant re-layout).
  3. "N viewing" label decrements.
  4. If this was the last remote collaborator: component fades out (opacity 1 -> 0, 300ms).

TRIGGER: WSConnectionManager enters RECONNECTING or RECONNECT_FAILED state
EXPECTED BEHAVIOR:
  1. PresenceIndicator hides immediately (opacity 0, 150ms). The pulse dot stops.
  2. Rationale (from BSD-3 scaffold): cannot confirm who is present while disconnected.
  3. On reconnect success: client clears its local presence roster, re-fetches current
     subscribers via REST (see Reconnect Presence Reconciliation below).

TRIGGER: own connect event (current user connects to list-channel)
EXPECTED BEHAVIOR:
  The current user does NOT appear in their own PresenceIndicator. The server sends
  presence.joined only to OTHER subscribers (per PRD-5 US-506). No client-side filter needed.

PRESENCE ROSTER RECONSTITUTION ON RECONNECT:
  After WSConnectionManager successfully reconnects:
  1. Client re-fetches current subscribers via REST (engineering to confirm endpoint:
     GET /api/v1/lists/{list_id}/presence or equivalent — flag as Integration Note 3).
  2. Local presence roster is replaced with the REST response (not merged — replace).
  3. PresenceIndicator re-renders with the new roster. Fade-in animation plays.
  4. Subsequent presence.joined / presence.left events update from this new baseline.
```

### Data Flow Specification
```
DATA SOURCE: WebSocket presence.joined / presence.left events on list-channel
             + REST re-fetch on reconnect (endpoint TBD — see Integration Note 3)
PRESENCE ROSTER (client-side state):
  Map<user_id, { display_name, avatar_url | null }> — populated on connect and events
EVENT BINDING:
  presence.joined { user_id } -> add user to roster, trigger enter animation
  presence.left   { user_id } -> remove user from roster, trigger exit animation
  disconnect      -> hide indicator, clear roster
  reconnect       -> REST re-fetch -> replace roster -> re-render
```

### Accessibility Specification
```
KEYBOARD:
  PresenceIndicator is non-interactive (no click target). Tab order skips it.
  Exception: tooltip is available on keyboard focus of the indicator group IF it is
  focusable. Recommend: add tabIndex=0 to the group so keyboard users can access the
  tooltip. aria-label="N collaborators viewing: [name list]".

SCREEN READER:
  - Indicator group: role="status", aria-live="polite", aria-atomic="false"
  - On presence.joined: announce "[Display name] is now viewing this list."
  - On presence.left:   announce "[Display name] left this list."
  - On last collaborator leaving: announce "No other collaborators viewing."
  - On disconnect/hide: no announcement (the DisconnectBanner covers connection state).
  - Announcements are polite priority (non-interruptive).

MOTION:
  All presence animations respect prefers-reduced-motion:
  - Skip translateX on avatar enter/exit; use opacity-only.
  - Stop pulse animation (pulse dot stays solid, no scale/opacity loop).
  - Fade transitions (component show/hide) reduced to instant show/hide.
```

---

## Flow 11: Presence Join/Leave Animations

Already specified in Flow 10 (RealtimePresenceIndicator Interaction Specification):
- Join: `presence-enter` (translateX(8px) + opacity 0→1, 200ms ease-out)
- Leave: `presence-exit` (opacity 1→0, 150ms ease-in)
- Component appear/disappear: opacity fade 300ms

No additional tokens or animations needed beyond those in the Design Token Reference above.

---

## Flow 12: Optimistic Update Conflict UX

```
CONTEXT: The current user has made a local edit that is in-flight (POST/PATCH not yet
confirmed by server). Before the server confirms, an item.updated event arrives from
another user for the same item_id.

SCENARIO A — CURRENT USER'S EDIT "WINS" (their updated_at is later):
  The incoming event's updated_at < client's optimistic updated_at.
  LWW rule: incoming event is DISCARDED (per PRD-5 Invariant 5 and Flow 4 above).
  VISUAL: No animation. No toast. User's optimistic edit remains visible.
  The user sees their edit as if nothing happened. Correct.

SCENARIO B — CURRENT USER'S EDIT "LOSES" (incoming updated_at is later):
  The incoming event's updated_at > client's optimistic updated_at.
  LWW rule: incoming event is APPLIED.
  VISUAL:
    1. The item row reverts to the incoming state (overwriting the optimistic edit).
    2. Row flashes brand-50 (BSD-3 item.updated animation, 600ms) — same visual as
       any remote update, signaling the change came from outside.
    3. Toast: "Your edit to '[item title]' was overwritten by [display name]."
       Auto-dismiss: 3,000ms. Non-blocking.
  RATIONALE FOR TOAST: Silent overwrite looks indistinguishable from a rendering bug.
  A toast tells the user what happened without blocking their workflow.

SCENARIO C — EDIT IN PROGRESS, INCOMING EVENT IS FOR THE SAME ITEM:
  The user's cursor is inside an item's edit input. An item.updated event arrives.
  VISUAL: Do NOT update the input's value while the user is actively typing in it.
  Wait until the user's input loses focus (blur) or their edit is submitted:
    - If user submits: their submitted value is the authoritative latest_updated_at.
      Apply LWW normally.
    - If user cancels (Escape, blur without submit): apply the incoming event state.
  RATIONALE: Updating an input under the user's cursor while they are typing is
  disorienting. The blur-then-apply pattern is the least-surprising behavior.

SCREEN READER:
  Scenario B toast: role="status", aria-live="polite".
  Announces: "Your edit to [item title] was overwritten by [display name]."
```

---

## Flow 13: Stale-Data Warning After Reconnect-Abandoned

See Component: StaleDataBanner above. Summary:

```
TRIGGER: WSConnectionManager enters RECONNECT_FAILED state
VISUAL: StaleDataBanner ("You may be viewing outdated data. Reload to see the latest.")
        appears below DisconnectBanner (failed variant).
OPTIONAL content degradation: item row opacity 0.75 (engineering call, see Open Design
Decision 1).
CLEAR: both banners dismissed on successful manual reconnect (user clicked "Reconnect",
new cycle succeeded). No explicit "dismiss" button on StaleDataBanner.
```

---

## Flow 14: BSD-4 Integration — Auth-Close Code Handoff

### Integration Note (see also Integration Notes section below)

```
TRIGGER: WSConnectionManager receives WS close code 1008 (policy violation)

THIS FLOW PRODUCES NO WS-SPECIFIC UI.

SEQUENCE:
  1. WSConnectionManager receives close code 1008.
  2. WSConnectionManager does NOT enter RECONNECTING state. It enters AUTH_FAILED state.
  3. No DisconnectBanner. No StaleDataBanner. No toast from BSD-5.
  4. The close code triggers the shared HTTP client's auth-check pathway:
     The REST re-fetch that the reconnection logic would normally attempt returns 401.
  5. BSD-4 SilentRefreshInterceptor intercepts the 401, calls POST /api/v1/auth/refresh.
  6. If /refresh returns 401: BSD-4 ForcedLogoutHandler fires.
     → Redirect to /login with SessionExpiredBanner (BSD-4 spec).
  7. If /refresh returns 200 (session renewed): the WS reconnection proceeds normally
     (AUTH_FAILED → RECONNECTING → CONNECTED). BSD-5 DisconnectBanner appears briefly
     during the reconnection window.

RATIONALE: A WS auth failure is a session-level event, not a WS-level event. BSD-4
already owns the session-expiry UX. BSD-5 deliberately does not duplicate it. The two
layers coordinate via the shared HTTP client's interceptor.

DISTINCTION — 1008 with HTTP 404 on list-channel:
  If the WS upgrade handshake itself returns HTTP 404 (access revoked or list deleted),
  this is an ACCESS_LOST state (not AUTH_FAILED). BSD-5 delegates to:
  - BSD-3 RevocationBlockingOverlay (collaborator.access_revoked path), OR
  - Flow 6 ListDeletedRedirect (list.deleted path).
  The 404 vs 401 distinction on the WS upgrade handshake is what separates the two.
```

---

## Connection Lifecycle State Diagram (ASCII)

```
Page navigates to /lists/[id]
         │
         ▼
   CONNECTING ──────── WS upgrade succeeds (HTTP 101) ──────────────────> CONNECTED
         │                                                                      │
         │ WS upgrade returns HTTP 401 (no session)                           │
         └─────────────────────────────────────────────────────────────────> AUTH_FAILED
         │                                                                    (BSD-4)
         │ WS upgrade returns HTTP 404 (access revoked / list gone)
         └─────────────────────────────────────────────────────────────────> ACCESS_LOST
                                                                             (BSD-3 / Flow 6)

CONNECTED
  │  ← remote mutation events → LiveUpdateAnimator (BSD-3)
  │  ← presence.joined/left   → RealtimePresenceIndicator (Flow 10)
  │  ← list.deleted           → ListDeletedRedirect (Flow 6)
  │  ← collaborator.*         → RevocationBlockingOverlay / role-change swap (Flow 7/8)
  │  ← share.granted          → dashboard append (Flow 9)
  │
  │ WS closes (code ≠ 1008): TRANSIENT DISCONNECT
  ▼
RECONNECTING (attempt 1 of 5)
  │ DisconnectBanner "Reconnecting... Attempt 1 of 5" appears
  │
  │ REST re-fetch → new baseline
  │ WS re-open attempt
  │  ├─ success → CONNECTED (DisconnectBanner slides away)
  │  └─ failure → attempt count++, wait (500ms/1s/2s/5s/10s), retry
  │
  │ 5 consecutive failures
  ▼
RECONNECT_FAILED
  │ DisconnectBanner switches to failed variant (warning-50)
  │ StaleDataBanner appears
  │ [Optional] item rows dimmed
  │
  │ User clicks "Reconnect"
  └──────> RECONNECTING (attempt count reset to 1)

  │ WS close code 1008 at any point
  └──────> AUTH_FAILED → BSD-4 ForcedLogoutHandler
```

---

## ASCII Wireframes

### List Detail Header — PresenceIndicator Active (Desktop)

```
┌──────────────────────────────────────────────────── List Detail Header ─────┐
│                                                                              │
│  ← Back    [●] My Shopping List         [●] 2 viewing  [A][B][+1]  [Share]  │
│            (list name, editable        ↑              ↑            ↑        │
│             for owner)        RealtimePresence   Avatar  Collaborator        │
│                               Indicator         Stack   AvatarStack (BSD-3) │
│                               (pulse dot +              (non-presence,       │
│                                "N viewing" +             opens Share Dialog) │
│                                24px avatars)                                 │
└─────────────────────────────────────────────────────────────────────────────┘

Key:
  [●] = 8px pulse dot, realtime-pulse green (#22C55E)
  [A][B][+1] = 24px presence avatars, max 3 desktop, overlap 10px
  "2 viewing" = body-sm, success-600
  [Share] = BSD-3 Share button
```

### List Detail Header — Presence on Mobile (<768px)

```
┌──────────────── Mobile Header ─────────────────┐
│  ← My Shopping List          [●][A][+3] [Share]│
│                               ↑                │
│                       presence dot + max 2     │
│                       avatars + "+N" before    │
│                       CollaboratorAvatarStack  │
└────────────────────────────────────────────────┘
```

### DisconnectBanner — Retrying State (Desktop)

```
┌──────────────────────── 960px content column ──────────────────────────┐
│  [⟳] Reconnecting...                              Attempt 2 of 5       │ ← info-50 bg, info-600 border-bottom
└────────────────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────────────────┐
│  [List item content — normal, readable]                                 │
└─────────────────────────────────────────────────────────────────────────┘
```

### DisconnectBanner — Failed State + StaleDataBanner (Desktop)

```
┌──────────────────────── 960px content column ──────────────────────────┐
│  Live updates unavailable.                          [Reconnect]         │ ← warning-50 bg, warning-600 border-bottom
└────────────────────────────────────────────────────────────────────────┘
┌────────────────────────────────────────────────────────────────────────┐
│  [⚠] You may be viewing outdated data. Reload to see the latest.       │ ← warning-50 bg, warning-200 border-bottom
└────────────────────────────────────────────────────────────────────────┘
┌────────────────────────────────────────────────────────────────────────┐
│  [List item content — optionally dimmed to opacity 0.75]               │
└────────────────────────────────────────────────────────────────────────┘
```

### DisconnectBanner — Mobile (<768px)

```
┌───────────── Mobile (100% - 32px) ─────────────┐
│  [⟳] Reconnecting...                           │ ← retrying (no attempt counter on mobile)
└────────────────────────────────────────────────┘

┌───────────── Mobile (100% - 32px) ─────────────┐
│  Live updates unavailable.   [Reconnect]        │ ← failed (48px height for touch target)
└────────────────────────────────────────────────┘
```

---

## Accessibility Specification (Consolidated)

```
KEYBOARD NAVIGATION:
  New interactive elements introduced:
  - DisconnectBanner "Reconnect" button (failed variant): focusable, Enter/Space triggers
  - RealtimePresenceIndicator group: tabIndex=0 for tooltip access, not otherwise interactive
  All other new elements are non-interactive (banners, presence avatars, toast).

SCREEN READER ANNOUNCEMENTS (summary):
  DisconnectBanner retrying:  role="status", aria-live="polite" — announced once on appear;
                              attempt counter updates announced on each increment
  DisconnectBanner failed:    role="alert", aria-live="assertive" — failure warrants assertive
  StaleDataBanner:            role="status", aria-live="polite" — announced once on appear
  RealtimePresenceIndicator:  role="status", aria-live="polite", aria-atomic="false"
                              — presence.joined: "[Name] is now viewing this list."
                              — presence.left:   "[Name] left this list."
                              — last user leaves: "No other collaborators viewing."
  list.renamed:               visually-hidden aria-live="polite" region: "List renamed to [name]."
  list.deleted toast:         role="status", aria-live="polite" — via existing toast region
  collaborator.role_changed toast: role="status", aria-live="polite"
  share.granted toast:        role="status", aria-live="polite"
  edit-overwritten toast:     role="status", aria-live="polite"

FOCUS MANAGEMENT:
  No new focus traps introduced (RevocationBlockingOverlay focus trap is BSD-3's).
  DisconnectBanner appears/disappears without stealing focus.
  RealtimePresenceIndicator appears/disappears without stealing focus.
  All state changes communicate via aria-live, not focus movement.

MOTION (prefers-reduced-motion):
  ALL animations specified in this BSD must check prefers-reduced-motion:
  - presence-enter / presence-exit: skip translateX, use opacity-only
  - reconnect-banner-enter / reconnect-banner-exit: skip translateY, use opacity-only
  - control-fade-in / control-fade-out: keep opacity transitions (they convey state change)
  - Pulse animation on presence dot: stop loop; show solid dot
  - Item row dimming (StaleDataBanner optional): skip entirely under reduced-motion
  - All BSD-3 animations referenced here (LiveUpdateAnimator etc.) follow BSD-3's own
    reduced-motion handling — BSD-5 adds no new rules for those.

COLOR CONTRAST:
  DisconnectBanner retrying text (neutral-700 on info-50): WCAG AA compliant
  DisconnectBanner failed text (neutral-700 on warning-50): WCAG AA compliant
  StaleDataBanner text (neutral-700 on warning-50): WCAG AA compliant
  "N viewing" label (success-600 on white): WCAG AA compliant (4.5:1+)
  Dimmed item rows (opacity 0.75 on white): neutral-900 text remains AA compliant
```

---

## Responsive Breakpoints Summary

| Component | Mobile (<768px) | Tablet (768–1023px) | Desktop (≥1024px) |
|-----------|----------------|---------------------|-------------------|
| DisconnectBanner (retrying) | 100%-32px, 48px height, no attempt counter | 100% content width, 40px | 960px column, 40px, attempt counter |
| DisconnectBanner (failed) | 100%-32px, 48px, Reconnect button full-width or inline | 100% content width, 40px, Reconnect right-aligned | 960px column, 40px, Reconnect right-aligned |
| StaleDataBanner | 100%-32px, 36px, text truncates to 1 line | 100% content width, 36px | 960px column, 36px |
| RealtimePresenceIndicator | Max 2 avatars, "+N", "N viewing" label hidden (icon only) | Max 3 avatars, "N viewing" label | Max 3 avatars, "N viewing" label, tooltip |

---

## Integration Notes for Engineering

1. **BSD-4 ForcedLogoutHandler coordination:** WS close code 1008 must not trigger BSD-5
   reconnection logic. WSConnectionManager must detect code 1008, enter AUTH_FAILED state,
   and allow the BSD-4 HTTP layer to handle the session-expiry flow. Engineering must ensure
   the WSConnectionManager's close-code handler branches before starting any backoff timer.

2. **BSD-3 cross-references:**
   - `RevocationBlockingOverlay` (BSD-3): BSD-5 adds step 2 (close list-channel WS after
     overlay renders) and the offline-revocation edge case path.
   - `LiveUpdateAnimator` (BSD-3): BSD-5 adds own-event idempotency rule (Flow 4) and
     LWW stale-event suppression rule (Flow 4). These are behavioral additions, not visual.
   - `RealtimePresenceIndicator` (BSD-3 scaffold): fully specified in BSD-5 Flow 10.
     BSD-3 §RealtimePresenceIndicator is superseded by BSD-5 for implementation purposes.

3. **Presence roster REST endpoint:** BSD-5 requires a REST endpoint to re-fetch the current
   presence roster after reconnection (Flow 10, Presence Roster Reconstitution). PRD-5 does
   not specify this endpoint. Engineering-lead to confirm: does `GET /api/v1/lists/{id}`
   include current subscribers, or is a separate `GET /api/v1/lists/{id}/presence` needed?
   If the latter, it must be added to PRD-5 scope.

4. **WS close code catalogue:** Engineering must agree on which close codes are treated as
   transient (→ RECONNECTING) vs. auth failures (→ AUTH_FAILED via BSD-4) vs. access-lost
   (→ BSD-3/Flow 6). Minimum recommended mapping:
   - 1001 Going Away, 1006 Abnormal Close, 1011 Internal Error → RECONNECTING
   - 1008 Policy Violation → check HTTP status of upgrade response:
     - HTTP 401 → AUTH_FAILED (BSD-4 ForcedLogoutHandler)
     - HTTP 404 → ACCESS_LOST (BSD-3 / Flow 6)
   - 1000 Normal Closure initiated by server: check reason string or a custom sub-protocol
     field to distinguish "list deleted" from "access revoked" before routing.

5. **Toast component reuse:** BSD-5 specifies multiple toasts (role-change, edit-overwritten,
   list-deleted, share-granted). All should use the same toast component/queue from BSD-2/3
   to prevent simultaneous toast stacking. Engineering to confirm maximum concurrent toasts
   displayed (recommend: 1 at a time, queue remaining; or max 2 stacked with oldest on top).

6. **User-channel connection (/ws/v1/user):** The DisconnectBanner is scoped to list-channel
   disconnections (shown on /lists/[id] only). If the user-channel (/ws/v1/user) disconnects
   while the user is on /dashboard, no banner is shown — the next share.granted event will
   be missed and the user sees the new list on next REST load. This is intentional (best-effort
   per PRD-5). Engineering to confirm: does the user-channel reconnect independently from the
   list-channel, or are they coupled?

7. **Debounce before save on rapid keystrokes:** PRD-5 Non-Goals state that server-side
   debouncing is out of scope. The client should debounce item text saves (e.g., 500ms after
   last keystroke) before sending PATCH requests. This reduces LWW conflicts and `item.updated`
   fan-out volume. Not specified in BSD-2 — flag for engineering-lead to add to PR-5 scope if
   not already handled.

---

## Open Design Decisions

1. **Item row dimming under StaleDataBanner (opacity 0.75):** Specified as optional in
   StaleDataBanner component. Engineering call — no product sign-off needed. If dimming
   causes readability concerns or is complex to implement (especially with mixed interactive
   and non-interactive rows), omit it entirely. The StaleDataBanner text is sufficient to
   communicate the stale-data state.

2. **Toast queue behavior:** Multiple real-time events can fire in rapid succession (e.g.,
   a batch import creates 10 items, producing 10 `item.created` events). Engineering should
   decide: (a) show a toast per event (potentially overwhelming), (b) coalesce rapid toasts
   of the same type ("N items added by [name]"), or (c) suppress toasts for bulk events above
   a threshold. BSD-5 does not prescribe — coalescing is a UX improvement, not a correctness
   requirement. Flag for engineering-lead.

3. **Reconnect button placement on mobile (DisconnectBanner failed variant):** On mobile,
   the 100%-32px banner at 48px height has limited horizontal space. Two options: (a) inline
   "Reconnect" link after the message text, or (b) full-width "Reconnect" button below the
   message text (requires ~72px banner height). Either is acceptable. Engineering call.
