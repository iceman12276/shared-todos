# BSD-2: Lists Dashboard + Item Interactions

**Version:** 1.0
**Date:** 2026-04-19
**Status:** Draft
**Author:** ux-designer
**PRD Reference:** PRD-2: Todo Lists & Items CRUD

---

## Overview

This BSD covers the lists dashboard (all lists owned + shared), the list detail view (all items in a list), and every interaction on items: create, toggle done, inline edit, delete. It also specifies the empty states, loading states, optimistic updates, and error recovery paths. Realtime sync behavior (item events from collaborators) is detailed here as it affects the visual layer; the sharing/permission UI is in BSD-3.

---

## Design Token Reference

Inherits all tokens from BSD-1 Auth Flows. Additional tokens:

```
COLOR:
  done-overlay: rgba(0,0,0,0.35) -- strikethrough + muted text on completed items
  shared-badge-bg: #EEF2FF       -- indigo-50, badge background for shared lists
  shared-badge-text: #4338CA     -- indigo-700
  viewer-badge-bg: #F0FDF4       -- green-50
  viewer-badge-text: #15803D     -- green-700
  editor-badge-bg: #FFF7ED       -- orange-50
  editor-badge-text: #C2410C     -- orange-700
  realtime-pulse: #22C55E        -- green-500, live indicator dot

SPACING (extends base):
  list-card-padding: 20px
  item-row-height: 52px (min)
  item-row-padding: 12px 16px

MOTION:
  item-enter: height 0 -> auto + opacity 0 -> 1, 150ms ease-out
  item-exit: height auto -> 0 + opacity 1 -> 0, 120ms ease-in
  item-strike: text-decoration line-through, 200ms ease
  skeleton-pulse: opacity 0.4 <-> 1.0, 1.2s infinite ease-in-out
```

---

## Screen 1: Lists Dashboard

### Component Specification
```
COMPONENT: DashboardScreen
PURPOSE: Central hub showing all lists the user owns or has access to, enabling navigation to any list and creation of new ones.
LOCATION: /dashboard -- primary authenticated landing page
```

### Visual Specification
```
LAYOUT:
  - Full-page layout: top navigation bar (fixed, 56px) + main content area
  - Main content: max-width 960px, centered, padding 32px 24px
  - Top nav: "Shared Todos" logo left, logout button right, height 56px,
    white bg, border-bottom 1px neutral-200, position fixed

SECTIONS (top to bottom in main content):
  1. Page header: "My Lists" (heading-lg, neutral-900) left,
     "New list" button (brand-600, 36px height, radius md) right
     -- same horizontal row, align-items center
  2. Lists grid: 2 columns on desktop (>=1024px), 1 column on mobile (<768px)
     Gap: 16px between cards
  3. Shared-with-me section: same grid layout, shown only if user has shared lists
     Section sub-header: "Shared with me" (body-base/500, neutral-500, margin-bottom 12px)

EMPTY STATE (no lists at all):
  - Center of content area (vertically centered in remaining space)
  - Illustration: simple SVG clipboard icon (64px, neutral-300)
  - Heading: "No lists yet" (heading-lg, neutral-500)
  - Body: "Create your first list to get started." (body-base, neutral-400)
  - "Create a list" button (brand-600, full-width on mobile, auto on desktop)

LOADING STATE (initial page load):
  - 4 skeleton cards (2x2 grid), pulsing animation
  - Skeleton card: same dimensions as list card, neutral-100 background, rounded corners
```

