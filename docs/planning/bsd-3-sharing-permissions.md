# BSD-3: Sharing UI + Realtime Indicators

**Version:** 1.0
**Date:** 2026-04-19
**Status:** Draft
**Author:** ux-designer
**PRD Reference:** PRD-3: Sharing & Permissions

---

## Overview

This BSD covers the sharing UI for a list owner (invite collaborator, manage member list, change roles, revoke access) and the realtime indicators shown to all users during live collaboration (presence, live-update animations, role change feedback, access revocation feedback). It also specifies how the `share.granted` event updates a collaborator's dashboard in real time.

---

## Design Token Reference

Inherits all tokens from BSD-1 and BSD-2. Additional tokens:

```
COLOR:
  owner-badge-bg: #F3F4F6    -- neutral-100
  owner-badge-text: #374151  -- neutral-700
  editor-badge-bg: #FFF7ED   -- orange-50
  editor-badge-text: #C2410C -- orange-700
  viewer-badge-bg: #F0FDF4   -- green-50
  viewer-badge-text: #15803D -- green-700
  revoke-hover: #FEF2F2      -- error-50 (row hover when revoke is hovered)

SPACING:
  member-row-height: 56px
  avatar-size: 32px
  avatar-border: 2px white

AVATAR:
  - Circular crop, 32px diameter
  - Background: initials on brand-100 if no photo
  - Initials: first letter of display name, brand-700, body-sm/600
```

---

## Component: Share Dialog

### Component Specification
```
COMPONENT: ShareDialog
PURPOSE: Allow the list owner to invite new collaborators, view existing members, change roles, and revoke access.
LOCATION: Modal overlay, triggered from:
  - "Share" button in list detail header
  - "Share" item in overflow menu on list card
VISIBILITY: Owner only -- non-owners never see this dialog trigger
```

### Visual Specification
```
LAYOUT:
  - Modal overlay: rgba(0,0,0,0.4) backdrop
  - Modal card: white, radius lg, shadow xl
    - Width: 480px on desktop, 100% - 32px on mobile
    - Max-height: 80vh; overflow-y scroll on member list section
  - Modal header: "Share [list name]" (body-base/600) left, X close button right
  - Body sections (top to bottom):
    1. Invite section
    2. Divider (1px neutral-200), margin 16px 0
    3. Members section ("People with access" sub-header)
  - Padding: 24px (modal card), sections inherit padding

INVITE SECTION:
  - Sub-header: "Add collaborator" (body-sm/500, neutral-700), margin-bottom 8px
  - Inline form: [search input | role selector | Invite button] in a flex row
  - Search input:
    - Placeholder: "Email or username"
    - flex-grow: 1
    - height: 36px, radius md, border 1px neutral-200
    - Type: text (not email -- accepts username too)
  - Role selector:
    - Dropdown / select: "Viewer" | "Editor" -- defaults to "Viewer"
    - width: 96px, height 36px, radius md, border 1px neutral-200
    - Compact label (no full label text, just the role name)
  - Invite button:
    - "Invite" label, brand-600, height 36px, radius md
    - Disabled state: opacity 0.5, when input empty
  - Result area below the form row (replaces nothing -- shown contextually):
    - Error state: body-sm, error-600 text below input
    - Pending confirmation: shown while request in-flight

MEMBERS SECTION:
  - Sub-header: "People with access" (body-sm/500, neutral-500), margin-bottom 8px
  - Owner row (always first, non-interactive):
    - Avatar + display name + "(you)" if current user + "Owner" badge
    - No actions (owner cannot be removed)
  - Collaborator rows (one per collaborator):
    - Avatar + display name + email (body-sm, neutral-500)
    - Role badge (dropdown selector for editing: "Viewer" | "Editor")
    - Remove (trash) icon, right-aligned, neutral-400, hover error-500

EMPTY COLLABORATORS STATE:
  - "No collaborators yet." (body-sm, neutral-400, italic)

ROLE BADGE / SELECTOR (on member rows):
  - When read-only (not owner viewing): plain badge (no interaction)
  - When owner is viewing: clicking role badge opens inline dropdown
    to change between Viewer and Editor
```

