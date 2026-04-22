"""Shared auth cookie helpers used by both router.py and oauth.py."""

import secrets

from fastapi import Response

from app.config import settings

SESSION_COOKIE_NAME = "session"
REFRESH_COOKIE_NAME = "refresh_token"
_CSRF_COOKIE_NAME = "csrf_token"


def set_auth_cookies(response: Response, session_token: str) -> None:
    """Set httpOnly session cookie + non-httpOnly CSRF double-submit cookie."""
    max_age = settings.session_ttl_days * 86400
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        httponly=True,
        samesite="lax",
        max_age=max_age,
        secure=settings.cookie_secure,
    )
    csrf_token = secrets.token_urlsafe(32)
    response.set_cookie(
        key=_CSRF_COOKIE_NAME,
        value=csrf_token,
        httponly=False,  # nosemgrep: fastapi-cookie-httponly-false  # noqa: E501
        samesite="lax",
        max_age=max_age,
        secure=settings.cookie_secure,
    )


def set_refresh_cookie(response: Response, refresh_token: str, *, ttl_days: int) -> None:
    """Set httpOnly refresh_token cookie (PRD-4 US-401)."""
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        samesite="lax",
        max_age=ttl_days * 86400,
        secure=settings.cookie_secure,
    )
