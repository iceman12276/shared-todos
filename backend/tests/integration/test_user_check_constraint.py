"""Integration test: User CheckConstraint rejects rows with no auth method (MEDIUM-11)."""

import pytest
from sqlalchemy.exc import IntegrityError

from app.db.base import async_session_factory
from app.models.user import User


@pytest.mark.asyncio
async def test_user_requires_password_hash_or_google_sub() -> None:
    """A User with neither password_hash nor google_sub must be rejected by DB."""
    async with async_session_factory() as db:
        user = User(
            email="noauth@example.com",
            display_name="noauth",
            password_hash=None,
            google_sub=None,
        )
        db.add(user)
        with pytest.raises(IntegrityError):
            await db.flush()
        await db.rollback()


@pytest.mark.asyncio
async def test_user_with_password_hash_only_is_accepted() -> None:
    """A User with only password_hash must be accepted."""
    async with async_session_factory() as db:
        user = User(
            email="pwonly@example.com",
            display_name="pwonly",
            password_hash="$argon2id$v=19$m=65536,t=3,p=1$fakehash",  # noqa: S106
            google_sub=None,
        )
        db.add(user)
        await db.commit()


@pytest.mark.asyncio
async def test_user_with_google_sub_only_is_accepted() -> None:
    """A User with only google_sub must be accepted (OAuth-only user)."""
    async with async_session_factory() as db:
        user = User(
            email="oauthonly@example.com",
            display_name="oauthonly",
            password_hash=None,
            google_sub="google-sub-12345",
        )
        db.add(user)
        await db.commit()
