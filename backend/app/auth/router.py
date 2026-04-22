import logging
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete as sa_delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.cookies import REFRESH_COOKIE_NAME, SESSION_COOKIE_NAME, set_auth_cookies, set_refresh_cookie
from app.auth.dependencies import require_auth
from app.auth.email import send_password_reset_email
from app.auth.password import hash_password, make_dummy_hash, verify_password
from app.auth.rate_limiter import check_login_rate_limit, record_failed_login, reset_failed_logins
from app.auth.refresh_service import (
    create_refresh_token,
    get_revoked_refresh_token,
    get_valid_refresh_token,
    revoke_family,
    rotate_refresh_token,
)
from app.auth.schemas import (
    LoginRequest,
    PasswordResetCompleteBody,
    PasswordResetRequestBody,
    RegisterRequest,
)
from app.auth.session import (
    create_session,
    invalidate_all_user_sessions,
    invalidate_sessions_by_family,
)
from app.auth.tokens import generate_reset_token, hash_token
from app.config import settings
from app.db.base import get_session
from app.models.password_reset_token import PasswordResetToken
from app.models.session import Session
from app.models.user import User

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

_log = logging.getLogger("app.auth")

_GENERIC_AUTH_ERROR = "Invalid credentials"
_SESSION_EXPIRED_MSG = "Session expired. Please log in again."


def _user_out(user: User) -> dict:  # type: ignore[type-arg]
    return {"id": str(user.id), "email": user.email, "display_name": user.display_name}


async def _issue_credentials(
    db: AsyncSession, response: Response, user_id: UUID
) -> None:
    """Issue session + refresh token in one atomic commit. Sets both cookies.

    Both credentials share a new family_id. Session is staged without
    commit; refresh token is flushed; single commit persists both.
    Prevents session-without-refresh-token inconsistency.
    """
    family_id = uuid4()
    session_token = await create_session(
        db, user_id, ttl_days=settings.session_ttl_days, family_id=family_id, commit=False
    )
    raw_refresh, _ = await create_refresh_token(
        db,
        user_id=user_id,
        family_id=family_id,
        parent_id=None,
        ttl_days=settings.refresh_token_ttl_days,
    )
    await db.commit()
    set_auth_cookies(response, session_token)
    set_refresh_cookie(response, raw_refresh, ttl_days=settings.refresh_token_ttl_days)


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
        # success branch (US-101). Emit dummy session + refresh cookies so an
        # attacker cannot distinguish "email exists" from "email free" via
        # header presence or count.
        set_auth_cookies(response, secrets.token_urlsafe(32))
        set_refresh_cookie(
            response, secrets.token_urlsafe(32), ttl_days=settings.refresh_token_ttl_days
        )
        _log.info("register: duplicate email attempt (anti-enum response sent)")
        msg = "If this email is available, your account has been created."
        return {"user": None, "message": msg}

    display_name = body.email.split("@")[0]
    user = User(
        email=body.email,
        display_name=display_name,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    await _issue_credentials(db, response, user.id)
    _log.info("register: new user created user_id=%s", user.id)
    return {"user": _user_out(user), "message": "Account created successfully."}


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
        _log.warning("login: failed attempt for unknown/oauth-only email")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_GENERIC_AUTH_ERROR,
        )

    if not verify_password(body.password, user.password_hash):
        record_failed_login(request)
        _log.warning("login: wrong password for user_id=%s", user.id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_GENERIC_AUTH_ERROR,
        )

    reset_failed_logins(request)
    await _issue_credentials(db, response, user.id)
    _log.info("login: success user_id=%s", user.id)
    return {"user": _user_out(user)}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_session),  # noqa: B008
) -> None:
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if session_token:
        session_result = await db.execute(
            select(Session).where(Session.token_hash == hash_token(session_token))
        )
        session_obj = session_result.scalar_one_or_none()
        if session_obj is not None and session_obj.family_id is not None:
            # Revoke family (refresh tokens) + all associated sessions atomically
            await revoke_family(db, session_obj.family_id)
            await invalidate_sessions_by_family(db, session_obj.family_id, commit=False)
            await db.commit()
            _log.info("logout: family revoked family_id=%s", session_obj.family_id)
        else:
            # Pre-PR-4 session (no family) — delete the session record directly
            await db.execute(
                sa_delete(Session).where(Session.token_hash == hash_token(session_token))
            )
            await db.commit()
            _log.info("logout: pre-family session invalidated")
    else:
        _log.info("logout: no session cookie present")

    response.delete_cookie(SESSION_COOKIE_NAME)
    response.delete_cookie(REFRESH_COOKIE_NAME)


