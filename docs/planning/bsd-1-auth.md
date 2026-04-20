# BSD-1: Authentication Flows

**Version:** 1.0
**Date:** 2026-04-19
**Status:** Draft
**Author:** ux-designer
**PRD Reference:** PRD-1: Authentication

---

## Overview

This BSD covers every screen and component a user touches during authentication: registration (email+password), login (email+password), Google OAuth entry point, forgot-password request, password-reset completion, session maintenance, and logout. It also defines all loading, success, error, and edge-case states for each interaction.

---

## Global Design Tokens

```
TYPOGRAPHY:
  font-family: "Inter", system-ui, sans-serif
  heading-lg: 24px / 700 / line-height 32px
  body-base: 14px / 400 / line-height 20px
  body-sm: 12px / 400 / line-height 16px
  label: 14px / 500 / line-height 20px
  link: 14px / 500 / color brand-600 / underline on hover

COLOR:
  brand-600: #4F46E5   (primary action, links)
  brand-700: #4338CA   (hover state for brand-600)
  neutral-50: #F9FAFB  (page background)
  neutral-100: #F3F4F6 (input background)
  neutral-200: #E5E7EB (borders)
  neutral-700: #374151 (body text)
  neutral-900: #111827 (headings)
  error-500: #EF4444   (error text and border)
  error-50: #FEF2F2    (error input background tint)
  success-500: #22C55E (success states)
  white: #FFFFFF

SPACING (8px grid):
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 32px
  2xl: 48px
  3xl: 64px

RADIUS:
  sm: 4px
  md: 8px
  lg: 12px

SHADOW:
  card: 0 1px 3px rgba(0,0,0,0.1), 0 1px 2px rgba(0,0,0,0.06)
```

---

## Screen 1: Auth Shell (Shared Layout)

### Component Specification
```
COMPONENT: AuthShell
PURPOSE: Consistent wrapper for all auth screens — centers the card on the page and provides the app logo/name above it.
LOCATION: Wraps Register, Login, ForgotPassword, ResetPassword screens.
```

### Visual Specification
```
LAYOUT:
  - Page background: neutral-50, full viewport height
  - Content column: centered horizontally, vertically centered at 45% viewport height
    (slightly above true center to account for visual weight)
  - Column width: 400px fixed on desktop (>=1024px), 100% - 32px on mobile (<1024px)
  - Logo area: above card, margin-bottom 24px, center-aligned

TYPOGRAPHY:
  - App name "Shared Todos": heading-lg, neutral-900, center-aligned below logo icon

COLOR:
  - Background: neutral-50

SPACING:
  - Card padding: 32px all sides
  - Card: white background, radius lg, shadow card
  - Between logo area and card: 24px
```

### Responsive Specification
```
DESKTOP (>=1024px):
  - Card: 400px wide, fixed, centered on page

TABLET (768-1023px):
  - Card: 100% - 48px (max 400px), centered

MOBILE (<768px):
  - Card: 100% - 32px, centered
  - Card padding: 24px
```

---

## Screen 2: Register (Email + Password)

### Component Specification
```
COMPONENT: RegisterScreen
PURPOSE: Allow new users to create an account with email and password.
LOCATION: /register -- inside AuthShell
```

### Visual Specification
```
LAYOUT:
  - Card header: "Create your account" (heading-lg, neutral-900), margin-bottom 8px
  - Sub-header: "Already have an account? Sign in" with "Sign in" as a brand-600 link, margin-bottom 24px
  - Google OAuth button at top of form, then divider "or", then email+password fields
    (Google is placed first -- lower friction path emphasized)
  - Submit button: full width, below fields
  - "Terms and Privacy" note: body-sm, neutral-500, center-aligned, 12px margin-top

FORM FIELDS (below divider, top to bottom):
  1. Email address (type="email", autocomplete="email")
  2. Password (type="password", autocomplete="new-password") -- with visibility toggle
  3. Confirm password (type="password", autocomplete="new-password") -- with visibility toggle

FIELD ANATOMY:
  - Label: label style, neutral-700, margin-bottom 4px
  - Input: 100% width, height 40px, padding 8px 12px, radius md
    - Default: border 1px neutral-200, background white
    - Focus: border brand-600 (1px), box-shadow 0 0 0 3px rgba(79,70,229,0.15)
    - Error: border error-500 (1px), background error-50
  - Error message: body-sm, error-500, margin-top 4px, role="alert"

DIVIDER (between Google button and email form):
  - Horizontal rule with "or" text centered, margin 20px 0
  - Line: 1px neutral-200 each side, "or" text body-sm neutral-500

GOOGLE OAUTH BUTTON:
  - Full width, height 40px, white background, border 1px neutral-200, radius md
  - Google logo (SVG, 18px) left-aligned with 12px gap to label text
  - Text: "Continue with Google", label style, neutral-700
  - Hover: background neutral-50, border neutral-300

SUBMIT BUTTON:
  - Full width, height 40px, background brand-600, white text, radius md
  - Text: "Create account", label style, font 500
  - Hover: brand-700
  - Disabled: opacity 0.5, cursor not-allowed
  - Loading: spinner replaces label text (14px white spinner)
```