### Interaction Specification

```
ELEMENT: Search input
TRIGGER: input change (typing)
EXPECTED BEHAVIOR:
  1. No autocomplete dropdown in v1 (no live user search -- entry is exact email or username)
  2. Input accepts any text
  3. "Invite" button enabled when input is non-empty after trim

ELEMENT: Role selector (invite form)
TRIGGER: change
EXPECTED BEHAVIOR:
  1. Update selected role value for the pending invite
  2. Roles: "Viewer" (default) | "Editor"
  3. Tooltip on hover: "Viewers can read, Editors can edit items"

ELEMENT: "Invite" button
TRIGGER: click
EXPECTED BEHAVIOR:
  1. Validate: input non-empty after trim
  2. Show loading state: button spinner, input + role selector disabled
  3. POST /api/v1/lists/[id]/shares { identifier: string, role: "viewer"|"editor" }
  4. On 201: clear input, show success feedback below input:
     "Invited [display name] as [Role]." (body-sm, success-600)
     Add new member row to bottom of member list with enter animation
  5. On 404 (no account found): show error below input:
     "No account found with that email or username."
  6. On 409 (already a collaborator): show error:
     "This user is already a collaborator. Use the role selector below to change their role."
  7. On 400 (self-share): show error:
     "You cannot share a list with yourself."
  8. On 403: show error: "Only the list owner can share this list."
  9. On 429: show error: "Too many invite requests. Please wait before trying again."
  10. On 500 / network: show error: "Something went wrong. Please try again."
  11. On any error or success: re-enable input, role selector, button
LOADING STATE: spinner in Invite button, input + role selector disabled
SUCCESS STATE: inline "Invited..." feedback, new member row appears, input cleared, refocus input
ERROR STATE: error text below search input (error-600, body-sm)
EDGE CASES:
  - Email lookup: identifier could be email OR username -- server resolves
  - Same user already owner (self-share): step 7
  - Invite the same user twice: step 6 (409)
  - User account exists but user lookup reveals it: anti-enumeration -- PRD-3 specifies
    "No account found." for both "no account" and "found but can't share" cases.
    BSD implements: 404 response -> "No account found." only (do not say why)

ELEMENT: Role badge selector (member row)
TRIGGER: click on role badge
EXPECTED BEHAVIOR:
  1. Open inline dropdown with two options: "Viewer" | "Editor"
     Current role is checked/highlighted
  2. On select different role: PATCH /api/v1/lists/[id]/shares/[user_id] { role: newRole }
  3. On 200: update badge to new role, animate transition
     Collaborator receives collaborator.role_changed realtime event
     Their UI controls update live without reload (BSD-2 covers this)
  4. On 403: show toast "Only the list owner can change roles."
  5. On 500 / network: show toast error, badge reverts to original role
  6. On select same role: close dropdown, no request
LOADING STATE: badge shows spinner while PATCH in-flight; dropdown remains open
SUCCESS STATE: badge updates to new role
ERROR STATE: toast, badge reverts
EDGE CASES:
  - Owner demotes themselves: not possible (owner row has no role selector)
  - Role change while collaborator is active in session: handled by realtime event (BSD-2)
  - Network offline: optimistic update not applied; show offline toast, keep original

ELEMENT: Remove (trash) icon on member row
TRIGGER: click
EXPECTED BEHAVIOR:
  1. Inline confirmation appears in the row (replace row actions with):
     "Remove [display name]? [Cancel] [Remove]"
     Row background tints to revoke-hover (error-50) during confirmation
  2. "Remove" confirm: DELETE /api/v1/lists/[id]/shares/[user_id]
  3. On 204: remove row with exit animation (height collapse 120ms)
     Collaborator receives collaborator.access_revoked realtime event
  4. On 403: show toast "Only the list owner can revoke access."
  5. On 500: show toast, row remains, confirmation dismissed
  6. "Cancel": dismiss confirmation, row returns to normal
LOADING STATE: row shows loading overlay (opacity 0.6) during DELETE in-flight
SUCCESS STATE: row removed with animation
ERROR STATE: toast, row preserved
EDGE CASES:
  - Revoke while collaborator actively viewing list: collaborator gets realtime event,
    their UI redirects to dashboard (BSD-2 covers the collaborator's perspective)
  - Double-click Remove: second click blocked (button disabled after first)
  - Escape key: dismisses confirmation
  - Last collaborator removed: members section shows "No collaborators yet."

ELEMENT: X close button / backdrop click
TRIGGER: click
EXPECTED BEHAVIOR:
  1. Close dialog (fade + scale-down 150ms)
  2. No pending operations cancelled (invite/remove in-flight continue)
  3. Return focus to trigger element ("Share" button in list header)
```

