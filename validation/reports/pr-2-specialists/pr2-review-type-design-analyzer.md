# PR #2 Type Design Analysis — 2 MEDIUM, 5 LOW; convention-setter PASS

## Rating Matrix
| Type | Encap | Invariant | Useful | Enforce |
|---|---|---|---|---|
| User | 6 | 6 | 8 | 6 |
| Session | 5 | 5 | 9 | 7 |
| PasswordResetToken | 8 | 8 | 9 | 7 |
| RegisterRequest/LoginRequest | 6 | 5 | 8 | 6 |
| UserOut | 5 | 4 | 6 | 5 |
| PasswordResetCompleteBody | 6 | 5 | 8 | 6 |
| Settings (delta) | 8 | 7 | 9 | 8 |

## Convention-setter check: PASS
Every model inherits Base, uses Mapped[...] with type_annotation_map (UUID → Uuid(as_uuid=True), datetime → DateTime(timezone=True)). Zero naive timestamps. Migration shows deterministic constraint names (pk_users, ix_sessions_token, fk_*, uq_*). PR-1 convention propagates cleanly — strong signal for PR-3/4/5.

## MEDIUM

### 1. `Session.token` stored RAW (file: models/session.py:15)
Unlike sibling `PasswordResetToken.token_hash` (correctly SHA-256), `Session.token` is raw `secrets.token_urlsafe(32)`. DB read via SQLi / logs / backup leak / stolen replica yields live session credentials. Glaring asymmetry with sibling in same PR. PR-5 realtime inherits — compromised session row = WS takeover. **Fix:** rename to `token_hash`, hash in create_session, compare via hmac.compare_digest in get_session_user. Helper already exists at `app/auth/tokens.py`.

### 2. `User` identity invariant not enforced (models/user.py:16-17)
Both `password_hash` and `google_sub` nullable, but business rule (implicit in router.py:109 + reset logic:160-162) is "at least one must be set." Missing CheckConstraint:
```python
__table_args__ = (sa.CheckConstraint(
    "password_hash IS NOT NULL OR google_sub IS NOT NULL",
    name="at_least_one_auth_method"),)
```
Without it, a future OAuth-linking bug could create a ghost user. Naming convention produces `ck_users_at_least_one_auth_method`.

## LOW

- L1. `UserOut.id: str` — should be `id: UUID`; avoids `str(user.id)` at every call site. PR-3+ inherits if not fixed now.
- L2. Plaintext field names `password`, `new_password` — consider SecretStr to prevent log/traceback leakage; propagates to PR-6 frontend type generation.
- L3. `Session` lacks `relationship(User, lazy="raise")` — prevents N+1 in async; PR-5 WS auth will want `session.user`.
- L4. PasswordResetToken: no partial unique index on `(user_id) WHERE used_at IS NULL AND expires_at > now()` — if business rule is "at most one active token per user."
- L5. `secret_key` has dev default (overlaps silent-failure-hunter C6)
- L6. `rate_limit_login_attempts: int = Field(default=10, ge=1)` — add `le=10_000` bound to prevent config-typo disabling.

## Positive
- SessionService is free functions (not anemic class). Idiomatic SQLAlchemy 2.x async.
- `ondelete="CASCADE"` consistent on both Session/PasswordResetToken → User.
- `email: Mapped[str] = mapped_column(sa.String(254), unique=True, index=True)` — RFC-correct, unique enforced at DB (not just ORM).
- `PasswordResetToken` is best-designed type in PR — token never raw, used_at for single-use state, timezone-aware expires_at.
- Settings extends PR-1 `extra="forbid"` cleanly. No drift.

## Verdict
Structural foundation strong, PR-1 conventions propagate cleanly. 2 MEDIUMs (raw Session.token, missing User CheckConstraint) are load-bearing — both compound into PR-5 (realtime auth) and PR-4 (share with ghost user). Recommend addressing before PR-3 merges to avoid second alembic revision across three FK'd tables.