### List Card Anatomy
```
COMPONENT: ListCard
PURPOSE: Represents a single list in the dashboard grid.

LAYOUT:
  - White background, radius md, shadow card, border 1px neutral-200
  - Padding: 20px
  - Min-height: 100px
  - Hover: border neutral-300, box-shadow slightly elevated (0 4px 8px rgba(0,0,0,0.08))
  - Cursor: pointer (entire card is clickable)

CONTENTS (top to bottom):
  1. Title row: list name (body-base/500, neutral-900) left;
     role badge (if shared) right
  2. Meta row: item count ("X items", body-sm, neutral-500) left;
     owner name ("by [name]", body-sm, neutral-500) right (only on shared lists)
  3. Action row (owner only): "..." overflow menu button (16px, neutral-400), top-right corner
     -- only visible on hover or focus (keyboard accessible always)

ROLE BADGE (on shared lists in the "Shared with me" section):
  - "Editor" badge: orange-50 bg, orange-700 text, 4px radius, 10px 6px padding, body-sm/500
  - "Viewer" badge: green-50 bg, green-700 text, same sizing

OWNED LIST INDICATOR (in "My Lists" section):
  - No badge -- ownership is implicit by section placement
  - If a list is owned AND shared with others: small "Shared" badge (indigo-50, indigo-700)
    at top-right instead of overflow menu position (overflow menu still accessible via "...")

REALTIME INDICATOR (when user has list open in another tab / when collaborators are active):
  Not shown on dashboard cards -- shown only on list detail view
```

### Interaction Specification

```
ELEMENT: List card (entire card surface)
TRIGGER: click
EXPECTED BEHAVIOR:
  1. Navigate to /lists/[id] (client-side routing)
  2. Show list detail screen
EDGE CASES:
  - Click on "..." overflow menu: stops propagation, does not navigate

ELEMENT: "New list" button
TRIGGER: click
EXPECTED BEHAVIOR:
  1. Open "Create list" inline modal or bottom sheet on mobile
     (see Create List Modal below)
EDGE CASES:
  - User already has 200+ lists: no hard cap in v1; button works regardless

ELEMENT: "..." overflow menu (owned lists only)
TRIGGER: click
EXPECTED BEHAVIOR:
  1. Show dropdown menu with options:
     - "Rename" (always shown for owner)
     - "Share" -> opens Share Dialog (BSD-3)
     - Divider
     - "Delete" (text: error-500)
  2. Click outside or Escape: dismiss menu
  3. "Rename": open inline rename input on the card (see Rename List below)
  4. "Delete": open delete confirmation dialog (see Delete List below)
  5. "Share": open share dialog (BSD-3)
EDGE CASES:
  - Keyboard access: overflow button focusable, Enter opens menu, arrow keys navigate items, Escape closes

ELEMENT: Dashboard (loading)
TRIGGER: Page mount / navigation arrival
EXPECTED BEHAVIOR:
  1. Show skeleton cards immediately (no blank white flash)
  2. GET /api/v1/lists (returns owned + shared lists)
  3. On success: replace skeletons with real list cards, animate in (fade 150ms)
  4. On error: replace skeletons with error state:
     "Could not load your lists. [Retry]" link
  5. On empty result: show empty state
```

### Data Flow Specification
```
DATA SOURCE: GET /api/v1/lists
RESPONSE: {
  owned: [{ id, name, item_count, share_count, updated_at }],
  shared: [{ id, name, item_count, owner_display_name, role, updated_at }]
}
TRANSFORMS:
  - Sort each section by updated_at descending
  - item_count formatted: "1 item" / "N items"
BINDING:
  - owned array -> "My Lists" section
  - shared array -> "Shared with me" section (hidden if empty)
  - Loading: skeleton cards
  - Error: error state with retry
```

### Navigation Specification
```
ENTRY POINTS: /dashboard (post-login redirect, logout redirect target)
EXIT POINTS: /lists/[id] (any list card click)
BACK BEHAVIOR: browser back from /lists/[id] returns to /dashboard
DEEP LINK: /dashboard -- authenticated users only; unauthenticated -> /login
```