### Interaction Specification

```
ELEMENT: Email input
TRIGGER: blur (when focus leaves the field)
EXPECTED BEHAVIOR:
  1. Validate: non-empty AND basic email pattern (must contain @ with domain)
  2. If invalid: show inline error "Please enter a valid email address"
  3. If valid: clear any existing error for this field
LOADING STATE: n/a (sync client validation)
SUCCESS STATE: no error shown
ERROR STATE: error-500 border, error-50 background, inline message below field

ELEMENT: Password input
TRIGGER: blur
EXPECTED BEHAVIOR:
  1. Validate: minimum 12 characters
  2. If too short: show "Password must be at least 12 characters"
  3. If confirm-password has been touched and no longer matches: re-validate confirm
SUCCESS STATE: no error
ERROR STATE: error border + inline message

ELEMENT: Confirm password input
TRIGGER: blur
EXPECTED BEHAVIOR:
  1. Validate: value matches password field
  2. If mismatch: "Passwords do not match"
SUCCESS STATE: no error
ERROR STATE: error border + inline message

ELEMENT: "Create account" button
TRIGGER: click
EXPECTED BEHAVIOR:
  1. Run full client validation on all three fields; surface errors on any that fail
  2. If any invalid: stop, focus first invalid field
  3. If all valid: disable button, show spinner, POST /api/v1/auth/register
  4. On 201: redirect to /dashboard (session cookie set by server)
  5. On 409 (email taken): show non-enumeration banner:
     "If this email is available, your account has been created. Check your inbox to confirm."
  6. On 422 (server validation fail): show banner "Please check your entries and try again."
  7. On 429: show banner "Too many attempts. Please try again in a few minutes."
  8. On 500 / network error: show banner "Something went wrong. Please try again."
  9. On any error: re-enable button, clear spinner
LOADING STATE: spinner in button, label hidden, button disabled, fields remain editable
SUCCESS STATE: redirect to /dashboard
ERROR STATES: dismissible banner at top of card (error-50 bg, error-200 border, error-700 text)
EDGE CASES:
  - Double-click: second click blocked (button disabled on first click)
  - Network offline: step 8 error banner
  - Password < 12 chars slips through: server 422 fires, step 6 shows

ELEMENT: "Continue with Google" button
TRIGGER: click
EXPECTED BEHAVIOR:
  1. Initiate Google OAuth 2.0 Authorization Code flow with PKCE
  2. Redirect browser to Google consent screen
  3. On return to /auth/callback:
     - New user: account created + session set, redirect to /dashboard
     - Returning user: session set, redirect to /dashboard
     - Same email as existing email+password account: accounts linked, login succeeds
  4. If OAuth cancelled or errored: redirect to /register?error=oauth_cancelled
     Show banner: "Google sign-in was cancelled or failed. Please try again."
LOADING STATE: spinner inside button after click
SUCCESS STATE: redirect to /dashboard
ERROR STATE: banner on /register with error=oauth_cancelled
EDGE CASES:
  - Popup blocked: show inline note below button "Allow popups for this site if nothing opened"
  - Google service down: treat same as step 4 error

ELEMENT: "Sign in" link (sub-header)
TRIGGER: click
EXPECTED BEHAVIOR: navigate to /login (client-side routing)
```