### Invitation Success Inline Feedback
```
COMPONENT: InviteSuccessFeedback
LOCATION: Below the invite form row
APPEARANCE:
  - Text: "Invited [display name] as [Editor|Viewer]."
  - Color: success-600
  - Font: body-sm
  - Auto-dismiss: 4000ms (fades out)
  - OR: replaced by next error/success if user sends another invite
```

### Data Flow Specification
```
LOAD (on dialog open):
  GET /api/v1/lists/[id]/shares
  RESPONSE: [{ user_id, display_name, email, role, added_at }]
  Plus owner from list metadata
  BINDING: populate member list

INVITE:
  POST /api/v1/lists/[id]/shares
  REQUEST: { identifier: string, role: "viewer" | "editor" }
  RESPONSE:
    201: { user_id, display_name, email, role }
    404: { error: "user_not_found" }
    409: { error: "already_collaborator" }
    400: { error: "self_share" }
    403: { error: "forbidden" }
    429: { error: "rate_limited" }

ROLE CHANGE:
  PATCH /api/v1/lists/[id]/shares/[user_id]
  REQUEST: { role: "viewer" | "editor" }
  RESPONSE: 200 { role }

REVOKE:
  DELETE /api/v1/lists/[id]/shares/[user_id]
  RESPONSE: 204 {}
```

### Navigation Specification
```
ENTRY POINTS: "Share" button on /lists/[id], "Share" in overflow menu on /dashboard list card
EXIT POINTS: X close, backdrop click -> return to origin screen
DEEP LINK: No dedicated URL; dialog is a modal overlay
```

### Accessibility Specification
```
KEYBOARD:
  - Modal: role="dialog", aria-modal="true", aria-labelledby=dialog-title-id
  - Tab order: X close -> search input -> role selector -> Invite button -> member rows
  - Each member row: role="listitem"
  - Role badge selector: role="combobox" or native select
  - Remove button: aria-label="Remove [display name] from list"
  - Confirmation inline: role="alertdialog", trap focus within the row

SCREEN READER:
  - On new member added: aria-live="polite" region announces "Invited [name] as [role]"
  - On member removed: announces "[name] removed"
  - Role changes: announces "Changed [name]'s role to [role]"
  - Error messages: role="alert"

FOCUS MANAGEMENT:
  - On dialog open: focus search input
  - On dialog close: return focus to "Share" button
  - On inline remove confirmation: focus "Remove" confirm button
  - On confirmation dismissed: return focus to trash icon
  - On invite success: focus search input (ready for next invite)
```

---

## Component: Collaborator Avatar Stack

### Component Specification
```
COMPONENT: CollaboratorAvatarStack
PURPOSE: Show a compact visual list of who has access to the current list, serving as an entry point to the Share Dialog.
LOCATION: List detail header, right of list name row.
```

### Visual Specification
```
LAYOUT:
  - Avatars overlap: each avatar offset 16px left of previous, border 2px white (avatar-border)
  - Show max 3 avatars; if more: "+N" bubble (same size as avatar, neutral-200 bg, neutral-600 text)
  - Avatar size: 32px circle
  - Cursor: pointer (entire stack is clickable -> opens Share Dialog)
  - Tooltip on hover over individual avatar: shows display name + role

AVATAR CONTENT:
  - If user has profile photo: circular crop of photo
  - If no photo: circular bg (brand-100), initials (first letter of display name, brand-700)

PRESENCE INDICATOR:
  - Active collaborator (currently viewing list): green dot (8px, realtime-pulse #22C55E)
    positioned bottom-right of avatar, border 1.5px white
  - Inactive (has access but not currently viewing): no dot
```