### Accessibility Specification
```
KEYBOARD:
  - Tab order: New list button -> list cards in DOM order -> each card's overflow menu
  - Each list card: role="button", tabIndex=0, Enter/Space navigates to list
  - Overflow menu: role="menu", items role="menuitem", arrow keys navigate

SCREEN READER:
  - List card: aria-label="[List name], [N] items, last updated [relative time]"
  - Role badge: included in aria-label: "...shared as Editor"
  - Loading: aria-busy="true" on the lists container, aria-label="Loading your lists"
  - Empty state: aria-live="polite" announces when loading completes with 0 results

FOCUS MANAGEMENT:
  - On overflow menu open: focus first menu item
  - On menu close: return focus to "..." button
  - On list creation success: focus newly created list card
```

---

## Modal: Create List

### Component Specification
```
COMPONENT: CreateListModal
PURPOSE: Allow the user to name and create a new todo list.
LOCATION: Overlay on /dashboard, triggered by "New list" button.
```

### Visual Specification
```
LAYOUT:
  - Modal overlay: rgba(0,0,0,0.4) backdrop
  - Modal card: white, radius lg, shadow xl, width 420px on desktop, 100% - 32px on mobile
  - Vertically and horizontally centered
  - Header: "New list" (body-base/600, neutral-900) left, X close button right
  - Body: single "List name" text input, full width, height 40px
  - Footer: "Cancel" text button (neutral-700) + "Create" primary button (brand-600)
    right-aligned, gap 8px
  - Padding: 24px
```

### Interaction Specification

```
ELEMENT: List name input
TRIGGER: change
EXPECTED BEHAVIOR:
  1. Character count shown below input: "[N]/200" (body-sm, neutral-400), right-aligned
  2. If over 200 chars: character count turns error-500
  3. "Create" button disabled while input is empty or > 200 chars

ELEMENT: "Create" button
TRIGGER: click
EXPECTED BEHAVIOR:
  1. Validate: name non-empty after trim, <= 200 chars
  2. If invalid: show inline error below input
  3. If valid: disable button, spinner, POST /api/v1/lists
  4. On 201: close modal, add new list card to top of "My Lists" section with enter animation
  5. On 422: show error below input "List name is invalid."
  6. On 500 / network: show banner inside modal "Something went wrong. Please try again."
  7. On error: re-enable button
LOADING STATE: spinner in button, button disabled, input disabled
SUCCESS STATE: modal closes, new card appears in dashboard
ERROR STATE: inline error below input or modal-internal banner
EDGE CASES:
  - Enter key in input: submits form
  - Escape key: closes modal without creating
  - Name is all whitespace: trimmed to empty, treated as empty

ELEMENT: X button / "Cancel" button / backdrop click
TRIGGER: click
EXPECTED BEHAVIOR:
  1. Close modal (fade out 150ms)
  2. No list created
  3. Return focus to "New list" button
```

### Data Flow Specification
```
DATA SOURCE: POST /api/v1/lists
REQUEST: { name: string }
RESPONSE:
  201: { id, name, item_count: 0, updated_at }
  422: { error: "validation_error" }
BINDING: On 201 -> prepend to owned lists array, animate card in
```

### Accessibility Specification
```
- Modal: role="dialog", aria-modal="true", aria-labelledby=modal-title-id
- On open: trap focus inside modal, focus list name input
- On close: return focus to "New list" button
- Escape: close modal
```

---

## Modal: Rename List

### Component Specification
```
COMPONENT: RenameListModal
PURPOSE: Allow the list owner to change a list's name.
LOCATION: Triggered from overflow menu on list card or from list detail header.
```

### Visual Specification
```
LAYOUT: Same modal frame as Create List
- Header: "Rename list"
- Body: "List name" input pre-populated with current name, text selected on open
- Footer: "Cancel" + "Save" buttons
```

### Interaction Specification

```
ELEMENT: "Save" button
TRIGGER: click
EXPECTED BEHAVIOR:
  1. Validate: non-empty after trim, <= 200 chars, different from current name
  2. If same as current name: close modal (no request needed)
  3. If valid and changed: disable button, spinner, PATCH /api/v1/lists/[id]
  4. On 200: update list name in all UI locations (card title, list detail header if open)
     close modal
  5. On 403: show banner "You don't have permission to rename this list."
  6. On 422: show inline error "List name is invalid."
  7. On 500 / network: show modal-internal error banner
EDGE CASES:
  - Rename during a collaborative session: other users see list.renamed realtime event (BSD-3)
  - Concurrent rename by owner on two devices: last write wins (server timestamp)
```

