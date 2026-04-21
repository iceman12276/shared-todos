"""Integration tests: Session.token_hash column stores hash, not raw token (HIGH-9)."""

import pytest
from sqlalchemy import select

from app.auth.session import create_session
from app.auth.tokens import hash_token
from app.db.base import async_session_factory
from app.models.session import Session
from app.models.user import User


@pytest.mark.asyncio
async def test_session_row_stores_hash_not_raw_token() -> None:
    """create_session must store hash_token(raw) in DB, not the raw token itself."""
    async with async_session_factory() as db:
        user = User(
            email="hashtest@example.com",
            display_name="hashtest",
            password_hash=None,
            google_sub="google-sub-hashtest",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

        raw_token = await create_session(db, user.id, ttl_days=1)

        result = await db.execute(select(Session).where(Session.user_id == user.id))
        session_row = result.scalar_one()

    # The raw token must NOT be stored in the DB
    assert session_row.token_hash != raw_token
    # The stored value must match the expected hash of the raw token
    assert session_row.token_hash == hash_token(raw_token)


@pytest.mark.asyncio
async def test_session_lookup_by_raw_token_resolves_user() -> None:
    """get_session_user(raw_token) must still find the user after the hash refactor."""
    from app.auth.session import get_session_user

    async with async_session_factory() as db:
        user = User(
            email="hashlookup@example.com",
            display_name="hashlookup",
            password_hash=None,
            google_sub="google-sub-hashlookup",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

        raw_token = await create_session(db, user.id, ttl_days=1)
        found_user = await get_session_user(db, raw_token)

    assert found_user is not None
    assert found_user.id == user.id
