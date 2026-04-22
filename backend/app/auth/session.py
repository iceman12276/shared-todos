import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.tokens import hash_token
from app.models.session import Session
from app.models.user import User


async def create_session(
    db: AsyncSession,
    user_id: UUID,
    ttl_days: int,
    *,
    family_id: UUID | None = None,
    commit: bool = True,
) -> str:
    """Create a new session record. Pass commit=False to batch into a larger transaction."""
    raw_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(days=ttl_days)
    session = Session(
        user_id=user_id,
        token_hash=hash_token(raw_token),
        expires_at=expires_at,
        family_id=family_id,
    )
    db.add(session)
    if commit:
        await db.commit()
    return raw_token


async def get_session_user(db: AsyncSession, token: str) -> User | None:
    now = datetime.now(UTC)
    result = await db.execute(
        select(User)
        .join(Session, Session.user_id == User.id)
        .where(Session.token_hash == hash_token(token), Session.expires_at > now)
    )
    return result.scalar_one_or_none()


async def invalidate_session(db: AsyncSession, token: str) -> None:
    await db.execute(delete(Session).where(Session.token_hash == hash_token(token)))
    await db.commit()


async def invalidate_all_user_sessions(
    db: AsyncSession, user_id: UUID, *, commit: bool = True
) -> None:
    """Invalidate all sessions for a user — called on password reset (US-107).

    Pass commit=False when the caller needs to batch this into a larger transaction.
    """
    await db.execute(delete(Session).where(Session.user_id == user_id))
    if commit:
        await db.commit()


async def invalidate_sessions_by_family(
    db: AsyncSession, family_id: UUID, *, commit: bool = False
) -> None:
    """Delete all sessions linked to a refresh token family (PRD-4 Invariant 4).

    Called when a family is revoked (logout or reuse detection). Defaults to
    commit=False so callers can batch this into the family revocation transaction.
    """
    await db.execute(delete(Session).where(Session.family_id == family_id))
    if commit:
        await db.commit()
