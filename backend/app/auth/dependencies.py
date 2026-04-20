from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.session import get_session_user
from app.db.base import get_session
from app.models.user import User


async def require_auth(
    session: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_session),
) -> User:
    """FastAPI dependency that returns the current authenticated User.

    Returns 401 for unauthenticated requests. For list/item resource endpoints
    (PR-3+), callers that check row-level permissions should return 404 when
    the caller lacks read access — NOT 403 — per OQ-1 (stranger → 404, never 403).
    This dependency only handles the auth layer (is a valid session present?);
    the resource authorization layer is a separate concern in PR-3+.
    """
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    user = await get_session_user(db, session)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user
