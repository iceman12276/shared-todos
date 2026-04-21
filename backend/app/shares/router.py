import logging
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, status
from psycopg import errors as psy_errors
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.authz.dependencies import ListPermission, require_list_permission
from app.db.base import get_session
from app.models.share import Share
from app.models.user import User
from app.shares.schemas import ShareCreate, ShareOut, ShareUpdate

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/lists/{list_id}/shares", tags=["shares"])


@router.post("", response_model=ShareOut, status_code=status.HTTP_201_CREATED)
async def create_share(
    body: ShareCreate,
    perm: ListPermission = Depends(require_list_permission("share_list")),  # noqa: B008
    db: AsyncSession = Depends(get_session),  # noqa: B008
) -> Share:
    if body.user_id == perm.user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot share with yourself"
        )

    # Verify target user exists (OQ-1: return 404, not 422, to avoid user-registry enumeration)
    target = await db.get(User, body.user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    # Reject duplicate share
    existing = await db.execute(
        sa.select(Share).where(Share.list_id == perm.list_id, Share.user_id == body.user_id)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already has access")

    share = Share(list_id=perm.list_id, user_id=body.user_id, role=body.role)
    db.add(share)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if isinstance(exc.orig, psy_errors.UniqueViolation):
            # Duplicate-key race: concurrent request won the insert first
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="User already has access"
            ) from exc
        if isinstance(exc.orig, psy_errors.ForeignKeyViolation):
            # FK race: target user deleted between our SELECT and INSERT
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc
        # Unknown IntegrityError (CHECK, NOT NULL, or future schema drift) —
        # re-raise so the 500 handler sees it. Don't silently 404.
        raise
    await db.refresh(share)
    _log.info("share: created list_id=%s user_id=%s role=%s", perm.list_id, body.user_id, body.role)
    return share


@router.get("", response_model=list[ShareOut])
async def list_shares(
    perm: ListPermission = Depends(require_list_permission("share_list")),  # noqa: B008
    db: AsyncSession = Depends(get_session),  # noqa: B008
) -> list[Share]:
    result = await db.execute(sa.select(Share).where(Share.list_id == perm.list_id))
    return list(result.scalars().all())


@router.patch("/{target_user_id}", response_model=ShareOut)
async def change_role(
    target_user_id: UUID,
    body: ShareUpdate,
    perm: ListPermission = Depends(require_list_permission("change_collaborator_role")),  # noqa: B008
    db: AsyncSession = Depends(get_session),  # noqa: B008
) -> Share:
    result = await db.execute(
        sa.select(Share).where(Share.list_id == perm.list_id, Share.user_id == target_user_id)
    )
    share = result.scalar_one_or_none()
    if share is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    share.role = body.role
    await db.commit()
    await db.refresh(share)
    _log.info(
        "share: role changed list_id=%s user_id=%s new_role=%s by owner_id=%s",
        perm.list_id,
        target_user_id,
        body.role,
        perm.user_id,
    )
    return share


@router.delete("/{target_user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_share(
    target_user_id: UUID,
    perm: ListPermission = Depends(require_list_permission("revoke_share")),  # noqa: B008
    db: AsyncSession = Depends(get_session),  # noqa: B008
) -> None:
    result = await db.execute(
        sa.select(Share).where(Share.list_id == perm.list_id, Share.user_id == target_user_id)
    )
    share = result.scalar_one_or_none()
    if share is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    await db.delete(share)
    await db.commit()
    _log.info(
        "share: revoked list_id=%s user_id=%s by owner_id=%s",
        perm.list_id,
        target_user_id,
        perm.user_id,
    )