### Interaction Specification
```
ELEMENT: Avatar stack (clickable area)
TRIGGER: click
EXPECTED BEHAVIOR:
  1. Open Share Dialog (same behavior as "Share" button)
  2. Note: this affordance is available to ALL roles (owner, editor, viewer) as a way
     to SEE who has access -- but non-owners see a read-only version of the Share Dialog
     (see Share Dialog -- Read-Only Variant below)

ELEMENT: Individual avatar
TRIGGER: hover
EXPECTED BEHAVIOR:
  1. Show tooltip: "[Display name] -- [Editor|Viewer|Owner]"
  2. If currently active (green dot): tooltip adds " -- Viewing now"
```

---

## Component: Share Dialog -- Read-Only Variant (Non-Owner View)

### Component Specification
```
COMPONENT: ShareDialogReadOnly
PURPOSE: Show collaborators (editor/viewer) who else has access to the list -- read-only, no management actions.
LOCATION: Triggered by avatar stack click from non-owner users.
```

### Visual Specification
```
LAYOUT:
  - Same modal frame, width 400px
  - Header: "People with access"
  - Body: member list only (no invite section)
  - Member rows: avatar + name + role badge; NO remove icons, NO role selectors
  - Footer: "Close" button only
  - Read-only note at bottom: "Only the list owner can manage access."
    (body-sm, neutral-400, italic)
```

### Accessibility Specification
```
- role="dialog", aria-label="People with access to [list name]"
- Member rows: read-only list items, no interactive controls
```

---

## Component: Realtime Presence Indicator

### Component Specification
```
COMPONENT: RealtimePresenceIndicator
PURPOSE: Show that at least one other collaborator is currently viewing the list -- indicates live collaboration is active.
LOCATION: List detail header, right of list name row, left of avatar stack.
```

### Visual Specification
```
LAYOUT (when active collaborators present):
  - Green pulsing dot (8px, realtime-pulse) + "Live" label (body-sm/500, success-600)
  - Pulse animation: scale 1.0 -> 1.4 -> 1.0, 2s infinite ease-in-out, opacity 0.6 -> 1.0 -> 0.6
  - Tooltip on hover: "N collaborator(s) viewing now"

LAYOUT (no active collaborators / only you):
  - Not shown at all (hidden, not greyed out)
```

### Interaction Specification
```
TRIGGER: WebSocket/SSE channel presence event (user joins or leaves list channel)
EXPECTED BEHAVIOR:
  1. On first remote collaborator joining channel: indicator fades in (opacity 0 -> 1, 300ms)
  2. On last remote collaborator leaving: indicator fades out (opacity 1 -> 0, 300ms)
  3. Count in tooltip updates as collaborators join/leave
  4. No sound or intrusive notification -- purely visual

EDGE CASES:
  - Connection drops: hide indicator (cannot confirm others are present)
  - Reconnect: re-evaluate presence after full state re-fetch
  - Only the list owner is viewing: no indicator shown (no "remote" collaborators present)
```

---

## Component: Live Update Animations (Realtime Item Events)

### Component Specification
```
COMPONENT: LiveUpdateAnimator
PURPOSE: Visually differentiate items that just changed due to a remote collaborator's action (not the local user's action).
LOCATION: Applied to ItemRow components in list detail view when realtime events arrive.
```

### Visual Specification and Behavior

