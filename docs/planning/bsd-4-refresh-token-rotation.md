# BSD-4: Refresh-Token Rotation UX

**Version:** 1.0
**Date:** 2026-04-21
**Status:** Draft
**Author:** ux-designer
**PRD Reference:** PRD-4: Refresh-Token Rotation

---

## Overview

Refresh-token rotation is a security feature that is **intentionally invisible on the happy path**. The user never sees a token, never types one, and never knowingly participates in rotation. The client handles `POST /api/v1/auth/refresh` silently in the background. This BSD's scope is therefore not a new screen — it is:

1. The **silent-refresh in-flight window** (what the user experiences during the ~100ms–1.5s background call)
2. The **forced-logout path** triggered when `/refresh` returns any 401 (no cookie / expired / revoked / reused)
3. The **in-flight unsaved edits** behavior at the forced-logout moment
4. The **cross-tab consistency** requirement when forced logout fires in one tab
5. The **session-expired banner** — a new state on the existing login screen (BSD-1)
6. A confirmation that **explicit logout** (BSD-1 LogoutButton) is unchanged

No new screens are introduced. All new states are expressed on existing screens defined in BSD-1 and BSD-2.

---

## Design Token Reference

Inherits all tokens from BSD-1, BSD-2, and BSD-3. Additional tokens for this BSD:

```
COLOR:
  info-600: #2563EB    -- blue-600, used for the "Reconnecting..." toast icon + border
  info-50:  #EFF6FF    -- blue-50, toast background
  blue-200: #BFDBFE    -- banner border color

MOTION:
  toast-enter: translateY(100%) -> translateY(0) + opacity 0 -> 1, 200ms ease-out
  toast-exit:  opacity 1 -> 0, 150ms ease-in
  banner-enter: translateY(-8px) + opacity 0 -> translateY(0) + opacity 1, 150ms ease-out
```

---

## Flow 1: Silent Refresh (Happy Path)

### Component Specification
```
COMPONENT: SilentRefreshInterceptor
PURPOSE: Transparently renew an expired or missing session by calling the refresh endpoint,
         then retrying the original failed request — all without user-visible interruption.
LOCATION: Global HTTP client layer (wraps all authenticated API calls). Runs before any
          component error handler sees the 401. Sits alongside the existing
          SessionExpiryInterceptor from BSD-1, which it supersedes for the first retry attempt.
```

### Interaction Specification

```
TRIGGER: Any authenticated API request returns 401
EXPECTED BEHAVIOR:
  1. HTTP client intercepts the 401 before the calling component sees it.
  2. An in-flight flag is set to prevent parallel retry storms
     (subsequent 401s that arrive while a refresh is already in progress queue
     behind the in-flight promise — they do not each spawn a new /refresh call).
  3. POST /api/v1/auth/refresh is called (no request body; refresh token is in
     the httpOnly cookie automatically sent by the browser).
  4a. If /refresh returns 200 (new session + rotation cookies set):
       - Re-issue the original failed request with the new session cookie.
       - If the retry succeeds: return the response normally. User sees nothing.
       - If the retry also 401s (race: session already revoked between refresh and retry):
         treat as FAILED REFRESH (see Flow 2).
       - Release the in-flight flag; drain the queue of pending requests.
  4b. If /refresh returns any 401: proceed to Flow 2 (Forced Logout).

LATENCY BUDGET:
  0ms – 1,499ms:  No visible indicator. The original in-flight request is paused;
                  the UI appears momentarily unresponsive but does not change state.
  ≥ 1,500ms:      Show the "Reconnecting..." toast (see ReconnectingToast component below).
                  Toast disappears immediately when the retry resolves (success or failure).
  Upper bound:    /refresh call times out at 10,000ms (engineering-configurable).
                  Timeout is treated as a failed refresh → Flow 2.

LOADING STATE: None visible for <1,500ms. ReconnectingToast for ≥1,500ms.
SUCCESS STATE: Original request completes normally; UI state is preserved. No flash, no
               redirect, no spinner on the current screen.
ERROR STATE:   Any 401 from /refresh → Flow 2 (Forced Logout).
```