### Data Flow Specification
```
DATA SOURCE: POST /api/v1/auth/register
REQUEST: { email: string, password: string }
RESPONSE:
  201: { user: { id, email, display_name } } -- session cookie set by server
  409: { error: "email_taken" }
  422: { error: "validation_error", detail: [...] }
  429: { error: "rate_limited" }
TRANSFORMS: none
BINDING:
  201 -> router.push("/dashboard")
  409/422/429/5xx -> error banner
```

### Navigation Specification
```
ENTRY POINTS: /register direct, "Create account" link from /login
EXIT POINTS:
  - Success: /dashboard
  - "Sign in" link: /login
  - Google OAuth: /auth/callback -> /dashboard or /register?error=oauth_cancelled
BACK BEHAVIOR: authenticated users are redirected away from /register to /dashboard (auth guard)
DEEP LINK: /register -- unauthenticated users only
```

### Accessibility Specification
```
KEYBOARD:
  Tab order: Google button -> Email -> Password -> Confirm password -> Create account -> Sign in link
  Enter on any input: submits form
  Escape: dismisses error banner

SCREEN READER:
  - form: aria-label="Create account"
  - Each input: associated label via htmlFor/id
  - Error messages: role="alert"
  - Error banner: role="alert"
  - Spinner state: aria-busy="true" on button, aria-label="Creating account..."

FOCUS MANAGEMENT:
  - Page load: focus email input
  - On validation error: focus first invalid input
  - On error banner: tabIndex=-1, programmatic focus()
```

---

## Screen 3: Login (Email + Password)

### Component Specification
```
COMPONENT: LoginScreen
PURPOSE: Allow existing users to authenticate with email and password or Google OAuth.
LOCATION: /login -- inside AuthShell
```

### Visual Specification
```
LAYOUT:
  - Card header: "Welcome back" (heading-lg, neutral-900), margin-bottom 8px
  - Sub-header: "Don't have an account? Sign up" with "Sign up" as brand-600 link, margin-bottom 24px
  - Google OAuth button at top
  - Divider "or"
  - Email field
  - Password field + "Forgot password?" link (body-sm, brand-600, right-aligned, margin-top 4px)
  - "Sign in" submit button (full width)
```

### Interaction Specification

```
ELEMENT: "Sign in" button
TRIGGER: click
EXPECTED BEHAVIOR:
  1. Client-validate: email non-empty + valid format, password non-empty (not blank)
  2. If invalid: show field errors, stop, focus first invalid field
  3. If valid: disable button, spinner, POST /api/v1/auth/login
  4. On 200: redirect to /dashboard (session cookie set by server)
  5. On 401: show error banner "Incorrect email or password."
     (MUST NOT distinguish wrong email vs wrong password -- anti-enumeration)
  6. On 429: show banner "Too many sign-in attempts. Please wait 15 minutes before trying again."
  7. On 500 / network: show generic error banner "Something went wrong. Please try again."
  8. On any error: re-enable button, clear spinner
LOADING STATE: spinner in button, button disabled
SUCCESS STATE: redirect to /dashboard
ERROR STATE: dismissible banner at top of card
EDGE CASES:
  - 10 failed attempts / 15 min from same IP: step 6 (429) fires
  - Correct credentials after lockout window expires: succeeds normally

ELEMENT: "Forgot password?" link
TRIGGER: click
EXPECTED BEHAVIOR:
  1. Navigate to /forgot-password
  2. If email field has a value, pass it: /forgot-password?email=<value> for pre-population

ELEMENT: "Continue with Google" button
TRIGGER: click
EXPECTED BEHAVIOR: identical to Register screen Google OAuth flow
```

### Data Flow Specification
```
DATA SOURCE: POST /api/v1/auth/login
REQUEST: { email: string, password: string }
RESPONSE:
  200: { user: { id, email, display_name } } -- session cookie set
  401: { error: "invalid_credentials" }
  429: { error: "rate_limited", retry_after: number }
BINDING: 200 -> router.push("/dashboard"), 401/429/5xx -> error banner
```

### Navigation Specification
```
ENTRY POINTS: /login direct, links from /register and /forgot-password
EXIT POINTS: /dashboard (success), /register ("Sign up"), /forgot-password ("Forgot password?")
BACK BEHAVIOR: authenticated users redirected to /dashboard (auth guard)
```

