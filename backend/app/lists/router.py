import logging

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_auth
from app.authz.dependencies import ListPermission, require_list_permission
from app.db.base import get_session
from app.lists.schemas import ListCreate, ListOut, ListUpdate
from app.models.list_ import List
from app.models.share import Share
from app.models.user import User

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/lists", tags=["lists"])


@router.post("", response_model=ListOut, status_code=status.HTTP_201_CREATED)
async def create_list(
    body: ListCreate,
    user: User = Depends(require_auth),  # noqa: B008
    db: AsyncSession = Depends(get_session),  # noqa: B008
) -> List:
    lst = List(owner_id=user.id, name=body.name)
    db.add(lst)
    await db.commit()
    await db.refresh(lst)
    _log.info("list: created list_id=%s owner_id=%s", lst.id, user.id)
    return lst


@router.get("", response_model=list[ListOut])
async def list_lists(
    user: User = Depends(require_auth),  # noqa: B008
    db: AsyncSession = Depends(get_session),  # noqa: B008
) -> list[List]:
    owned = await db.execute(sa.select(List).where(List.owner_id == user.id))
    owned_lists = list(owned.scalars().all())

    shared_result = await db.execute(
        sa.select(List)
        .join(Share, Share.list_id == List.id)
        .where(Share.user_id == user.id)
    )
    shared_lists = list(shared_result.scalars().all())

    seen: set[object] = set()
    result: list[List] = []
    for lst in owned_lists + shared_lists:
        if lst.id not in seen:
            seen.add(lst.id)
            result.append(lst)
    return result


@router.get("/{list_id}", response_model=ListOut)
async def get_list(
    perm: ListPermission = Depends(require_list_permission("read_list")),  # noqa: B008
    db: AsyncSession = Depends(get_session),  # noqa: B008
) -> List:
    lst = await db.get(List, perm.list_id)
    if lst is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return lst


@router.patch("/{list_id}", response_model=ListOut)
async def rename_list(
    body: ListUpdate,
    perm: ListPermission = Depends(require_list_permission("rename_list")),  # noqa: B008
    db: AsyncSession = Depends(get_session),  # noqa: B008
) -> List:
    lst = await db.get(List, perm.list_id)
    if lst is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    lst.name = body.name
    await db.commit()
    await db.refresh(lst)
    _log.info("list: renamed list_id=%s by user_id=%s", lst.id, perm.user_id)
    return lst


@router.delete("/{list_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_list(
    perm: ListPermission = Depends(require_list_permission("delete_list")),  # noqa: B008
    db: AsyncSession = Depends(get_session),  # noqa: B008
) -> None:
    lst = await db.get(List, perm.list_id)
    if lst is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    await db.delete(lst)
    await db.commit()
    _log.info("list: deleted list_id=%s by user_id=%s", perm.list_id, perm.user_id)