---

## Modal: Delete List Confirmation

### Component Specification
```
COMPONENT: DeleteListModal
PURPOSE: Confirm before permanently deleting a list and all its items.
LOCATION: Triggered from overflow menu on list card or list detail header (owner only).
```

### Visual Specification
```
LAYOUT:
  - Modal card: same frame, width 380px
  - Header: "Delete list?" (neutral-900)
  - Body: "This will permanently delete '[list name]' and all [N] items inside it.
    This cannot be undone." (body-base, neutral-700)
    Warning icon (20px, error-500) to the left of body text
  - Footer: "Cancel" (neutral-700) left + "Delete" (error-500 background, white text) right
```

### Interaction Specification

```
ELEMENT: "Delete" confirmation button
TRIGGER: click
EXPECTED BEHAVIOR:
  1. Disable button, spinner, DELETE /api/v1/lists/[id]
  2. On 204: close modal, remove list card from dashboard with exit animation
     If currently on /lists/[id]: redirect to /dashboard
  3. On 403: show banner "You don't have permission to delete this list."
  4. On 500 / network: show error banner, re-enable button
LOADING STATE: spinner in delete button
SUCCESS STATE: card removed, modal closed
EDGE CASES:
  - Collaborators viewing the list when deleted: they receive collaborator.access_revoked event,
    redirected to dashboard (BSD-3 covers this)
  - Delete fails: list remains, error shown

ELEMENT: "Cancel" / X / backdrop
TRIGGER: click
EXPECTED BEHAVIOR: close modal, no delete, return focus to trigger element
```

---

## Screen 2: List Detail View

### Component Specification
```
COMPONENT: ListDetailScreen
PURPOSE: Show all items in a list and allow interactions based on user role.
LOCATION: /lists/[id]
```

### Visual Specification
```
LAYOUT:
  - Top nav (same as dashboard, fixed 56px)
  - List header section: below nav, padding 24px 24px 0
    - Back link: "<- My Lists" (body-sm, brand-600), left
    - List name: heading-lg, neutral-900, editable for owner (click to rename inline)
    - Owner badge: "Your list" (subtle, body-sm, neutral-400) OR shared badge
    - Sharing button (owner only): "Share" button (outlined, 32px, right of name row)
    - Collaborator avatars (if list is shared): small avatar stack, max 3 shown + "+N more"
    - Realtime presence indicator: green dot + "N active" when collaborators are viewing
  - "Add item" bar: sticky below list header, above items
    - Text input: "Add an item..." placeholder, 100% width - padding, height 44px
    - "Add" button: 36px, brand-600, right side
    - Shown only for owner and editor roles
    - Viewer role: bar replaced with read-only notice "You can view but not edit this list"
  - Items list: scrollable, padding 0 24px 24px

ITEMS LIST HEADER:
  - "X items" count left, "X completed" right (body-sm, neutral-500)
  - Both update in real time as items change

LOADING STATE (initial):
  - 3-5 skeleton item rows, pulsing

EMPTY STATE (no items):
  - Illustration: checklist SVG (48px, neutral-300), center-aligned
  - Text: "No items yet." (body-base, neutral-400)
  - Sub-text (owner/editor only): "Add your first item above."
```

