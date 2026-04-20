"""Unit tests for session service — uses real DB via db_session fixture."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.session import create_session, get_session_user, invalidate_session
from app.models.session import Session
from app.models.user import User


@pytest.fixture
async def sample_user(db_session: AsyncSession) -> User:
    user = User(
        email="alice@example.com",
        display_name="Alice",
        password_hash=None,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_create_session_returns_token(db_session: AsyncSession, sample_user: User) -> None:
    token = await create_session(db_session, sample_user.id, ttl_days=7)
    assert isinstance(token, str)
    assert len(token) > 20


@pytest.mark.asyncio
async def test_create_session_stores_in_db(db_session: AsyncSession, sample_user: User) -> None:
    token = await create_session(db_session, sample_user.id, ttl_days=7)
    from sqlalchemy import select
    result = await db_session.execute(select(Session).where(Session.token == token))
    row = result.scalar_one_or_none()
    assert row is not None
    assert row.user_id == sample_user.id


@pytest.mark.asyncio
async def test_get_session_user_valid(db_session: AsyncSession, sample_user: User) -> None:
    token = await create_session(db_session, sample_user.id, ttl_days=7)
    user = await get_session_user(db_session, token)
    assert user is not None
    assert user.id == sample_user.id


@pytest.mark.asyncio
async def test_get_session_user_invalid_token(db_session: AsyncSession) -> None:
    user = await get_session_user(db_session, "bogus-token")
    assert user is None


@pytest.mark.asyncio
async def test_get_session_user_expired(db_session: AsyncSession, sample_user: User) -> None:
    token = await create_session(db_session, sample_user.id, ttl_days=-1)
    user = await get_session_user(db_session, token)
    assert user is None


@pytest.mark.asyncio
async def test_invalidate_session(db_session: AsyncSession, sample_user: User) -> None:
    token = await create_session(db_session, sample_user.id, ttl_days=7)
    await invalidate_session(db_session, token)
    user = await get_session_user(db_session, token)
    assert user is None