```
item.created (from remote user):
  - New ItemRow slides in from below (translate-y 8px -> 0 + opacity 0 -> 1, 200ms ease-out)
  - Row briefly highlights: background flashes brand-50 (#EEF2FF) fading to white, 800ms ease
  - Small avatar badge of the creating user floats near the checkbox for 3s then fades
    (body-sm, neutral-500: "Added by [name]" tooltip on hover; avatar 20px)

item.updated (from remote user):
  - Row background flashes brand-50 fading to white, 600ms ease
  - If this is a done-state change: checkbox transitions with the standard done animation
  - No avatar badge (too noisy for frequent updates)

item.deleted (from remote user):
  - If no one is editing that item: row collapses (height 0 + opacity 0, 150ms ease-in) + toast:
    "An item was deleted by [display name]."
  - If local user has that item open for editing: close edit mode first, then animate removal,
    then toast: "[display name] deleted the item you were editing."

list.renamed (from remote user):
  - List name heading updates in-place with a brief highlight (text color brand-600 for 1s, then neutral-900)
  - Browser tab title updates (document.title)

collaborator.role_changed (received by affected collaborator):
  DEMOTED (editor -> viewer):
    - Add item bar: animate out (height collapse 200ms), replaced by viewer notice
      "You can view but not edit this list"
    - Item row edit/delete icons: fade out (opacity 1 -> 0, 150ms)
    - Item row checkboxes: become non-interactive (cursor:default, aria-disabled)
    - Toast: "Your access level has changed. You now have view-only access."
  PROMOTED (viewer -> editor):
    - Viewer notice bar: animate out, replaced by add-item bar (height expand 200ms)
    - Item row edit/delete icons: fade in
    - Checkboxes: become interactive
    - Toast: "Your access level has changed. You can now edit this list."

collaborator.access_revoked (received by revoked user):
  - Overlay the entire list page with a centered blocking message:
    Dialog (non-dismissible):
      - Heading: "Access removed"
      - Body: "Your access to this list has been removed by the owner."
      - CTA button: "Back to My Lists" (brand-600)
  - On CTA click: navigate to /dashboard
  - Meanwhile: all realtime subscriptions unsubscribed
  - List page is NOT accessible after this point (any refresh returns 404/403 per security spec)

share.granted (received by newly-added collaborator):
  - If collaborator is on /dashboard: new list card slides into "Shared with me" section
    (same enter animation as new list creation)
    Toast: "[Owner display name] shared [list name] with you as [Viewer|Editor]."
  - If collaborator is NOT on /dashboard: they see the list on next dashboard load
    (polling-based discovery is acceptable per PRD-3 Non-Goals)
```

---

## Component: Revocation Blocking Overlay

### Component Specification
```
COMPONENT: RevocationBlockingOverlay
PURPOSE: Immediately block access to a list for a user whose access was just revoked mid-session.
LOCATION: Full-page overlay over /lists/[id], rendered when collaborator.access_revoked event arrives.
```

### Visual Specification
```
LAYOUT:
  - Full viewport overlay: rgba(255,255,255,0.95) backdrop (semi-opaque white, blurs list behind it)
  - Centered card: white, radius lg, shadow xl, width 380px, padding 32px
  - Icon: lock SVG (48px, neutral-400), center-aligned
  - Heading: "Access removed" (heading-lg, neutral-900)
  - Body: "Your access to this list has been removed by the owner." (body-base, neutral-700)
  - CTA: "Back to My Lists" (brand-600, full width, height 40px)
  - No dismiss option -- this overlay is non-dismissible
```

### Interaction Specification
```
TRIGGER: collaborator.access_revoked WebSocket/SSE event (targeting this user's ID)
EXPECTED BEHAVIOR:
  1. Overlay renders immediately over the list page (z-index above all content)
  2. Focus moves to "Back to My Lists" button
  3. All keyboard interaction with the list behind is blocked (focus trap on overlay)
  4. "Back to My Lists" click: navigate to /dashboard
  5. All realtime subscriptions unsubscribed on navigate
  6. Subsequent direct navigation to /lists/[id]: server returns 404/403, client shows
     "List not found." on /dashboard (toast)
EDGE CASES:
  - User is offline when revoked: overlay appears when they reconnect and re-subscribe to channel
  - Multiple tabs with same list open: all tabs should receive the event and show overlay
  - User tries to right-click / copy URL: OK -- URL navigation is blocked server-side anyway
```

