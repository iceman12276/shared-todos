"""FastAPI dependencies for list-level authorization.

OQ-1 (pinned): stranger → 404 on every verb, never 403. Insufficient
access emits 404 regardless of whether the list exists, to prevent
list-existence enumeration.
"""

import logging
from dataclasses import dataclass
from uuid import UUID

import sqlalchemy as sa
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_auth
from app.authz.permissions import Role, can_perform, effective_role
from app.db.base import get_session
from app.models.list_ import List
from app.models.share import Share
from app.models.user import User

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ListPermission:
    list_id: UUID
    user_id: UUID
    role: Role


def require_list_permission(
    required_action: str,
) -> "type[ListPermission]":
    """Return a FastAPI dependency that resolves the caller's role on a list.

    If the caller lacks the required permission → HTTPException(404).
    404 is emitted for both strangers and non-existent lists (OQ-1 anti-enum).

    Usage::

        @router.get("/lists/{list_id}")
        async def get_list(
            perm: ListPermission = Depends(require_list_permission("read_list")),
        ) -> ...:
            ...
    """

    async def _dependency(
        list_id: UUID,
        user: User = Depends(require_auth),  # noqa: B008
        db: AsyncSession = Depends(get_session),  # noqa: B008
    ) -> ListPermission:
        # Resolve ownership and share in one query each, not two round-trips.
        # We look up the list and the share independently so that a missing
        # list and a present-but-inaccessible list are indistinguishable to
        # the caller (OQ-1).

        # Check if caller is the owner
        owner_result = await db.execute(
            sa.select(List.id).where(List.id == list_id, List.owner_id == user.id)
        )
        is_owner = owner_result.scalar_one_or_none() is not None

        # Check if caller has a share row
        share_result = await db.execute(
            sa.select(Share.role).where(
                Share.list_id == list_id, Share.user_id == user.id
            )
        )
        share_role = share_result.scalar_one_or_none()

        role = effective_role(is_owner=is_owner, share_role=share_role)

        if role is None or not can_perform(role, required_action):
            _log.warning(
                "authz: denied list_id=%s user_id=%s role=%r action=%r",
                list_id,
                user.id,
                role,
                required_action,
            )
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

        _log.info(
            "authz: granted list_id=%s user_id=%s role=%r action=%r",
            list_id,
            user.id,
            role,
            required_action,
        )
        return ListPermission(list_id=list_id, user_id=user.id, role=role)

    return _dependency  # type: ignore[return-value]
