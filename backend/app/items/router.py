import logging

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.authz.dependencies import ListPermission, require_list_permission
from app.db.base import get_session
from app.items.schemas import ItemCreate, ItemOut, ItemUpdate
from app.models.item import Item

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/lists/{list_id}/items", tags=["items"])


@router.post("", response_model=ItemOut, status_code=status.HTTP_201_CREATED)
async def create_item(
    body: ItemCreate,
    perm: ListPermission = Depends(require_list_permission("create_item")),  # noqa: B008
    db: AsyncSession = Depends(get_session),  # noqa: B008
) -> Item:
    item = Item(list_id=perm.list_id, content=body.content, order=body.order)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    _log.info("item: created item_id=%s list_id=%s", item.id, perm.list_id)
    return item


@router.get("", response_model=list[ItemOut])
async def list_items(
    perm: ListPermission = Depends(require_list_permission("list_items")),  # noqa: B008
    db: AsyncSession = Depends(get_session),  # noqa: B008
) -> list[Item]:
    result = await db.execute(
        sa.select(Item).where(Item.list_id == perm.list_id).order_by(Item.order)
    )
    return list(result.scalars().all())


@router.patch("/{item_id}", response_model=ItemOut)
async def update_item(
    item_id: str,
    body: ItemUpdate,
    perm: ListPermission = Depends(require_list_permission("update_item")),  # noqa: B008
    db: AsyncSession = Depends(get_session),  # noqa: B008
) -> Item:
    item = await db.get(Item, item_id)
    if item is None or item.list_id != perm.list_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if body.content is not None:
        item.content = body.content
    if body.completed is not None:
        item.completed = body.completed
    if body.order is not None:
        item.order = body.order
    await db.commit()
    await db.refresh(item)
    _log.info("item: updated item_id=%s by user_id=%s", item.id, perm.user_id)
    return item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: str,
    perm: ListPermission = Depends(require_list_permission("delete_item")),  # noqa: B008
    db: AsyncSession = Depends(get_session),  # noqa: B008
) -> None:
    item = await db.get(Item, item_id)
    if item is None or item.list_id != perm.list_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    await db.delete(item)
    await db.commit()
    _log.info("item: deleted item_id=%s by user_id=%s", item_id, perm.user_id)
