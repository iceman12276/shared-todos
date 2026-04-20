from datetime import datetime, timedelta, timezone
from uuid import UUID

import secrets
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import Session
from app.models.user import User


async def create_session(db: AsyncSession, user_id: UUID, ttl_days: int) -> str:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=ttl_days)
    session = Session(user_id=user_id, token=token, expires_at=expires_at)
    db.add(session)
    await db.commit()
    return token


async def get_session_user(db: AsyncSession, token: str) -> User | None:
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(User)
        .join(Session, Session.user_id == User.id)
        .where(Session.token == token, Session.expires_at > now)
    )
    return result.scalar_one_or_none()


async def invalidate_session(db: AsyncSession, token: str) -> None:
    await db.execute(delete(Session).where(Session.token == token))
    await db.commit()


async def invalidate_all_user_sessions(db: AsyncSession, user_id: UUID) -> None:
    """Invalidate all sessions for a user — called on password reset (US-107)."""
    await db.execute(delete(Session).where(Session.user_id == user_id))
    await db.commit()