### Item Row Anatomy
```
COMPONENT: ItemRow
PURPOSE: Display a single todo item with its state and inline editing affordances.

DEFAULT STATE:
  - Height: min 52px (expands for long titles or notes)
  - Padding: 12px 16px
  - Background: white
  - Border-bottom: 1px neutral-100 (no border on last item)
  - Hover: background neutral-50

LAYOUT (flex row, align-items flex-start):
  1. Checkbox (24x24px) -- left, 8px right margin
     - Uncompleted: circular outline, neutral-300, 1.5px stroke
     - Completed: filled brand-600 circle, white checkmark SVG
  2. Content area (flex-grow):
     - Title: body-base, neutral-900 when undone; neutral-400 + line-through when done
     - Notes (if present): body-sm, neutral-500, margin-top 2px, max 2 lines then truncated
       "Show more" link if truncated
  3. Action buttons (right, visible on row hover or focus-within):
     - Edit (pencil icon, 16px, neutral-400)
     - Delete (trash icon, 16px, neutral-400, hover error-500)
     - Shown only for owner and editor roles

COMPLETED ITEM STYLING:
  - Title: neutral-400, line-through (text-decoration applied with 200ms ease transition)
  - Checkbox: brand-600 filled
  - Row background: slightly lighter (neutral-50 tint)
```

### Interaction Specification

```
ELEMENT: Checkbox
TRIGGER: click
EXPECTED BEHAVIOR:
  1. Optimistically toggle done state in UI immediately (no wait for server)
  2. PATCH /api/v1/lists/[id]/items/[item_id] { done: !current }
  3. On 200: confirm (state already reflects new value)
  4. On 403: revert optimistic update, show toast "You don't have permission to update items."
  5. On 500: revert optimistic update, show toast "Failed to save. Please try again."
LOADING STATE: checkbox shows loading spinner (tiny, 12px) while request in-flight
SUCCESS STATE: done state reflected, title styled
ERROR STATE: rollback to previous state, toast notification
EDGE CASES:
  - Rapid toggle: debounce at 300ms (last click wins); pending requests cancel previous
  - Network offline: queue update, show "Offline - changes will sync when reconnected"
  - Viewer role: click does nothing; checkbox has no pointer cursor; aria-disabled="true"

ELEMENT: Inline title edit
TRIGGER: click on edit (pencil) button, OR double-click on title text
EXPECTED BEHAVIOR:
  1. Title text replaced with an inline text input, pre-filled with current title
  2. Input auto-focuses, text selected
  3. Notes textarea appears below if notes exist (or if user starts typing in notes area)
  4. "Save" and "Cancel" buttons appear below the input
  5. "Save" click or Enter key: validate (non-empty, <= 500 chars), then PATCH
  6. On 200: replace input with updated title, animate exit of edit controls
  7. On 403: show toast "You don't have permission to edit items."
  8. On 500 / network: show error below input, keep editing
  9. "Cancel" or Escape: discard changes, restore original title
LOADING STATE: "Save" button shows spinner, input disabled
SUCCESS STATE: editing mode exits, title updated in place
ERROR STATE: error below input, keep editing
EDGE CASES:
  - Viewer clicks pencil: pencil icon not shown for viewers (guard in render)
  - Empty title on save: show inline error "Title cannot be empty"
  - Realtime conflict: another user edits the same item; on 200 from our PATCH, use server's
    response as source of truth; realtime event from the other user may arrive too --
    last-server-response wins (reconcile on item.updated event)
  - Long title: textarea expands vertically
  - Click elsewhere during edit: ask to save (show "You have unsaved changes" prompt) if dirty,
    or discard if unchanged

ELEMENT: Notes "Show more" toggle
TRIGGER: click
EXPECTED BEHAVIOR:
  1. Expand notes to full text (no character limit in expanded view)
  2. Toggle label changes to "Show less"
  3. Collapsing re-truncates to 2 lines

ELEMENT: Delete (trash) button
TRIGGER: click
EXPECTED BEHAVIOR:
  1. Show inline confirmation tooltip/popover on the item row:
     "Delete this item? [Cancel] [Delete]"
     (no full-screen modal -- inline to keep the flow lightweight)
  2. User confirms Delete: DELETE /api/v1/lists/[id]/items/[item_id]
  3. On 204: remove item with exit animation (height collapse 120ms)
  4. On 403: show toast "You don't have permission to delete items."
  5. On 500: show toast, item remains
  6. User cancels: dismiss popover, item unchanged
LOADING STATE: item row shows a subtle loading overlay (opacity 0.5) during DELETE in-flight
SUCCESS STATE: item removed with animation
EDGE CASES:
  - Viewer: trash icon not shown
  - Item already deleted by another user (404 from server): remove from UI silently (no error)
  - Escape key: dismisses confirmation popover

ELEMENT: "Add item" input + "Add" button
TRIGGER: "Add" button click OR Enter in input
EXPECTED BEHAVIOR:
  1. Validate: non-empty after trim, <= 500 chars
  2. If invalid: shake input + show inline error "Item title cannot be empty"
  3. If valid:
     a. Optimistically add item to bottom of list with enter animation
     b. Clear input, refocus input (ready for next item)
     c. POST /api/v1/lists/[id]/items { title: string }
     d. On 201: replace optimistic item with server response (update id, created_at)
     e. On 403: remove optimistic item, show toast "You don't have permission to add items."
     f. On 422: remove optimistic item, show inline error below input
     g. On 500: remove optimistic item, show toast, restore input text
LOADING STATE: optimistic item shows as slightly faded (opacity 0.7) until server confirms
SUCCESS STATE: item persisted, input cleared, focus back on input
EDGE CASES:
  - Paste long text > 500 chars: input accepts it but on submit validation fires
  - Enter key with empty input: no-op (not even a shake)
  - Rapid successive adds: each queued; optimistic items appear in order

ELEMENT: List name heading (owner only)
TRIGGER: click on name or edit icon next to name
EXPECTED BEHAVIOR:
  1. Open Rename List modal (same as from overflow menu on dashboard)

ELEMENT: "Share" button (owner only)
TRIGGER: click
EXPECTED BEHAVIOR:
  1. Open Share Dialog (BSD-3)
```

