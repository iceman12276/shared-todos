"""Refresh token service — create, look up, rotate, and revoke token families.

All write operations stage changes on the session but do NOT commit.
The caller is responsible for a single commit to keep multi-operation
paths atomic (PRD-4 Invariant 2: detection and revocation in one transaction).
"""

import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.tokens import hash_token
from app.models.refresh_token import RefreshToken


async def create_refresh_token(
    db: AsyncSession,
    *,
    user_id: UUID,
    family_id: UUID,
    parent_id: UUID | None,
    ttl_days: int,
) -> tuple[str, RefreshToken]:
    """Issue a new refresh token in the given family. Returns (raw_token, model)."""
    raw = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    rt = RefreshToken(
        family_id=family_id,
        user_id=user_id,
        token_hash=hash_token(raw),
        parent_token_id=parent_id,
        issued_at=now,
        expires_at=now + timedelta(days=ttl_days),
    )
    db.add(rt)
    await db.flush()  # populate rt.id without committing
    return raw, rt


async def get_valid_refresh_token(db: AsyncSession, raw_token: str) -> RefreshToken | None:
    """Return the RefreshToken for raw_token if it is active and unexpired, else None."""
    token_hash = hash_token(raw_token)
    now = datetime.now(UTC)
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > now,
        )
    )
    return result.scalar_one_or_none()


async def get_revoked_refresh_token(db: AsyncSession, raw_token: str) -> RefreshToken | None:
    """Return a RefreshToken that has been revoked (reuse-detection path)."""
    token_hash = hash_token(raw_token)
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked_at.isnot(None),
        )
    )
    return result.scalar_one_or_none()


async def rotate_refresh_token(
    db: AsyncSession, old_rt: RefreshToken, *, ttl_days: int
) -> tuple[str, RefreshToken]:
    """Revoke old_rt and issue a new token in the same family.

    Stages both writes without committing — caller commits once (atomicity).
    """
    old_rt.revoked_at = datetime.now(UTC)
    new_raw, new_rt = await create_refresh_token(
        db,
        user_id=old_rt.user_id,
        family_id=old_rt.family_id,
        parent_id=old_rt.id,
        ttl_days=ttl_days,
    )
    return new_raw, new_rt


async def revoke_family(db: AsyncSession, family_id: UUID) -> None:
    """Revoke every token in the family (logout or reuse-detection path).

    Stages the bulk UPDATE without committing — caller commits once.
    """
    now = datetime.now(UTC)
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )
