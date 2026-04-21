# PRD-4: Refresh-Token Rotation

**Version:** 1.0
**Date:** 2026-04-21
**Status:** Draft
**Author:** product-manager

---

## Problem

PR-1 established server-side session tokens stored as hashed values in the `sessions` table, with a configurable TTL (default: 7 days). A session token with a long TTL that never rotates is a static secret — if it is stolen (e.g., via network interception, server-side log leak, or a compromised database backup), an attacker can use it for the full TTL without the legitimate user knowing. There is currently no mechanism to detect token reuse, rotate credentials on use, or revoke a compromise mid-session.

Refresh-token rotation solves this by replacing the session token on each use, making every prior token single-use and worthless after rotation. Reuse of a rotated-away token is an unambiguous compromise signal, triggering revocation of the entire token family and forcing re-authentication.

---

## Users

- **Primary:** Any authenticated user with an active session — all registered users are affected by this feature transparently.
- **Secondary:** Security-conscious users who want assurance that a stolen session token cannot be used indefinitely without detection.
- **Out of scope for this PRD:** Admin-level session management UI; device-level session listing and revocation.

---

## Goals

- Every use of a refresh token produces a new refresh token and invalidates the old one (rotation-on-use).
- Reuse of a previously rotated token is detected within the same request that presented it and results in immediate revocation of the entire token family, forcing re-authentication.
- Refresh tokens ride httpOnly `SameSite=Lax` cookies, consistent with the existing session cookie pattern from PR-1.
- Refresh tokens are stored server-side as hashes — never as plaintext — consistent with the `hash_token` precedent from PR-2.
- A dedicated `POST /api/v1/auth/refresh` endpoint is the sole mechanism for obtaining a new session credential.
- Token families are revocable as a unit: revoking one family member revokes all.

---

## Non-Goals

- JWT-based refresh tokens. All tokens remain server-side hashed records. No stateless token scheme.
- Session-listing or per-device session management UI (listing "logged in from X devices" or remote logout of individual sessions).
- Per-device token families — the revocation unit is a token family (one per login event), not a physical device.
- "Remember me" toggle affecting refresh-token TTL — token TTL is fixed per environment and not user-configurable in v1.
- Inactivity-based auto-rotation outside of the explicit refresh endpoint call — tokens only rotate when `POST /api/v1/auth/refresh` is called.
- OAuth token management for Google — Google's own tokens are managed by Google's OAuth infrastructure, not this system.
- Admin-visible session audit log UI.

---

## Token Family Model

A **token family** is created at each login event (email+password or OAuth). It groups all refresh tokens issued in a chain from that single login. The revocation unit is the family: revoking any member revokes all tokens in that family, forcing re-authentication.

- One family per login event, not per device or per user account.
- A user who logs in on two browsers has two families; revoking one family does not affect the other.
- A family is identified by a `family_id` (UUID), shared across all tokens in the chain.

---

## Storage Model

A new `refresh_tokens` table mirrors the `sessions` table pattern. It does not replace `sessions` — the existing session/cookie lookup in `session.py` remains unchanged. Refresh tokens are a separate credential layer that, when presented to `POST /api/v1/auth/refresh`, issue a new session token.

**Proposed schema (informational — engineering owns the exact Alembic migration):**

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID, PK | Row identity |
| `family_id` | UUID, indexed | Groups all tokens from one login event |
| `user_id` | UUID, FK → users.id (CASCADE) | Owner |
| `token_hash` | varchar(64), unique, indexed | SHA-256 of the raw token (same `hash_token` function as PR-2) |
| `parent_token_id` | UUID, FK → refresh_tokens.id, nullable | Points to the token this was rotated from; null for the root of a family |
| `issued_at` | timestamptz | When this token was issued |
| `expires_at` | timestamptz | Absolute expiry (e.g., 30 days from issuance) |
| `revoked_at` | timestamptz, nullable | Set when revoked; null = active |

Token is considered valid if: `revoked_at IS NULL AND expires_at > now()`.

---

## Rotation Triggers