### Edge Cases
```
- PARALLEL 401s: Multiple in-flight requests all 401 simultaneously. Only one
  /refresh call is made (in-flight flag). Remaining requests queue and replay after
  the single /refresh resolves.

- CROSS-TAB DURING ROTATION: If Tab A is mid-rotation and Tab B also sends a
  request that 401s, Tab B independently starts its own /refresh. The server handles
  concurrent refresh requests per the token family invariant (only one active token
  at a time). If Tab B presents a token that Tab A just rotated away, Tab B's
  /refresh returns 401 (reuse detected) → Tab B follows Flow 2. Tab A, having
  received a valid 200 already, continues normally. See also Flow 4.

- NETWORK OFFLINE: /refresh call fails with a network error (not 401). Do NOT
  follow Flow 2. Show a generic network-error toast (existing pattern from BSD-2)
  and re-enable the original failing action. The user's session is intact — the
  failure was transport, not auth.

- /REFRESH ITSELF 401s DURING ANOTHER /REFRESH CALL: Should not occur in normal
  operation (the refresh endpoint requires only the refresh cookie, not a session
  cookie). If it does, treat as failed refresh → Flow 2.
```

---

## Component: ReconnectingToast

### Component Specification
```
COMPONENT: ReconnectingToast
PURPOSE: Non-blocking indicator that the client is re-establishing the session in the
         background, shown only when the refresh round-trip exceeds 1,500ms.
LOCATION: Bottom-center of the viewport, above any persistent navigation. Fixed position,
          z-index above page content, below modal overlays.
```

### Visual Specification
```
LAYOUT:
  - Fixed, bottom-center: bottom 24px, horizontally centered
  - Width: auto (content), max-width 320px
  - Padding: 12px 16px
  - Background: info-50 (#EFF6FF)
  - Border: 1px info-600 (#2563EB), radius md (8px)
  - Shadow: card shadow (0 1px 3px rgba(0,0,0,0.1))
  - Flex row: spinner (14px, info-600) + gap 8px + message text

TYPOGRAPHY:
  - "Reconnecting..." — body-sm (12px/400), neutral-700

ANIMATION:
  - Appear: toast-enter (translateY up from bottom, 200ms ease-out)
  - Dismiss: toast-exit (fade-out, 150ms ease-in)

RESPONSIVE:
  DESKTOP (>=768px): bottom-center as specified above
  MOBILE (<768px):   bottom-center, width: calc(100% - 32px), max-width 320px
                     bottom: 16px (reduced to avoid overlap with mobile browser chrome)
```

### Interaction Specification
```
TRIGGER: SilentRefreshInterceptor has been waiting ≥1,500ms for /refresh to resolve
EXPECTED BEHAVIOR:
  1. Toast appears at bottom-center with spinner and "Reconnecting..." label.
  2. Toast remains until /refresh resolves (success or failure).
     - On 200 success + retry success: toast immediately dismisses (toast-exit).
     - On 401 failure: toast dismisses as Flow 2 redirect begins
       (user will see the login screen with session-expired banner instead).
  3. Toast is NOT dismissible by user click (it will resolve on its own within the
     timeout window).
LOADING STATE: n/a (the toast IS the loading state)
SUCCESS STATE: toast dismisses; original request completes; page continues normally
ERROR STATE: toast dismisses; redirect to /login (Flow 2) begins
EDGE CASES:
  - User clicks something during the toast: the click is queued or no-ops depending
    on whether the action requires an API call. This is consistent with the existing
    "requests queue behind in-flight flag" behavior.
  - Toast appears and /refresh succeeds at 1,501ms: toast briefly appears then
    immediately dismisses. This flash is acceptable; the 1,500ms threshold is a
    practical UX heuristic, not a hard commitment.
```

### Accessibility Specification
```
SCREEN READER:
  - role="status", aria-live="polite"
  - aria-label="Reconnecting to session, please wait"
  - Announced once on appear; dismissal not announced
    (outcome is either normal page state or the login screen in Flow 2)

FOCUS: Does not steal focus
MOTION: Respects prefers-reduced-motion — skip translateY, use opacity-only transition
```

---

## Flow 2: Forced Logout (Any 401 from /refresh)

### Component Specification
```
COMPONENT: ForcedLogoutHandler
PURPOSE: When the refresh endpoint cannot renew the session for any reason, terminate
         the client auth state, clear any pending optimistic edits, and redirect to
         the login screen with a one-time session-expired banner.
LOCATION: Global HTTP client layer, triggered by SilentRefreshInterceptor after a
          failed /refresh call.
```

### Interaction Specification

```
TRIGGER: POST /api/v1/auth/refresh returns any 401
         (covers all 4 failure modes: no cookie, expired, revoked, reused)

NOTE (OQ-4a): All 4 failure modes produce an identical user-facing response.
The user cannot distinguish between them. If OQ-4a resolves to allow a distinct
"terminated for security reasons" message, only the banner text in the
SessionExpiredBanner component changes — everything else in this flow is unchanged.

EXPECTED BEHAVIOR:
  1. Cancel all queued pending requests (requests waiting behind the in-flight flag).
     Return a synthetic "session ended" error to their callers so components can
     clean up local state (collapse open modals, roll back optimistic edits —
     see Flow 3 for in-flight edit handling).
  2. If ReconnectingToast is showing, dismiss it immediately (toast-exit).
  3. Clear client-side auth state (user identity, cached session info).
     Do NOT clear sessionStorage or localStorage for non-auth data.
  4. Write "session_expired" to sessionStorage key "post_login_redirect_reason".
  5. Store the current URL path in sessionStorage key "post_login_redirect" if it is
     a valid post-login destination (not /login, /register, /forgot-password,
     /reset-password, or / — mirrors the BSD-1 SessionExpiryInterceptor rule).
  6. Redirect to /login.
  7. /login reads sessionStorage key "post_login_redirect_reason" == "session_expired"
     and renders the SessionExpiredBanner (see component below).

LOADING STATE: Steps 1–6 are synchronous (<1ms). No spinner between /refresh failing
               and the redirect to /login. The redirect is immediate.
SUCCESS STATE: /login loads with SessionExpiredBanner; user logs in; redirected to
               stored URL or /dashboard.
ERROR STATE:   If redirect itself fails (abnormal), reload the page. The server session
               is gone; a page reload falls through to /login via the auth guard.
```

### Edge Cases
```
- DOUBLE TRIGGER (two tabs): If Tab A and Tab B both detect a failed /refresh
  simultaneously, each independently follows this flow. Both land on /login.
  This is correct and expected — see Flow 4.

- REDIRECT TO AUTH PATHS: If the stored URL is /login, /register, /forgot-password,
  /reset-password, or / (root), discard it. Post-login redirect defaults to /dashboard.
  (Matches BSD-1 SessionExpiryInterceptor rule.)

- GOOGLE OAUTH FLOW INTERRUPTED: If forced logout fires while the OAuth callback
  is in progress, the callback will 401 on its session creation call. The
  /register?error=oauth_cancelled path from BSD-1 handles this naturally. No
  special case needed in ForcedLogoutHandler.
```

---

## Component: SessionExpiredBanner (New State on Existing Login Screen)

### Component Specification
```
COMPONENT: SessionExpiredBanner
PURPOSE: Inform the user that their previous session ended and they must log in again.
         Displayed once at the top of the /login card. Dismissed by successful login
         or after 10 seconds, whichever comes first.
LOCATION: /login card — in the same slot as AuthErrorBanner from BSD-1 (above the
          Google OAuth button, below the "Welcome back" heading and sub-header). Uses a
          distinct info/notice visual treatment, not the error treatment.
TRIGGER: sessionStorage key "post_login_redirect_reason" == "session_expired" on /login load.
```