@router.post("/refresh", status_code=status.HTTP_200_OK)
async def refresh_token_endpoint(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict:  # type: ignore[type-arg]
    """Rotate refresh token and reissue session (PRD-4 US-402).

    All four 401 paths return identical HTTP status + body (OQ-4a / US-405).
    """
    raw = request.cookies.get(REFRESH_COOKIE_NAME)

    if not raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=_SESSION_EXPIRED_MSG
        )

    # Reuse detection: token exists in DB but is already revoked (I2)
    revoked_rt = await get_revoked_refresh_token(db, raw)
    if revoked_rt is not None:
        # Atomic: revoke entire family + all associated sessions in one transaction
        await revoke_family(db, revoked_rt.family_id)
        await invalidate_sessions_by_family(db, revoked_rt.family_id, commit=False)
        await db.commit()
        _log.warning(
            "refresh: reuse detected, family revoked family_id=%s", revoked_rt.family_id
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=_SESSION_EXPIRED_MSG
        )

    valid_rt = await get_valid_refresh_token(db, raw)
    if valid_rt is None:
        # No match, expired, or unknown — same 401 (US-405)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=_SESSION_EXPIRED_MSG
        )

    # Rotate: revoke old token, issue new refresh token + new session atomically (I1, I2)
    new_raw_refresh, _ = await rotate_refresh_token(
        db, valid_rt, ttl_days=settings.refresh_token_ttl_days
    )
    new_session_token = await create_session(
        db,
        valid_rt.user_id,
        ttl_days=settings.session_ttl_days,
        family_id=valid_rt.family_id,
        commit=False,
    )
    await db.commit()

    set_auth_cookies(response, new_session_token)
    set_refresh_cookie(response, new_raw_refresh, ttl_days=settings.refresh_token_ttl_days)
    _log.info("refresh: rotated family_id=%s user_id=%s", valid_rt.family_id, valid_rt.user_id)
    return {}


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
            _log.info(
                "password-reset request: google-only account, no email sent user_id=%s", user.id
            )
        else:
            token = generate_reset_token()
            prt = PasswordResetToken(
                user_id=user.id,
                token_hash=hash_token(token),
                expires_at=datetime.now(UTC) + timedelta(hours=_RESET_TTL_HOURS),
            )
            db.add(prt)
            await db.commit()
            try:
                await send_password_reset_email(body.email, token)
                _log.info("password-reset request: email sent user_id=%s", user.id)
            except Exception as exc:  # best-effort: don't leak send failures
                _log.error(
                    "password-reset request: SMTP send failed user_id=%s error=%r", user.id, exc
                )

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

    user_result = await db.execute(select(User).where(User.id == prt.user_id))
    user = user_result.scalar_one()

    # Single transaction: mark token used + update password + invalidate sessions.
    # All three mutations commit atomically — a crash at any point leaves the
    # user's password unchanged and the reset token re-usable (preferred over
    # partial state). US-107 requires session invalidation as part of the
    # successful-reset guarantee.
    prt.used_at = now
    user.password_hash = hash_password(body.new_password)
    await invalidate_all_user_sessions(db, user.id, commit=False)
    await db.commit()
    _log.info(
        "password-reset complete: password updated + all sessions invalidated user_id=%s", user.id
    )

    return {"message": "Password updated. All sessions have been invalidated."}