Refresh tokens rotate **only on explicit call to `POST /api/v1/auth/refresh`**. No other request path rotates tokens. Inactivity does not trigger rotation. The access session (the existing `sessions` table record from PR-1) and the refresh token are separate credentials; the refresh token is the long-lived credential used to re-issue a session after the session expires or the user's session cookie is cleared.

---

## User Stories

### US-401: Obtain a refresh token on login

**Description:** As a user who logs in, I want a refresh token issued alongside my session cookie so I can silently renew my session without re-entering credentials.

**Dependencies:** US-102, US-103

**Acceptance Criteria:**
- [ ] On successful login (email+password or OAuth), a new token family is created and a refresh token is issued.
- [ ] The refresh token is delivered as a separate httpOnly `SameSite=Lax` cookie (e.g., `refresh_token`), distinct from the session cookie.
- [ ] The raw refresh token is never returned in a response body or visible to JavaScript.
- [ ] The refresh token hash and family metadata are stored in the `refresh_tokens` table.
- [ ] The refresh token TTL is 30 days (configurable via settings; default value is 30 days).

---

### US-402: Silently refresh a session

**Description:** As a user whose session has expired or will expire soon, I want my client to call the refresh endpoint and receive a new session without prompting me to log in again.

**Dependencies:** US-401

**Acceptance Criteria:**
- [ ] `POST /api/v1/auth/refresh` accepts the refresh token from the `refresh_token` httpOnly cookie (no request body or Authorization header variant).
- [ ] On a valid, unexpired, non-revoked refresh token: the old refresh token is revoked (marked `revoked_at = now()`), a new refresh token is issued in the same family (`parent_token_id` pointing to the old record), and a new session is issued.
- [ ] The response sets two cookies: the new session cookie and the rotated refresh token cookie (via `Set-Cookie`).
- [ ] No token material is returned in the response body.
- [ ] The old refresh token cannot be used again after rotation — a second request presenting the old token triggers reuse detection (US-404).
- [ ] An expired or absent refresh token returns 401 with a generic "session expired" message. The client should redirect to login.

---

### US-403: Refresh token expiry and explicit logout

**Description:** As a user, I want my refresh token to expire after a fixed TTL, and for logout to permanently invalidate my refresh token family.

**Dependencies:** US-401, US-105

**Acceptance Criteria:**
- [ ] A refresh token presented after its `expires_at` returns 401. The user must log in again.
- [ ] On logout (`POST /api/v1/auth/logout`), the user's current refresh token family is revoked in full (all records with the matching `family_id` have `revoked_at` set).
- [ ] After logout, presenting the refresh token from that family returns 401 — the family revocation is respected even if individual token records are not yet expired.

---

### US-404: Reuse detection and family revocation

**Description:** As the system, when a previously rotated-away refresh token is presented, I want to detect this as a likely compromise signal, revoke the entire token family, and force re-authentication.

**Dependencies:** US-402

**Acceptance Criteria:**
- [ ] Presenting a refresh token that has already been rotated (its `revoked_at` is set) triggers immediate revocation of the entire `family_id` — all tokens in the family have `revoked_at` set within the same request.
- [ ] The response to a reuse attempt is 401 with a generic message (see Open Questions — OQ-4a).
- [ ] The session associated with the compromised family is also invalidated — a session cookie from that login event cannot be used after family revocation.
- [ ] No information is leaked in the response that would allow an attacker to distinguish "token reuse detected" from "token expired" or "token not found" — the HTTP status code and message body must be identical across all 401 scenarios.
- [ ] The revocation completes within the same database transaction as the detection — there is no window between detection and revocation.

---

### US-405: Stranger / unauthenticated access to the refresh endpoint

**Description:** As the system, requests to `POST /api/v1/auth/refresh` with no cookie, a malformed cookie, or a token not present in the database must be rejected safely.

**Dependencies:** None

**Acceptance Criteria:**
- [ ] A request with no `refresh_token` cookie returns 401.
- [ ] A request with a cookie value whose hash does not match any `refresh_tokens` row returns 401.
- [ ] The 401 response body and message are identical to those for expired and reused tokens — no distinguishing signal.
- [ ] The refresh endpoint does not expose any information about whether the token existed but expired, versus never existed.

---

## Invariants