### Visual Specification
```
LAYOUT:
  - Full card width, margin-bottom 16px
  - Padding: 12px 16px
  - Background: info-50 (#EFF6FF)
  - Border: 1px solid blue-200 (#BFDBFE), radius md (8px)
  - Flex row: info icon (16px, info-600 #2563EB) + gap 8px + message text
  - Optional: thin progress bar along bottom edge of banner (see below)

TYPOGRAPHY:
  - "Session expired. Please log in again." — body-sm (12px/400), neutral-700
  [OQ-4a: if OQ-4a resolves to a distinct security-termination message, only this
   text changes. All layout, color, and positioning remain identical.]

AUTO-DISMISS PROGRESS BAR (optional implementation):
  - Thin strip (3px) along the bottom inner edge of the banner
  - 10s linear shrink from 100% to 0% width
  - Color: info-600 at 40% opacity
  - If engineering finds this complex to implement: omit the bar; auto-dismiss at
    10s with no visual countdown. Product does not need to weigh in — engineering call.

ANIMATION:
  - Appear: banner-enter (slide down + fade in, 150ms ease-out)
  - Dismiss: fade-out 150ms ease-in, triggered by successful login OR 10s timer

RESPONSIVE:
  DESKTOP (>=1024px): full card width (within 400px card)
  TABLET (768-1023px): full card width (within 100% - 48px card)
  MOBILE (<768px):    full card width (within 100% - 32px card), padding 10px 14px
```

### Interaction Specification
```
ELEMENT: SessionExpiredBanner
TRIGGER: /login mounts; sessionStorage "post_login_redirect_reason" == "session_expired"
EXPECTED BEHAVIOR:
  1. On /login mount: read sessionStorage "post_login_redirect_reason".
  2. If value == "session_expired": render banner immediately (with the card,
     not after a delay).
  3. Clear sessionStorage "post_login_redirect_reason" immediately after reading
     (so a manual /login page refresh does not re-show the banner).
     Retain "post_login_redirect" URL key — still needed for post-login redirect.
  4. Start 10-second auto-dismiss timer.
  5. On successful login: dismiss banner (fade-out) before redirect fires.
  6. On 10s timeout: dismiss banner (fade-out). No other side effect.
  7. No manual dismiss button (X). The 10s auto-dismiss is sufficient; a close
     target adds noise to a screen the user is about to interact with anyway.

LOADING STATE: n/a (banner is static)
SUCCESS STATE: Banner dismissed; user redirected to stored URL or /dashboard
ERROR STATE:   If login fails, the AuthErrorBanner from BSD-1 renders in the same slot.
               SessionExpiredBanner remains alongside it (they stack vertically, margin-
               bottom 8px between them) until the 10s timer expires.
               If both are showing: SessionExpiredBanner above, AuthErrorBanner below.
EDGE CASES:
  - User opens /login directly (no sessionStorage key): no banner shown. Expected.
  - User bookmarks /login and returns later: no banner. Expected — the banner requires
    the sessionStorage state written by ForcedLogoutHandler.
  - Login fails during banner's 10s window: both banners coexist (see ERROR STATE above).
  - SessionStorage unavailable (private browsing restriction): gracefully omit banner.
    The user still lands on /login and can log in normally. No crash.
```

### Data Flow Specification
```
DATA SOURCE: sessionStorage key "post_login_redirect_reason" (written by ForcedLogoutHandler)
REQUEST: none (synchronous client-side read on mount)
TRANSFORMS: Read once → clear immediately → render banner if value matched
BINDING: value == "session_expired" → render SessionExpiredBanner; otherwise → nothing
```

### Navigation Specification
```
ENTRY POINTS: /login, arrived at via ForcedLogoutHandler redirect
EXIT POINTS: stored "post_login_redirect" URL, or /dashboard (on successful login)
BACK BEHAVIOR: Browser back from /login after forced logout returns to the previous
               page, which will 401 again and re-redirect. Acceptable in v1 — there
               is no auth state to restore. The user must log in.
DEEP LINK: /login is the natural URL. Banner requires sessionStorage written by
           ForcedLogoutHandler — cannot be triggered by URL param alone.
```

### Accessibility Specification
```
KEYBOARD:
  No interactive elements in banner. Tab order unchanged from BSD-1 login:
  Google button → Email → Password → Forgot password → Sign in → Sign up link.

SCREEN READER:
  - role="status", aria-live="polite", aria-atomic="true"
  - Announced once when banner appears; auto-dismiss is not announced
  - aria-label on banner region: "Session status"

FOCUS MANAGEMENT:
  /login with banner: focus goes to email input (unchanged from BSD-1).
  Do NOT shift focus to the banner — the user's goal is to log in, not read the banner.
  Screen readers receive the announcement via aria-live without focus theft.

MOTION:
  Banner transitions MUST respect prefers-reduced-motion:
  - Under reduced-motion: skip translateY; use opacity-only, or instant show/hide.
  - Auto-dismiss progress bar: hidden entirely under reduced-motion (timer still runs).
```