### Accessibility Specification
```
- Overlay: role="alertdialog", aria-modal="true", aria-label="Access to this list has been removed"
- Focus trap: only the CTA button is focusable
- No escape key dismiss (non-dismissible by design)
- Screen reader: announces the heading and body text on render
```

---

## Component: Role Badges (Reference)

```
COMPONENT: RoleBadge
PURPOSE: Consistently display role labels across the app.
LOCATIONS: List cards (dashboard), list detail header, share dialog member rows, share dialog read-only.

VARIANTS:
  owner:   neutral-100 bg, neutral-700 text, "Owner"
  editor:  editor-badge-bg, editor-badge-text, "Editor"
  viewer:  viewer-badge-bg, viewer-badge-text, "Viewer"
  shared:  shared-badge-bg, shared-badge-text, "Shared" (on owned lists that have collaborators)

ANATOMY:
  - Padding: 2px 8px
  - Border-radius: 4px (sm)
  - Font: body-sm (12px/400/500 depending on context)
  - No border
```

---

## Navigation Flow: Sharing

```
/dashboard (list card, owner)
  -> "..." overflow menu -> "Share" -> Share Dialog
  -> Share Dialog: invite user, change role, revoke
  -> Dialog close -> /dashboard (unchanged)

/lists/[id] (list detail, owner)
  -> "Share" button -> Share Dialog
  -> Share Dialog actions (same as above)
  -> Dialog close -> /lists/[id]

/lists/[id] (list detail, any role)
  -> Avatar stack click -> Share Dialog (read-only for non-owner)
  -> Dialog close -> /lists/[id]

/lists/[id] (active session, collaborator gets revoked)
  -> RevocationBlockingOverlay appears immediately
  -> "Back to My Lists" -> /dashboard

/dashboard (collaborator receives share.granted event)
  -> New list card appears in "Shared with me" section + toast notification
```

---

## Authorization Matrix: UI Enforcement

The PRD-3 authorization matrix is enforced both server-side (authoritative) and in the UI (UX enforcement, not security gate):

| UI Element | Owner | Editor | Viewer | Stranger |
|------------|-------|--------|--------|----------|
| Add item bar visible | yes | yes | no | no |
| Item checkbox interactive | yes | yes | no | no |
| Item edit (pencil) icon visible | yes | yes | no | no |
| Item delete (trash) icon visible | yes | yes | no | no |
| List rename (click on name) | yes | no | no | no |
| "Share" button visible | yes | no | no | no |
| Avatar stack clickable (opens dialog) | yes | yes | yes | no |
| Share Dialog -- invite section shown | yes | no | no | no |
| Share Dialog -- role selectors on member rows | yes | no | no | no |
| Share Dialog -- remove icons on member rows | yes | no | no | no |
| "Delete list" in overflow menu | yes | no | no | no |
| "Rename" in overflow menu | yes | no | no | no |

Note: Viewer notice ("You can view but not edit this list") is shown in add-item bar area for viewers.
Stranger: entire /lists/[id] is inaccessible; 404 response (per PRD-3 security spec).

---

## Open Design Decisions (for planning-lead)

1. **User search autocomplete:** PRD-3 specifies exact email or username lookup (registered-users-only, no invite-to-stranger). BSD v1 uses a plain text input with no autocomplete dropdown. If autocomplete (e.g., type 3+ chars, see matching users) is desired, it introduces a user-enumeration risk that validation-lead must approve -- flag this explicitly.

2. **Collaborator online presence on dashboard cards:** BSD shows presence only in the list detail view (via avatar dots). Dashboard list cards do NOT show live activity indicators. If stakeholders want "3 active now" on dashboard cards, this requires per-list presence data on the dashboard load endpoint -- scope increase for engineering.

3. **share.granted notification UI:** BSD shows a toast notification when a share.granted event arrives on the dashboard. An in-app notification bell (notification list) would be more persistent but is outside v1 scope (PRD-3 Non-Goals).

4. **Revocation overlay copy:** "Your access to this list has been removed by the owner." If the owner preference is not to be identified as the revoker, the copy can be changed to "Your access to this list has been removed." -- no functional change.
