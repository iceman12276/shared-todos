# PR #2 Comment Analysis — 5 HIGH (bug-encoding), 6 missing WHY, 4 dead WHAT, 3 rot-risk

## HIGH — bug-encoding inaccurate comments (fix first)

### 1. csrf.py:7-11 — docstring exemption list contradicts code
Docstring claims `/api/v1/auth/oauth/*` is exempt, but code only exempts `login` and `register`. OAuth works incidentally because GETs filter out earlier (line 33), NOT because of path rule. Future maintainer adding `POST /api/v1/auth/oauth/*` reads docstring, ships CSRF bypass. Also claims "under /api/v1/" scope, but no path-prefix guard in code — applies to every path.

### 2. csrf.py:40-41 — stale comment actively wrong
"OAuth callback is GET-only — no exemption needed, but protect any future OAuth POST endpoints by NOT exempting the entire prefix" — no corresponding code enforces this. Comment implies deliberate design decision that isn't there.

### 3. oauth.py:1-11 — module docstring overstates state integrity
"Signed with itsdangerous AND nonce-bound via cookie" — signing alone does NOT prevent CSRF; only nonce-cookie comparison (line 154) does. A reader might loosen the cookie check later thinking signing is sufficient.

### 4. oauth.py:78-83 — docstring on `_decode_id_token_payload` factually wrong
"dev/test only path" — BUT called unconditionally from real callback handler in production. Future security-sweep reader sees "dev/test only" and assumes prod has separate verification, fails to find it, assumes it's already there, moves on.

### 5. rate_limiter.py:18 — misdescribes data structure
"(ip, window_start) -> count" — actually `dict[str, list[datetime]]`. Leftover from earlier fixed-window design, never updated after sliding-window switch.

## Missing WHY where required
6. dependencies.py — `require_auth` contract vs get_session precedent. Return type, 401 collapse (bad session = no session for anti-enum), no TTL extension.
7. router.py:37-56 — `_set_auth_cookies`: `httponly=False` on CSRF cookie needs rationale (double-submit pattern requires JS read; httponly=True would defeat).
8. router.py:72-78 — register anti-enum comment good but misses user-facing consequence: `user=None`+201 is a deliberate API quirk.
9. router.py:160-162 — password-reset Google-only `pass` branch: is this intentional per US-106 anti-enum or silent footgun?
10. session.py:12-18 — `create_session` has no docstring at all. Security-critical: token entropy, TTL semantics, persistence order.
11. oauth.py:196-210 — account linking comment says WHAT not WHY. Linking-on-email-match threat model needs explicit documentation.

## Dead WHAT comments to remove
12. rate_limiter.py:39 — `# Evict expired entries` (restates list comp)
13. oauth.py:157 — `# Exchange code for tokens` (restates next statement)
14. router.py:218 — `# Mark token as used (single-use)` (restates `prt.used_at = now`)
15. router.py:222 — `# Update password` (restates assignment)
16. password.py:6 — OWASP parameter comment borderline — strengthen with measurement data or shorten to OWASP-page date reference.

## Rot-risk references
17. US-xxx / OQ-1 story-ID references throughout (router.py, session.py, dependencies.py, oauth.py, rate_limiter.py). Examples: `(US-101)`, `(US-106)`, `(OAuth CSRF, item 4)` — "item 4" especially rot-prone (unanchored numeric). CLAUDE.md explicitly warns against reference-rot.
18. rate_limiter.py:7-8 — "v1 single-replica" will rot the moment topology changes.
19. password.py:9-11 — GOOD WHY (threat model, mechanism, alternative). Keep.

## Exemplars to preserve
- password.py:9-11 (dummy hash rationale) — perfect WHY
- router.py:106-108 (login dummy-hash) — explains hash() vs verify() timing distinction
- router.py:72-75 (register Set-Cookie anti-enum) — explains non-obvious header dimension
- oauth.py:44 (`_NONCE_TTL = 600`) — one-line magic-number justification

## Files analyzed
`csrf.py`, `oauth.py`, `router.py`, `session.py`, `password.py`, `tokens.py`, `rate_limiter.py`, `dependencies.py`, `email.py`.

## Verdict
Comment density appropriate, most WHY comments load-bearing. Inaccurate comments (items 1-5) are security-bug-encoding and must be fixed. Missing WHY on auth contracts (items 6-11) should be added. Dead WHATs (items 12-15) and rot-risk references (items 17-18) are polish.