### Accessibility Specification
```
KEYBOARD:
  Tab order: Google button -> Email -> Password -> Forgot password link -> Sign in button -> Sign up link
  Enter: submits form from any input
SCREEN READER: same patterns as Register
FOCUS MANAGEMENT:
  - Page load: focus email input
  - On error: focus banner or first invalid input
```

---

## Screen 4: Forgot Password

### Component Specification
```
COMPONENT: ForgotPasswordScreen
PURPOSE: Allow users to request a password reset link sent to their email.
LOCATION: /forgot-password -- inside AuthShell
```

### Visual Specification
```
LAYOUT (request form state):
  - Header: "Reset your password" (heading-lg)
  - Body text: "Enter your email address and we'll send you a reset link."
    (body-base, neutral-700, margin-bottom 24px)
  - Email field (pre-populated if ?email= param present)
  - "Send reset link" button (full width, brand-600)
  - "Back to sign in" link (body-sm, brand-600, center-aligned, margin-top 16px)

SUCCESS STATE (replaces entire card content after any non-network response):
  - Icon: envelope SVG, 40px, brand-600, center-aligned
  - Heading: "Check your email" (heading-lg)
  - Body: "If an account exists for [email address], you'll receive a password reset link
    shortly. Check your spam folder if you don't see it." (body-base)
  - "Back to sign in" button (full width, outlined variant)
  - Note: success state is shown regardless of whether email exists -- anti-enumeration
```

### Interaction Specification

```
ELEMENT: "Send reset link" button
TRIGGER: click
EXPECTED BEHAVIOR:
  1. Validate: email non-empty and valid format; show field error if not
  2. If valid: disable button, spinner, POST /api/v1/auth/password-reset/request
  3. On ANY server response (200, 404, 422, 429): show success state
     (intentionally opaque -- prevents email enumeration)
  4. On network failure (no response received):
     show error banner "Could not send request. Please check your connection and try again."
     re-enable button
LOADING STATE: spinner in button, button disabled
SUCCESS STATE: card content replaced with check-email message
ERROR STATE: only network failure shows an error banner
EDGE CASES:
  - OAuth-only account email: server sends no email; UI still shows success state
  - Rapid re-submission: rate-limited server-side; UI still shows success state
  - Network offline: error banner, button re-enabled

ELEMENT: "Back to sign in" link / button
TRIGGER: click
EXPECTED BEHAVIOR: navigate to /login
```

### Data Flow Specification
```
DATA SOURCE: POST /api/v1/auth/password-reset/request
REQUEST: { email: string }
RESPONSE: any non-network response -> show success state
BINDING: success state replaces card content
```

### Navigation Specification
```
ENTRY POINTS: "Forgot password?" on /login (?email= prepopulation)
EXIT POINTS: "Back to sign in" -> /login
```

### Accessibility Specification
```
KEYBOARD: Tab -> Email -> Send reset link -> Back to sign in
SCREEN READER:
  - Success state transition: aria-live="polite" on card content region
FOCUS MANAGEMENT:
  - On success state render: focus the "Check your email" heading (tabIndex=-1 + focus())
```

---

## Screen 5: Reset Password (Complete Reset)

### Component Specification
```
COMPONENT: ResetPasswordScreen
PURPOSE: Allow users who clicked a valid reset link to set a new password.
LOCATION: /reset-password?token=[token] -- inside AuthShell
```

### Visual Specification
```
TOKEN VALIDATION STATE (shown on page load):
  LOADING: full card shows centered spinner, text "Validating your reset link..."
  INVALID / EXPIRED / ALREADY-USED:
    - Icon: X-circle SVG, 40px, error-500, center-aligned
    - Heading: "This link has expired or is invalid"
    - Body: "Password reset links are only valid for 1 hour and can only be used once."
    - CTA: "Request a new link" button (full width, brand-600) -> /forgot-password
  VALID: show password form below

PASSWORD FORM (after valid token confirmed):
  - Header: "Set a new password" (heading-lg)
  - Body: "Your new password must be at least 12 characters." (body-base, neutral-700)
  - New password field (with visibility toggle)
  - Confirm new password field (with visibility toggle)
  - "Update password" button (full width, brand-600)

SUCCESS STATE (after successful reset):
  - Icon: check-circle SVG, 40px, success-500, center-aligned
  - Heading: "Password updated"
  - Body: "Your password has been changed. All previous sessions have been signed out."
  - "Sign in" button (full width, brand-600) -> /login
```