### Realtime Item Updates

```
EVENT: item.created (from WebSocket/SSE channel)
SOURCE: Another user creates an item
BEHAVIOR:
  1. Add item to bottom of list with enter animation (same as optimistic add)
  2. Update item count in header
  3. If the creating user is us (echo of our own optimistic update): deduplicate
     (compare item id; if optimistic placeholder exists, replace it)

EVENT: item.updated (from WebSocket/SSE channel)
SOURCE: Another user updates an item
BEHAVIOR:
  1. Find item in list by id
  2. If item is not currently being edited by local user: update in place (no animation, just data update)
  3. If item IS being edited by local user: show subtle indicator "This item was updated by [user]"
     Do NOT overwrite local user's in-progress edits; reconcile on save

EVENT: item.deleted (from WebSocket/SSE channel)
SOURCE: Another user deletes an item
BEHAVIOR:
  1. Find item by id, remove with exit animation
  2. If local user has that item's edit mode open: close edit mode, remove item, show toast
     "This item was deleted by [user]"

EVENT: list.renamed (from WebSocket/SSE channel)
BEHAVIOR:
  1. Update list name heading in real time
  2. Update page title (document.title)
  3. Update "My Lists" dashboard card name if dashboard is open in another tab

EVENT: collaborator.access_revoked (targeting this user)
BEHAVIOR (covered in full detail in BSD-3):
  1. Redirect to /dashboard
  2. Toast: "Your access to this list has been removed."
```

### Data Flow Specification
```
INITIAL LOAD:
  GET /api/v1/lists/[id] -> { id, name, role, owner, collaborators, item_count }
  GET /api/v1/lists/[id]/items -> [{ id, title, notes, done, created_at, updated_at }]
  Both requests in parallel

ITEM ORDER: created_at ascending (oldest first)

REALTIME SUBSCRIPTION:
  On component mount: subscribe to list channel [id]
  On component unmount: unsubscribe
  On reconnect: re-fetch full items list before re-subscribing (missed events not replayed)

TRANSFORMS:
  - items sorted by created_at asc client-side (server returns in insert order)
  - "X items" count = total items; "X completed" = items where done === true
```