---

## Flow 3: In-Flight Unsaved Edits at Forced-Logout Moment

### Specification
```
CONTEXT: The user is actively editing a todo item text, or has typed into a form
         field, when ForcedLogoutHandler fires. The pending API request for that
         edit is either queued behind the refresh in-flight flag (about to be
         cancelled) or has already returned 401 and triggered the refresh cycle
         that subsequently also 401d.
```

### Interaction Specification
```
TRIGGER: ForcedLogoutHandler step 1 — cancel queued requests with synthetic error
EXPECTED BEHAVIOR:
  1. Components that had pending optimistic updates receive the synthetic
     "session ended" error via their error callback.
  2. Optimistic state is ROLLED BACK per the existing BSD-2 optimistic-rollback
     pattern (item/field returns to its last server-confirmed state).
  3. Any text typed into an input but not yet submitted is LOST. No recovery
     mechanism exists for unsaved field text in v1.
  4. The redirect to /login proceeds (ForcedLogoutHandler step 6).
  5. The SessionExpiredBanner on /login ("Session expired. Please log in again.")
     is the only user-visible acknowledgment of the interruption.
     No separate "you had unsaved edits" message appears on the login screen.

RATIONALE FOR NO DRAFT RECOVERY:
  Surfacing draft text recovery on /login would require writing potentially
  sensitive todo content to sessionStorage, plus per-component save-draft logic.
  PRD-4 does not scope this. v1 accepts edit loss on forced logout.

EDGE CASE / OPEN QUESTION FOR PRODUCT:
  Forced logout causing lost user edits is a data-loss event, albeit rare.
  If product considers this unacceptable, one option is writing in-progress
  field text to sessionStorage before redirect and restoring it post-login.
  This requires explicit product-manager sign-off and engineering scoping —
  it is NOT in PRD-4 scope. Flag: needs product-manager confirmation on whether
  edit draft recovery is in scope for any future version, so engineering can
  plan the ForcedLogoutHandler step ordering accordingly.
```

---

## Flow 4: Cross-Tab Consistency

### Specification
```
CONTEXT: Two or more browser tabs are open. Forced logout fires in Tab A (any 401
         from /refresh). Tab B is in some authenticated state.
```

### Recommended Approach: Each Tab Handles Its Own 401
```
RECOMMENDATION: No proactive cross-tab signaling (no BroadcastChannel, no
storage event listeners for auth state). Each tab handles its own API 401
independently via its own SilentRefreshInterceptor → ForcedLogoutHandler cycle.

RATIONALE:
  - Server-side family revocation means Tab B's next API call will 401. Tab B
    calls /refresh, gets 401 (family revoked), and follows Flow 2. End state:
    both tabs land on /login. No extra client machinery needed.
  - Tab B may remain in an "authenticated-looking" state for a brief window
    (between Tab A's forced logout and Tab B's next API call). Data visible
    during that window is still protected server-side.
  - BroadcastChannel adds complexity and a new API surface requiring test
    coverage. The simpler path achieves the correct end state.

OPEN QUESTION FOR ENGINEERING:
  If engineering determines that the stale-tab window is unacceptable given
  PRD-5's realtime WebSocket requirements (the WS connection may itself
  error-out on auth revocation, closing Tab B's connection and triggering
  a visible disconnect state), BroadcastChannel sync can be added as a
  targeted enhancement. Defer this decision to engineering-lead after
  PRD-5 WS architecture is defined.

USER EXPERIENCE:
  Tab A: redirect to /login with SessionExpiredBanner immediately.
  Tab B: continues to display its current (now-stale) state. On the user's
         next action in Tab B that triggers an API call, Tab B 401s, calls
         /refresh (also 401), follows Flow 2 → /login with SessionExpiredBanner.
         Timeline: up to several seconds of stale display, then redirect.
  Tab B idle (no API calls): remains in stale-authenticated state until the
         user takes an action or reloads the page. Acceptable in v1.
```

---

