from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_auth
from app.auth.password import hash_password, verify_password
from app.auth.rate_limiter import check_login_rate_limit, record_failed_login, reset_failed_logins
from app.auth.schemas import LoginRequest, RegisterRequest, UserOut
from app.auth.session import (
    create_session,
    invalidate_session,
)
from app.config import settings
from app.db.base import get_session
from app.models.user import User

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

_GENERIC_AUTH_ERROR = "Invalid credentials"
_COOKIE_NAME = "session"


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=settings.session_ttl_days * 86400,
        secure=settings.cookie_secure,
    )


def _user_out(user: User) -> dict:  # type: ignore[type-arg]
    return {"id": str(user.id), "email": user.email, "display_name": user.display_name}


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    response: Response,
    db: AsyncSession = Depends(get_session),
) -> dict:  # type: ignore[type-arg]
    result = await db.execute(select(User).where(User.email == body.email))
    existing = result.scalar_one_or_none()

    if existing is not None:
        # Anti-enumeration: return same 201 structure with no user data (US-101).
        # BSD says: "if this email is available, your account has been created"
        return {"user": None, "message": "If this email is available, your account has been created."}

    display_name = body.email.split("@")[0]
    user = User(
        email=body.email,
        display_name=display_name,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = await create_session(db, user.id, ttl_days=settings.session_ttl_days)
    _set_session_cookie(response, token)
    return {"user": _user_out(user)}


@router.post("/login", status_code=status.HTTP_200_OK)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_session),
) -> dict:  # type: ignore[type-arg]
    check_login_rate_limit(request)

    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    # Anti-enumeration: check password even if user not found (constant-time path)
    if user is None or user.password_hash is None:
        # Still do a dummy hash to avoid timing side-channel on missing user
        hash_password("dummy-timing-equalization")
        record_failed_login(request)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_GENERIC_AUTH_ERROR,
        )

    if not verify_password(body.password, user.password_hash):
        record_failed_login(request)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_GENERIC_AUTH_ERROR,
        )

    reset_failed_logins(request)
    token = await create_session(db, user.id, ttl_days=settings.session_ttl_days)
    _set_session_cookie(response, token)
    return {"user": _user_out(user)}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_session),
) -> None:
    token = request.cookies.get(_COOKIE_NAME)
    if token:
        await invalidate_session(db, token)
    response.delete_cookie(_COOKIE_NAME)


@router.get("/session")
async def get_session_info(current_user: User = Depends(require_auth)) -> dict:  # type: ignore[type-arg]
    return {"user": _user_out(current_user)}
