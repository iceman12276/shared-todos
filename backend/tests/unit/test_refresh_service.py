"""Unit tests for refresh token service logic (PRD-4).

These test the service functions in isolation against real Postgres —
no mocks at the service layer.
"""

import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.refresh_service import (
    create_refresh_token,
    get_valid_refresh_token,
    revoke_family,
    rotate_refresh_token,
)
from app.auth.tokens import hash_token, verify_token_hash
from app.models.refresh_token import RefreshToken
from app.models.user import User


async def _make_user(db: AsyncSession, email: str = "rt@example.com") -> User:
    u = User(email=email, display_name="rt", google_sub=f"sub-{email}")
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest.mark.anyio
async def test_create_refresh_token_stores_hash(db_session: AsyncSession) -> None:
    """create_refresh_token must return a raw token and store only the hash."""
    user = await _make_user(db_session)
    family_id = uuid4()
    raw, rt = await create_refresh_token(
        db_session, user_id=user.id, family_id=family_id, parent_id=None, ttl_days=30
    )
    assert len(raw) > 20
    assert verify_token_hash(raw, rt.token_hash)
    assert rt.revoked_at is None
    assert rt.family_id == family_id
    assert rt.parent_token_id is None


@pytest.mark.anyio
async def test_create_refresh_token_raw_not_stored(db_session: AsyncSession) -> None:
    """The raw refresh token must not appear in any stored column."""
    user = await _make_user(db_session)
    raw, rt = await create_refresh_token(
        db_session, user_id=user.id, family_id=uuid4(), parent_id=None, ttl_days=30
    )
    # Raw token must differ from the stored hash
    assert raw != rt.token_hash


@pytest.mark.anyio
async def test_get_valid_refresh_token_returns_active(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    raw, rt = await create_refresh_token(
        db_session, user_id=user.id, family_id=uuid4(), parent_id=None, ttl_days=30
    )
    found = await get_valid_refresh_token(db_session, raw)
    assert found is not None
    assert found.id == rt.id


@pytest.mark.anyio
async def test_get_valid_refresh_token_returns_none_for_unknown(
    db_session: AsyncSession,
) -> None:
    found = await get_valid_refresh_token(db_session, secrets.token_urlsafe(32))
    assert found is None


@pytest.mark.anyio
async def test_get_valid_refresh_token_returns_none_for_expired(
    db_session: AsyncSession,
) -> None:
    user = await _make_user(db_session)
    family_id = uuid4()
    raw = secrets.token_urlsafe(32)
    rt = RefreshToken(
        family_id=family_id,
        user_id=user.id,
        token_hash=hash_token(raw),
        issued_at=datetime.now(UTC) - timedelta(days=31),
        expires_at=datetime.now(UTC) - timedelta(seconds=1),  # already expired
    )
    db_session.add(rt)
    await db_session.commit()

    found = await get_valid_refresh_token(db_session, raw)
    assert found is None


@pytest.mark.anyio
async def test_get_valid_refresh_token_returns_none_for_revoked(
    db_session: AsyncSession,
) -> None:
    user = await _make_user(db_session)
    raw, rt = await create_refresh_token(
        db_session, user_id=user.id, family_id=uuid4(), parent_id=None, ttl_days=30
    )
    rt.revoked_at = datetime.now(UTC)
    await db_session.commit()

    found = await get_valid_refresh_token(db_session, raw)
    assert found is None


@pytest.mark.anyio
async def test_rotate_refresh_token_revokes_old_issues_new(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    family_id = uuid4()
    raw_old, rt_old = await create_refresh_token(
        db_session, user_id=user.id, family_id=family_id, parent_id=None, ttl_days=30
    )

    new_raw, new_rt = await rotate_refresh_token(db_session, rt_old, ttl_days=30)

    # Old token now revoked
    await db_session.refresh(rt_old)
    assert rt_old.revoked_at is not None
    # New token is in same family, points to old
    assert new_rt.family_id == family_id
    assert new_rt.parent_token_id == rt_old.id
    # New token is valid
    found = await get_valid_refresh_token(db_session, new_raw)
    assert found is not None


@pytest.mark.anyio
async def test_rotate_refresh_token_old_no_longer_valid(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    raw_old, rt_old = await create_refresh_token(
        db_session, user_id=user.id, family_id=uuid4(), parent_id=None, ttl_days=30
    )
    await rotate_refresh_token(db_session, rt_old, ttl_days=30)

    found = await get_valid_refresh_token(db_session, raw_old)
    assert found is None


@pytest.mark.anyio
async def test_revoke_family_revokes_all_members(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    family_id = uuid4()
    raw1, rt1 = await create_refresh_token(
        db_session, user_id=user.id, family_id=family_id, parent_id=None, ttl_days=30
    )
    # Simulate a rotated chain: rt2 is the "current" active token
    _, rt2 = await rotate_refresh_token(db_session, rt1, ttl_days=30)
    # Grab the raw for rt2 by creating a fresh token in the same family
    raw_root, rt_root = await create_refresh_token(
        db_session, user_id=user.id, family_id=family_id, parent_id=None, ttl_days=30
    )

    await revoke_family(db_session, family_id)

    # All tokens in this family must be revoked
    await db_session.refresh(rt1)
    await db_session.refresh(rt2)
    await db_session.refresh(rt_root)
    assert rt1.revoked_at is not None
    assert rt2.revoked_at is not None
    assert rt_root.revoked_at is not None


@pytest.mark.anyio
async def test_revoke_family_does_not_affect_other_family(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    family_a = uuid4()
    family_b = uuid4()
    _, rt_a = await create_refresh_token(
        db_session, user_id=user.id, family_id=family_a, parent_id=None, ttl_days=30
    )
    raw_b, rt_b = await create_refresh_token(
        db_session, user_id=user.id, family_id=family_b, parent_id=None, ttl_days=30
    )

    await revoke_family(db_session, family_a)

    await db_session.refresh(rt_b)
    assert rt_b.revoked_at is None
    found = await get_valid_refresh_token(db_session, raw_b)
    assert found is not None