## Flow 5: Explicit Logout (Integration Note)

### Integration Note
```
Explicit logout via BSD-1 LogoutButton is UNCHANGED from a user-experience
perspective:
  - User clicks "Sign out"
  - Brief spinner shown (max 500ms)
  - Redirect to /login
  - No SessionExpiredBanner is shown (the banner is reserved for involuntary
    session termination — distinguishing voluntary logout from forced logout
    is intentional UX: users who just logged out should not see an "expired"
    message)

PR-4 adds server-side family revocation to POST /api/v1/auth/logout under
the hood. The client-side flow, visual states, timing, and post-logout
redirect are identical to BSD-1.

ENGINEERING NOTE: Confirm that the added family-revocation DB write in the
logout handler does not materially extend the server response time beyond
the 500ms client timeout specified in BSD-1. If it does, the timeout is the
fallback — the user is redirected regardless — but the session/family
revocation must still complete server-side.
```

---

## Flow 6: In-Flight Loading State During /refresh (Summary)

### Specification
```
CONTEXT: While SilentRefreshInterceptor awaits the /refresh response, the
         original API request is paused and the page is partially loaded.

LATENCY TIERS:

  Tier 1 — 0ms to 1,499ms:
    No visible change. UI appears momentarily unresponsive. Users on typical
    broadband will not perceive this window. No spinner, no overlay.

  Tier 2 — ≥1,500ms:
    ReconnectingToast appears at bottom-center (see Component above).
    Non-blocking. Does not prevent user interaction with the current page.
    Signals "working on reconnecting," not "something went wrong."

  Tier 3 — ≥10,000ms (timeout):
    /refresh abandoned. Treat as failed refresh → Flow 2 (Forced Logout).
    ReconnectingToast dismisses. Redirect to /login with SessionExpiredBanner.

DESIGN RATIONALE — no full-page loading overlay:
  A full-page overlay would signal a catastrophic problem and create visual
  churn on the happy path (which succeeds the vast majority of the time).
  The tiered approach keeps the common case (<1.5s) completely invisible
  while still communicating in the slow and failure cases.
```

---

## State Diagram: Silent Refresh + Forced Logout Fork

```
Authenticated API request fires
         |
         v
   Response 200? ──YES──> Normal response to component (done)
         |
        NO (401)
         |
         v
   In-flight refresh already running?
        YES ──> Queue request behind in-flight promise ──┐
         |                                               │
        NO                                              │
         |                                              │
         v                                              │
   Set in-flight flag                                   │
   POST /api/v1/auth/refresh                            │
         |                                              │
         |  (if still waiting at 1,500ms               │
         |   → show ReconnectingToast)                  │
         |                                              │
    /refresh 200? ──YES──> Dismiss toast if showing    │
         |                  Retry original request(s) <─┘
         |                  Release flag, drain queue
        NO (401)             |
         |              Retry 200? ──YES──> Normal response (done)
         |                   |
         |                  NO (401) ──> FORCED LOGOUT (below)
         |
    FORCED LOGOUT:
      Cancel queued requests (synthetic "session ended" error to callers)
      Roll back optimistic edits (BSD-2 pattern)
      Dismiss ReconnectingToast if showing
      Clear client auth state
      Write "session_expired" → sessionStorage["post_login_redirect_reason"]
      Write current URL → sessionStorage["post_login_redirect"] (if valid)
      Redirect to /login
         |
         v
    /login loads
      Reads + clears sessionStorage["post_login_redirect_reason"]
      Renders SessionExpiredBanner
      Focus: email input (unchanged from BSD-1)
      Banner auto-dismisses in 10s or on successful login
         |
         v
    User logs in → redirect to stored URL or /dashboard
```

---

## ASCII Wireframes

### Login Screen — SessionExpiredBanner State (Desktop)