### Interaction Specification

```
ELEMENT: Page load (token validation)
TRIGGER: Component mount / URL parse
EXPECTED BEHAVIOR:
  1. Extract token from ?token= query param
  2. If no token: immediately show invalid state (no network call needed)
  3. Show loading spinner
  4. GET /api/v1/auth/password-reset/validate?token=[token]
  5. On 200 valid: hide spinner, show password form; focus new password input
  6. On 400/404/410: show invalid/expired state
LOADING STATE: full card spinner
ERROR STATE: invalid state with "Request a new link" CTA

ELEMENT: "Update password" button
TRIGGER: click
EXPECTED BEHAVIOR:
  1. Validate: new password >= 12 chars; confirm matches
  2. If invalid: show field errors, stop
  3. If valid: disable button, spinner, POST /api/v1/auth/password-reset/complete
  4. On 200: show success state (server has invalidated all sessions)
  5. On 400 (already used): show banner "This reset link has already been used.
     Please request a new one." + "Request new link" button inline
  6. On 410 (expired): show banner "This link has expired." + "Request new link" inline
  7. On 422: show banner "Please check your entries and try again."
  8. On 500 / network: show generic error banner
  9. On any error: re-enable button
LOADING STATE: spinner in button, button disabled
SUCCESS STATE: card content replaced with success state
ERROR STATES: banners for token errors; field errors for validation failures
EDGE CASES:
  - Token tampered: validate endpoint returns 400, invalid state shown on page load
  - CSRF: token submitted in request body (not cookie), validated server-side
  - Refresh after success: token consumed, validate returns 400, invalid state shown
```

### Data Flow Specification
```
VALIDATE: GET /api/v1/auth/password-reset/validate?token=
  200: { valid: true }
  400/404/410: { error: "invalid" | "expired" | "already_used" }

COMPLETE: POST /api/v1/auth/password-reset/complete
  REQUEST: { token: string, new_password: string }
  RESPONSE:
    200: {} -- password updated, all sessions invalidated server-side
    400: { error: "already_used" }
    410: { error: "expired" }
    422: { error: "validation_error" }
```

### Navigation Specification
```
ENTRY POINTS: Reset link in email -> /reset-password?token=...
EXIT POINTS:
  - Success: "Sign in" button -> /login
  - Invalid/expired: "Request new link" -> /forgot-password
```

### Accessibility Specification
```
KEYBOARD: New password -> Confirm password -> Update password button
SCREEN READER:
  - Loading: aria-busy="true" on card, aria-label="Validating reset link"
  - Success: role="status" announcement
  - Error states: role="alert"
FOCUS MANAGEMENT:
  - Valid token, form shown: focus new password input
  - Invalid state: focus "Request a new link" button
  - Success state: focus "Sign in" button
```

---

## Component: Auth Error Banner

### Component Specification
```
COMPONENT: AuthErrorBanner
PURPOSE: Display non-field-level errors (server errors, rate limits, network failures) at the top of the card.
LOCATION: Top of any auth card, below header, above form.
```

### Visual Specification
```
LAYOUT:
  - Full card width, margin-bottom 16px
  - Padding: 12px 16px
  - Background: error-50
  - Border: 1px error-200
  - Border-radius: md (8px)
  - Flex row: warning icon (16px, error-500) + message text + dismiss X (right-aligned)

TYPOGRAPHY: body-sm, error-700

ANIMATION:
  - Appear: slide-down 150ms ease-in
  - Dismiss: fade-out 200ms

DISMISS:
  - X icon button (16x16), aria-label="Dismiss error", error-400 / hover error-700
```

### Interaction Specification
```
TRIGGER: Appears after failed form submission
EXPECTED BEHAVIOR:
  1. Slide into view below card header
  2. Focus shifted to banner (tabIndex=-1 + focus()) for screen readers
  3. Dismissed via X click (fade out) or automatically when user re-submits
```

---

## Component: Password Visibility Toggle

### Component Specification
```
COMPONENT: PasswordVisibilityToggle
PURPOSE: Let users reveal/hide password text.
LOCATION: Trailing icon inside every password input.
```

