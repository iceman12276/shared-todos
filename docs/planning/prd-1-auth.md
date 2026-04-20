# PRD-1: Authentication

**Version:** 1.0
**Date:** 2026-04-19
**Status:** Draft
**Author:** product-manager

---

## Problem

Users have no way to create an account, prove their identity, or maintain a secure session with the application. Without authentication, every feature of the product — list creation, sharing, collaboration — is inaccessible or insecure. Auth is the prerequisite for all other value.

---

## Users

- **Primary:** New users arriving to the app for the first time who need to register an account and log in.
- **Secondary:** Returning users who need to log in, manage their session, or recover access after forgetting their password.
- **Out of scope for this PRD:** Collaborators interacting with shared lists — that is covered in PRD-3.

---

## Goals

- A new user can register with an email address and a password.
- A new user can register (or an existing user can log in) via Google OAuth.
- A registered user can log in with their email and password.
- An authenticated session persists across page reloads until explicitly logged out or the session expires.
- A logged-in user can log out, terminating their session immediately.
- A user who has forgotten their password can reset it via an email-based flow.
- All auth state is enforced server-side via httpOnly session cookies (SameSite=Lax).

---

## Non-Goals

- MFA / two-factor authentication.
- Additional OAuth providers beyond Google (GitHub, Apple, etc.).
- Account deletion.
- Email address change after registration.
- Username/display-name separate from email.
- Admin-managed user accounts.
- SSO / SAML for enterprise.
- Session management UI (listing active sessions, remote logout of specific devices).

---

## User Stories

### US-101: Register with email and password

**Description:** As a new visitor, I want to create an account with my email and a password so I can access the app.

**Dependencies:** None