```
┌─────────────────────────────────────────────────────────┐
│                   [Shared Todos logo]                    │
│                      Shared Todos                        │
└─────────────────────────────────────────────────────────┘

┌──────────────────────── 400px ──────────────────────────┐
│  Welcome back                                           │
│  Don't have an account? Sign up                        │
│                                                         │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ [ℹ]  Session expired. Please log in again.          │ │  ← SessionExpiredBanner
│ │      info-50 bg (#EFF6FF), blue-200 border          │ │    info-600 icon (#2563EB)
│ │ [════════════════════════════════          ] 10s    │ │    optional progress bar
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
│ ┌─────────────────────────────────────────────────────┐ │
│ │  [G]  Continue with Google                          │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
│               ────────── or ──────────                  │
│                                                         │
│  Email address                                          │
│  ┌───────────────────────────────────────────────────┐ │
│  │                                                   │ │
│  └───────────────────────────────────────────────────┘ │
│                                                         │
│  Password                           Forgot password?    │
│  ┌───────────────────────────────────────────────────┐ │
│  │                                              [👁] │ │
│  └───────────────────────────────────────────────────┘ │
│                                                         │
│  ┌───────────────────────────────────────────────────┐ │
│  │                    Sign in                        │ │
│  └───────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘

Key:
  [ℹ] = info icon, 16px, info-600 (#2563EB)
  Banner: info-50 bg, blue-200 border — distinct from error-50/error-200 (AuthErrorBanner)
  Progress bar: 3px strip, bottom-inner edge, info-600 at 40% opacity, 10s linear shrink
  Slot: same position as AuthErrorBanner from BSD-1 (above Google button, below sub-header)
```

### Login Screen — SessionExpiredBanner State (Mobile, <768px)

```
┌──────────────── 100% - 32px ───────────────┐
│  Welcome back                               │
│  Don't have an account? Sign up            │
│                                             │
│ ┌─────────────────────────────────────────┐ │
│ │ [ℹ]  Session expired. Please log in.   │ │  ← same banner, full card width
│ │       padding: 10px 14px               │ │    reduced padding on mobile
│ │ [══════════════════         ] 10s      │ │
│ └─────────────────────────────────────────┘ │
│                                             │
│ ┌─────────────────────────────────────────┐ │
│ │  [G]  Continue with Google              │ │
│ └─────────────────────────────────────────┘ │
│  ──────────── or ────────────               │
│  [email field]                              │
│  [password field]          Forgot password? │
│  [Sign in button]                           │
└─────────────────────────────────────────────┘
```

### ReconnectingToast (Bottom-Center, Any Screen)

```
                      ↑ page content above ↑


          ┌──────────────────────────────────┐
          │  [⟳]  Reconnecting...            │   ← bottom-center, fixed
          └──────────────────────────────────┘   info-50 bg, info-600 border
                                                  200ms slide-up from bottom
          ↕ 24px gap to viewport bottom (desktop)
          ↕ 16px gap (mobile)
```

---

## Accessibility Specification (Consolidated)

```
KEYBOARD NAVIGATION:
  All new states use existing keyboard patterns from BSD-1 and BSD-2.
  No new keyboard shortcuts introduced.
  SessionExpiredBanner has no interactive elements → /login tab order unchanged.

SCREEN READER ANNOUNCEMENTS:
  ReconnectingToast:      role="status", aria-live="polite"
                          Announced once on appear; not announced on dismiss.
  SessionExpiredBanner:   role="status", aria-live="polite", aria-atomic="true"
                          Announced once on /login mount.
  ForcedLogoutHandler:    No ARIA needed on the handler itself — the /login
                          page load and banner announcement handle all communication.

FOCUS MANAGEMENT:
  /login with SessionExpiredBanner: focus → email input (unchanged from BSD-1).
  Do NOT shift focus to the banner. Screen readers receive the announcement via
  aria-live without focus theft. The user's goal is to re-authenticate, not
  to acknowledge the banner.

MOTION (prefers-reduced-motion):
  ReconnectingToast:      Skip translateY; use opacity-only or instant show/hide.
  SessionExpiredBanner:   Skip translateY; use opacity-only or instant show/hide.
  Progress bar:           Hidden entirely under reduced-motion. Timer still runs;
                          banner auto-dismisses at 10s without the visual countdown.

COLOR CONTRAST:
  "Reconnecting..." text (neutral-700 on info-50): passes WCAG AA (4.5:1+)
  SessionExpiredBanner text (neutral-700 on info-50): passes WCAG AA
  Info icon (info-600 on info-50): decorative; not relied upon alone for meaning
```