### Navigation Specification
```
ENTRY POINTS: List card click on /dashboard -> /lists/[id]
EXIT POINTS:
  - Back link -> /dashboard
  - Forced redirect (access revoked) -> /dashboard
BACK BEHAVIOR: browser back returns to /dashboard scroll position
DEEP LINK: /lists/[id] -- authenticated + access check; stranger/no-access -> /dashboard with toast
  "List not found." (404 response used per security spec)
```

### Accessibility Specification
```
KEYBOARD:
  - Tab order: back link -> list name -> Share button -> Add item input -> Add button -> item rows
  - Each item row: tabIndex=0, role="listitem"
  - Checkbox: role="checkbox", aria-checked, Enter/Space toggles
  - Edit button: aria-label="Edit item [title]"
  - Delete button: aria-label="Delete item [title]"
  - Inline edit confirmation: role="dialog", trap focus

SCREEN READER:
  - items list: role="list", aria-label="Items in [list name]"
  - Item count header: aria-live="polite" (updates as items added/removed)
  - Realtime events: aria-live="polite" on a visually-hidden announcer element
    "Item [title] was added by [user]" / "Item [title] was updated by [user]"

FOCUS MANAGEMENT:
  - On Add item success: focus stays on add-item input
  - On edit mode open: focus title input
  - On edit mode close (save/cancel): return focus to edit button
  - On item delete confirmation: focus confirm Delete button
  - On item delete confirmed: focus next item row, or add-item input if last item
```

---

## Component: Empty State (Reusable)

```
COMPONENT: EmptyState
PURPOSE: Consistent empty state pattern across dashboard and list detail.

VARIANTS:
  no-lists: clipboard SVG, "No lists yet", "Create your first list to get started."
  no-items: checklist SVG, "No items yet", "Add your first item above." (owner/editor)
             checklist SVG, "No items in this list." (viewer)
  loading-error: warning SVG, "Could not load.", "[Retry]" link
```

---

## Component: Toast Notifications

```
COMPONENT: Toast
PURPOSE: Surface transient feedback for operations that don't block the UI (permission errors, realtime event notices, offline status).
LOCATION: Bottom-right corner of viewport (bottom-center on mobile), stacked, max 3 visible.

VISUAL:
  - Pill shape: white bg, shadow card, radius lg, padding 12px 16px
  - Icon left (16px): info (blue), success (green), error (red), warning (orange)
  - Message text: body-sm, neutral-700
  - Optional action link: body-sm, brand-600 (e.g., "Retry")
  - Dismiss X: 12px, neutral-400
  - Auto-dismiss: 4000ms (error: 6000ms, no auto-dismiss)
  - Enter: slide up from bottom 200ms ease-out
  - Exit: fade out 150ms

STACKING:
  - Max 3 toasts visible at once; new toasts push oldest out if limit reached
  - Most recent at bottom of stack (closest to screen edge)
```

---

## Open Design Decisions (for planning-lead)

1. **Completed items grouping:** Should completed items be visually grouped at the bottom of the list (sorted by done state, then created_at), or remain in creation order with done items in-place? BSD currently specifies creation order (in-place). A "move to bottom on complete" behavior is more traditional but requires a sorting decision in PRD-2 first.

2. **Notes display on item rows:** BSD shows notes truncated to 2 lines with "Show more." If notes are commonly used, a dedicated expandable notes panel on click may be better UX. Keeping it simple (2-line truncation) for v1.

3. **Inline edit vs. dedicated detail panel:** BSD uses inline editing on item rows. A slide-in panel (like Todoist) provides more space for notes. Inline is simpler and consistent with the "desktop-first, light CRUD" scope.

4. **Optimistic updates and offline mode:** BSD specifies optimistic updates for checkbox toggles and item additions. Full offline queueing is noted as a stretch behavior. If engineering cannot implement the offline queue in v1, the checkbox behavior degrades to: wait for server response, show loading state, no optimistic toggle.
