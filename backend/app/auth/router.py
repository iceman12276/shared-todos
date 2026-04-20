import contextlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_auth
from app.auth.email import send_password_reset_email
from app.auth.password import hash_password, make_dummy_hash, verify_password
from app.auth.rate_limiter import check_login_rate_limit, record_failed_login, reset_failed_logins
from app.auth.schemas import (
    LoginRequest,
    PasswordResetCompleteBody,
    PasswordResetRequestBody,
    RegisterRequest,
)
from app.auth.session import (
    create_session,
    invalidate_all_user_sessions,
    invalidate_session,
)
from app.auth.tokens import generate_reset_token, hash_token
from app.config import settings
from app.db.base import get_session
from app.models.password_reset_token import PasswordResetToken
from app.models.user import User

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

_GENERIC_AUTH_ERROR = "Invalid credentials"
_COOKIE_NAME = "session"
_CSRF_COOKIE = "csrf_token"


def _set_auth_cookies(response: Response, session_token: str) -> None:
    """Set httpOnly session cookie + non-httpOnly CSRF double-submit cookie."""
    response.set_cookie(
        key=_COOKIE_NAME,
        value=session_token,
        httponly=True,
        samesite="lax",
        max_age=settings.session_ttl_days * 86400,
        secure=settings.cookie_secure,
    )
    csrf_token = secrets.token_urlsafe(32)
    response.set_cookie(
        key=_CSRF_COOKIE,
        value=csrf_token,
        httponly=False,  # nosemgrep: fastapi-cookie-httponly-false  # noqa: E501
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
    db: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict:  # type: ignore[type-arg]
    result = await db.execute(select(User).where(User.email == body.email))
    existing = result.scalar_one_or_none()

    if existing is not None:
        # Anti-enumeration: same 201 body AND same Set-Cookie headers as the
        # success branch (US-101). Without matching cookies an attacker can
        # distinguish "email exists" from "email free" via response headers.
        _set_auth_cookies(response, secrets.token_urlsafe(32))
        msg = "If this email is available, your account has been created."
        return {"user": None, "message": msg}

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
    _set_auth_cookies(response, token)
    return {"user": _user_out(user)}


@router.post("/login", status_code=status.HTTP_200_OK)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict:  # type: ignore[type-arg]
    check_login_rate_limit(request)

    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    # Anti-enumeration: verify against a precomputed dummy hash when user not
    # found — same argon2 verify() operation as the wrong-password branch,
    # guaranteeing timing equivalence (hash() and verify() have different paths).
    if user is None or user.password_hash is None:
        verify_password(body.password, make_dummy_hash())
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
    _set_auth_cookies(response, token)
    return {"user": _user_out(user)}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_session),  # noqa: B008
) -> None:
    token = request.cookies.get(_COOKIE_NAME)
    if token:
        await invalidate_session(db, token)
    response.delete_cookie(_COOKIE_NAME)


@router.get("/session")
async def get_session_info(current_user: User = Depends(require_auth)) -> dict:  # type: ignore[type-arg]  # noqa: B008
    return {"user": _user_out(current_user)}


_RESET_TTL_HOURS = 1


@router.post("/password-reset/request")
async def password_reset_request(
    body: PasswordResetRequestBody,
    db: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict:  # type: ignore[type-arg]
    """Request a password reset link. Always returns 200 — anti-enumeration (US-106)."""
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if user is not None:
        if user.password_hash is None:
            # Google-only account: no reset email, but still opaque response
            pass
        else:
            token = generate_reset_token()
            prt = PasswordResetToken(
                user_id=user.id,
                token_hash=hash_token(token),
                expires_at=datetime.now(UTC) + timedelta(hours=_RESET_TTL_HOURS),
            )
            db.add(prt)
            await db.commit()
            with contextlib.suppress(Exception):  # best-effort: don't leak send failures
                await send_password_reset_email(body.email, token)

    return {"message": "If an account exists for this email, a reset link has been sent."}


@router.get("/password-reset/validate")
async def password_reset_validate(
    token: str,
    db: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict:  # type: ignore[type-arg]
    """Validate a reset token without consuming it (US-107 — used on page load)."""
    token_hash = hash_token(token)
    now = datetime.now(UTC)
    result = await db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.expires_at > now,
            PasswordResetToken.used_at.is_(None),
        )
    )
    prt = result.scalar_one_or_none()
    if prt is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid")
    return {"valid": True}


@router.post("/password-reset/complete")
async def password_reset_complete(
    body: PasswordResetCompleteBody,
    db: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict:  # type: ignore[type-arg]
    """Complete a password reset. Invalidates ALL existing sessions (US-107)."""
    token_hash = hash_token(body.token)
    now = datetime.now(UTC)
    result = await db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.expires_at > now,
            PasswordResetToken.used_at.is_(None),
        )
    )
    prt = result.scalar_one_or_none()
    if prt is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_or_used")

    # Mark token as used (single-use)
    prt.used_at = now
    await db.commit()

    # Update password
    user_result = await db.execute(select(User).where(User.id == prt.user_id))
    user = user_result.scalar_one()
    user.password_hash = hash_password(body.new_password)
    await db.commit()

    # Invalidate ALL sessions for this user (US-107 hard requirement)
    await invalidate_all_user_sessions(db, user.id)

    return {"message": "Password updated. All sessions have been invalidated."}