---

## Responsive Breakpoints Summary

| Component | Mobile (<768px) | Tablet (768–1023px) | Desktop (≥1024px) |
|-----------|----------------|---------------------|-------------------|
| SessionExpiredBanner | Full card width, padding 10px 14px | Full card width | Full card width (within 400px card) |
| ReconnectingToast | Bottom-center, calc(100%-32px) wide, bottom 16px | Bottom-center, auto width, bottom 24px | Bottom-center, auto width, max-width 320px, bottom 24px |

---

## Integration Notes for Engineering

1. **Cross-tab proactive sync (deferred):** No BroadcastChannel in v1. Each tab
   detects its own 401 independently. Engineering-lead to confirm this is acceptable
   given PRD-5's realtime WebSocket requirements. The WS connection erroring on
   family revocation may naturally accelerate Tab B's detection, making proactive
   sync unnecessary.

2. **WebSocket teardown on forced logout:** When ForcedLogoutHandler fires, any open
   WebSocket connections (PRD-5 scope) must also be closed. The WS teardown belongs
   in ForcedLogoutHandler step 3 (clear auth state). Engineering to include WS
   teardown in the implementation scope for PR-4 even if the WS connection itself
   lands in PR-5.

3. **Explicit logout response time (BSD-1 500ms timeout):** With PR-4's added
   family-revocation DB write in POST /api/v1/auth/logout, confirm server response
   time stays within the 500ms client-side timeout from BSD-1. The timeout is the
   fallback (user redirected regardless), but the revocation must still complete.

4. **sessionStorage key contract:**
   - `"post_login_redirect"` — destination URL; written by ForcedLogoutHandler;
     read and cleared by /login after successful login (existing BSD-1 key,
     ForcedLogoutHandler is a new writer alongside the existing SessionExpiryInterceptor)
   - `"post_login_redirect_reason"` — string "session_expired"; written by
     ForcedLogoutHandler; read and immediately cleared by /login on mount
   Both keys must be read-then-cleared atomically (not cleared on redirect)
   to survive browser back/forward navigation within the redirect sequence.

5. **In-flight edit draft recovery (future scope):** Lost edits on forced logout
   are accepted in v1. If a future PRD scopes draft recovery, the ForcedLogoutHandler
   step 1 (cancel queued requests) is the hook point for writing field drafts to
   sessionStorage before step 6 (redirect). Preserve step ordering to keep this
   addition non-breaking.

6. **OQ-4b (session-to-family linkage):** Engineering decision per PRD-4. No UX
   impact. ForcedLogoutHandler fires on any 401 from /refresh regardless of the
   DB linkage approach chosen.

7. **SilentRefreshInterceptor and existing SessionExpiryInterceptor (BSD-1):**
   The SilentRefreshInterceptor from this BSD supersedes the existing
   SessionExpiryInterceptor for the first-401 retry attempt. Engineering must
   ensure these two interceptors do not both fire on the same 401 (double-redirect
   risk). Recommended: SilentRefreshInterceptor runs first; it either resolves
   (happy path) or calls ForcedLogoutHandler (which already handles the redirect).
   The SessionExpiryInterceptor should only fire if the SilentRefreshInterceptor
   is not present (i.e., as a fallback for requests that bypass the global HTTP
   client layer, if any).

---

## Open Design Decisions

1. **Auto-dismiss progress bar on SessionExpiredBanner:** Specified as optional.
   If engineering finds the shrinking progress bar complex (especially under
   prefers-reduced-motion), plain 10s auto-dismiss with no visual countdown is
   equally acceptable. Engineering call — no product sign-off needed.

2. **OQ-4a (assumed resolved as generic-401):** SessionExpiredBanner text is
   "Session expired. Please log in again." for all 4 failure modes. If the user
   confirms a distinct security-termination message (OQ-4a alternate resolution),
   only the banner text changes. No structural changes to any component.

3. **Tab B stale-display window:** Accepted as v1 behavior. If PRD-5's WebSocket
   implementation naturally closes Tab B's connection on family revocation, the
   stale window effectively becomes zero and BroadcastChannel sync is definitively
   unnecessary. Revisit after PRD-5 WS design is finalized.