### Visual Specification
```
- Eye icon (16px), right side of input, padding-right 36px on input to avoid overlap
- Default: neutral-400; hover: neutral-700
- Toggles between eye SVG (hidden) and eye-slash SVG (visible)
```

### Interaction Specification
```
ELEMENT: Eye icon button
TRIGGER: click
EXPECTED BEHAVIOR:
  1. Toggle input type between "password" and "text"
  2. Toggle icon: eye-slash when showing (text is visible), eye when hiding (text is obscured)
  3. aria-label updates: "Show password" / "Hide password"
  4. Announce to screen reader the new state
  5. Focus stays on toggle button

ACCESSIBILITY:
  aria-label: "Show password" / "Hide password"
  aria-pressed: false / true
  role: "button"
```

---

## Component: Session Expiry Interceptor

### Component Specification
```
COMPONENT: SessionExpiryInterceptor
PURPOSE: Redirect authenticated users to /login when their session expires mid-use, preserving their current URL for post-login redirect.
LOCATION: Global HTTP client layer (wraps all authenticated API calls).
```

### Interaction Specification
```
TRIGGER: Any authenticated API request returns 401
EXPECTED BEHAVIOR:
  1. Intercept 401 before calling component sees it
  2. Store current URL path in sessionStorage as "post_login_redirect"
  3. Redirect to /login?session_expired=true
  4. /login reads ?session_expired=true: show dismissible info banner (blue tint, not error):
     "Your session has expired. Please sign in again."
  5. After successful login: check sessionStorage for stored path, redirect there, clear key
EDGE CASES:
  - Parallel 401s from concurrent requests: deduplicate with an in-flight flag (only first fires)
  - Stored path is /register or /login or /: redirect to /dashboard instead
  - session_expired banner dismissed by user: URL param cleared via replaceState
```

---

## Component: Logout Action

### Component Specification
```
COMPONENT: LogoutButton
PURPOSE: Terminate the current session and redirect to /login.
LOCATION: App navigation header (all authenticated screens).
```

### Visual Specification
```
- "Sign out" label, body-sm, neutral-700
- Hover: neutral-900, underline
- Location: top navigation bar, far right
```

### Interaction Specification
```
ELEMENT: "Sign out" action
TRIGGER: click
EXPECTED BEHAVIOR:
  1. Disable button to prevent double-click
  2. POST /api/v1/auth/logout (session identified by cookie)
  3. On any response OR timeout (500ms): clear client-side auth state, redirect to /login
  4. Server invalidates session record synchronously; cookie alone insufficient
LOADING STATE: brief spinner (max 500ms then redirect regardless)
SUCCESS STATE: redirect to /login
ERROR STATE: always redirect to /login (best-effort, user intent is to log out)
EDGE CASES:
  - Network offline: client state cleared, redirect to /login
  - Double-click: second click ignored (disabled on first)
```

### Data Flow Specification
```
DATA SOURCE: POST /api/v1/auth/logout
REQUEST: {} (session identified by httpOnly cookie)
RESPONSE: 200 {} -- session record deleted server-side
BINDING: always redirect to /login after completion or 500ms timeout
```

---

## Navigation Flow: Complete Auth Journey

```
/register ──(success 201)──> /dashboard
    |
    "Sign in" link ──> /login
    Google OAuth ──> /auth/callback ──> /dashboard

/login ──(success 200)──> /dashboard
    |                          |
    "Forgot password?" ──> /forgot-password     "Sign out" ──> /login
    Google OAuth ──> /auth/callback ──> /dashboard

/forgot-password ──(any server response)──> [success state] ──"Back to sign in"──> /login

/reset-password?token=
    |
    valid token ──> password form ──(success)──> [success state] ──> /login
    invalid/expired ──> [error state] ──"Request new link"──> /forgot-password
```

---

## Open Design Decisions (for planning-lead)

1. **Google button position:** Placed above email+password to emphasize lower-friction path. If preference is traditional order (email first), swap without behavior change.

2. **Email confirmation gate:** PRD-1 does not require email verification before login. BSD assumes auto-login on register. If this changes, a post-register "check your email" intercept screen must be added.

3. **"Remember me" toggle:** PRD specifies 7-day TTL with no user control. BSD omits the toggle. If added, it requires PRD-1 update first.