These are correctness invariants that must hold at all times. Engineering and QA should treat violations as bugs, not edge cases:

1. **Single active token per family at any moment.** Within a family, at most one token has `revoked_at IS NULL AND expires_at > now()`. After rotation, the predecessor is revoked before the successor is inserted (within one transaction).
2. **Reuse-detection is atomic.** The window between detecting a reused token and revoking the family must be zero — detection and revocation happen in the same database transaction.
3. **No token material in logs.** Raw refresh tokens must never appear in application logs, error messages, or audit trails. Only `token_hash` (or the `family_id`) may appear in logs.
4. **Family revocation propagates to sessions.** When a family is revoked (reuse or logout), all session records (`sessions` table) for the same user that were issued by tokens in that family must also be invalidated. (Engineering: this requires tracing session → refresh token → family, or storing `family_id` on the session record. Approach is engineering's decision — flag the linkage requirement here.)
5. **Cookie attributes match session cookie.** The `refresh_token` cookie must be httpOnly, `SameSite=Lax`, and must set `Secure` in production. It must not be accessible to JavaScript.

---

## Success Metrics

- `POST /api/v1/auth/refresh` has an integration test that boots the real assembled app and verifies: valid rotation issues new cookies and invalidates the old token.
- Reuse detection test: presenting a rotated-away token returns 401 AND all other tokens in the same family are subsequently invalid (verified in the same test sequence).
- Revoked family test: after logout, the refresh token from the revoked family returns 401.
- Expired token test: a token presented after `expires_at` returns 401.
- All four 401 paths (no token, expired, reused, revoked) return indistinguishable HTTP responses (same status code, same response body shape) — verified by a single parameterized test.
- Zero occurrences of raw token material in application logs (verified by log inspection in the test suite).

---

## Constraints

- **No JWT.** All refresh tokens are server-side hashed records in `refresh_tokens`. Engineering may not introduce a stateless token scheme for this feature without a documented trade-off reviewed by validation-lead.
- **Same hashing function as PR-2.** Use `hash_token` from `app/auth/tokens.py` (SHA-256, constant-time comparison via `verify_token_hash`). Do not introduce a second hashing scheme.
- **Cookie-only delivery.** The refresh token must be delivered exclusively via httpOnly cookie. No response body, no Authorization header, no localStorage.
- **Atomic revocation.** Reuse detection and family revocation must complete in a single database transaction. No partial revocation states.
- **Configurable TTLs via Settings.** Refresh token TTL must be a `pydantic-settings` field with a documented default (30 days). Hard-coded TTLs are prohibited.

---

## Open Questions

**OQ-4a: User-facing message on reuse detection (sibling of OQ-1 from PRD-3).**

OQ-1 in PRD-3 established that strangers get a 404 (never 403) to avoid leaking list existence. This PRD's analogous decision is: when a refresh token is presented that has been rotated away (a reuse-detection trigger), what does the response look like?

*Recommendation:* Return HTTP 401 with a generic body (e.g., `{"detail": "Session expired. Please log in again."}`) — identical to expired-token and not-found-token responses. Do not indicate that reuse was detected or that a security event occurred. An attacker who knows their reuse triggered revocation gains information about the system's detection logic; a generic "session expired" denies that signal.

*Needs user confirmation:* Is the recommended generic-401 behavior approved, or should there be a distinct user-facing message (e.g., "Your session was terminated for security reasons. Please log in again.") that is more informative to the legitimate user without leaking the specific trigger to an attacker?

**Who resolves:** User decision, with validation-lead's input on whether any signal difference aids or hinders detection evasion.

---

**OQ-4b: Session-to-family linkage mechanism.**

Invariant 4 above requires that when a refresh token family is revoked, the associated session records in the `sessions` table are also invalidated. This requires a way to trace from a session back to its originating family (or vice versa). Two approaches exist: (a) add a `family_id` foreign key to the `sessions` table, or (b) look up sessions by `user_id` and timestamp proximity. Approach (a) is cleaner but requires a migration touching the existing `sessions` table from PR-1.

*This is engineering's decision — flagged here so it is not overlooked during implementation. No PM recommendation; both approaches satisfy the invariant.*

**Who resolves:** engineering-lead.