**Acceptance Criteria:**
- [ ] A user can submit an email address and a password to register.
- [ ] Email must be a syntactically valid address (RFC 5322); duplicates are rejected with a descriptive error (without revealing whether the email is registered — see Constraints).
- [ ] Password must be at least 12 characters. No maximum enforced. No complexity rules beyond minimum length.
- [ ] On success, the user is automatically logged in and redirected to their list dashboard.
- [ ] Passwords are stored using bcrypt or argon2 (engineering's choice of algorithm); plaintext is never stored or logged.
- [ ] Registration form does not expose whether a submitted email already exists in the system (generic "if this email is available, an account has been created" messaging, or equivalent that does not leak enumeration signal).

---

### US-102: Log in with email and password

**Description:** As a registered user, I want to log in with my email and password so I can access my lists.

**Dependencies:** US-101

**Acceptance Criteria:**
- [ ] A user can submit their email and password to log in.
- [ ] On success, an httpOnly session cookie (SameSite=Lax) is set and the user is redirected to their list dashboard.
- [ ] On failure (wrong email or wrong password), a generic error message is shown — the message must not distinguish between "email not found" and "wrong password" (prevents enumeration).
- [ ] Rate limiting is applied to login attempts: after 10 failed attempts within 15 minutes from the same IP, further attempts are rejected with a 429 response until the window resets.
- [ ] The session cookie has a configurable TTL (default: 7 days); the server must honor server-side session expiry and not rely solely on cookie expiry.

---

### US-103: Register or log in via Google OAuth

**Description:** As a new or returning user, I want to sign in with my Google account so I don't have to manage a separate password.

**Dependencies:** None

**Acceptance Criteria:**
- [ ] A "Sign in with Google" button initiates the OAuth 2.0 Authorization Code flow with PKCE.
- [ ] On first Google sign-in, an account is created using the Google-provided email and display name. No password is set on this account.
- [ ] On subsequent Google sign-ins with the same Google account, the existing account is found and the user is logged in.
- [ ] If a user previously registered with email+password using the same email address as their Google account, Google sign-in links to the existing account (no duplicate accounts).
- [ ] On success, the same httpOnly session cookie behavior as US-102 applies.
- [ ] If the OAuth flow fails or is cancelled by the user, a descriptive error is shown and no session is created.
- [ ] The OAuth state parameter is validated to prevent CSRF on the callback.

---

### US-104: Maintain session across page reloads

**Description:** As a logged-in user, I want my session to persist across page reloads so I don't have to log in on every visit.

**Dependencies:** US-102, US-103

**Acceptance Criteria:**
- [ ] An authenticated user who reloads or navigates within the app remains logged in without re-entering credentials.
- [ ] After the session TTL expires, the user is redirected to the login page on their next request; any in-progress data is not lost (state preserved in URL or local draft where possible).
- [ ] Unauthenticated requests to any protected route receive a 401 response (API) or a redirect to the login page (browser navigation).

---

### US-105: Log out

**Description:** As a logged-in user, I want to log out so that my session is terminated and my account is safe on shared devices.

**Dependencies:** US-102

**Acceptance Criteria:**
- [ ] A logged-in user can log out via a clearly accessible log-out action.
- [ ] On log out, the server-side session record is invalidated immediately — the session cookie alone is not sufficient to re-authenticate after logout.
- [ ] The session cookie is cleared from the browser on log out.
- [ ] After log out, the user is redirected to the login page.
- [ ] Any subsequent request using the old session cookie receives a 401.

---

### US-106: Request a password reset

**Description:** As a user who has forgotten their password, I want to request a reset link sent to my email so I can regain access.

**Dependencies:** US-101

**Acceptance Criteria:**
- [ ] A user can submit their email address on a "forgot password" screen.
- [ ] If the email corresponds to a registered account with a password (not Google-only), a time-limited reset link (valid for 1 hour) is sent to that address.
- [ ] The response is identical whether or not the email is registered — no enumeration signal is exposed.
- [ ] Reset tokens are single-use: once a link is clicked and the reset is completed, the token is invalidated.
- [ ] Reset tokens are cryptographically random (minimum 32 bytes of entropy); they are stored as a hash, not plaintext.
- [ ] In dev/CI, email is delivered to a local mailhog/mailpit sink. In production, a transactional email provider is used (vendor selection is engineering's call).
- [ ] If the email belongs to a Google-OAuth-only account (no password), the reset flow surfaces a message directing the user to sign in with Google instead; no reset email is sent.

---

### US-107: Complete a password reset

**Description:** As a user who has clicked a reset link, I want to set a new password so I can log in again.

**Dependencies:** US-106

**Acceptance Criteria:**
- [ ] Clicking a valid, unexpired reset link presents a form to enter and confirm a new password.
- [ ] The new password must meet the same requirements as US-101 (minimum 12 characters).
- [ ] On success, the new password is saved (hashed), all existing sessions for that account are invalidated, and the user is redirected to the login page with a success message.
- [ ] An expired or already-used token presents a clear error and prompts the user to request a new reset link.
- [ ] The reset form is not susceptible to CSRF (token is validated server-side).

---

## Success Metrics

- 100% of auth routes (register, login, logout, OAuth callback, reset-request, reset-complete) have integration tests hitting the real assembled app.
- Zero routes that reveal email enumeration signals (verified by QA test matrix).
- Rate-limiting on login is tested: 11th attempt within the window receives a 429.
- Password reset token invalidation is tested: re-use of a used token returns an error.
- Google OAuth happy path is covered by an E2E test with a stubbed OAuth provider.

---

## Constraints

- **httpOnly session cookies, SameSite=Lax** — no JWT in localStorage. Engineering may not deviate from this without a documented trade-off reviewed by validation-lead.
- **Password hashing** — bcrypt or argon2 only. MD5, SHA-*, and plaintext are explicitly prohibited.
- **No email enumeration** — registration, login failure, and password reset responses must not distinguish "email found" from "email not found." This is enforced at the API layer, not just the UI.
- **Rate limiting on login** — a hard requirement, not a nice-to-have. Must be in v1.
- **Reset tokens stored as hash** — never store the raw token; store a secure hash and compare on submission.
- **Google OAuth account linking** — if a user registers with email+password first, then later uses Google OAuth with the same email, the accounts must be linked, not duplicated.
- **Session invalidation on logout and password reset** — server-side invalidation is mandatory; cookie deletion alone is insufficient.

---

## Open Questions

None. All ambiguous decisions were resolved in the initiative memo (2026-04-19):
- Google OAuth: included in v1 (confirmed).
- Password reset: included in v1 (confirmed).
- MFA: explicitly out of v1 (confirmed).
- Additional OAuth providers: out of v1 (confirmed).
- Email service: mailhog/mailpit for dev/CI; real provider for prod — vendor selection deferred to engineering.
