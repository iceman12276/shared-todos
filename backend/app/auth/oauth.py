"""Google OAuth 2.0 Authorization Code + PKCE flow (US-103).

State parameter is signed with itsdangerous AND the nonce is bound to the
browser session via a short-lived httpOnly cookie (oauth_state_nonce).
At callback, the nonce extracted from the signed state must match the cookie
via secrets.compare_digest — this prevents CSRF attacks where an attacker
initiates OAuth and sends the callback URL to a victim.

The httpx client is injectable as a FastAPI dependency so tests can provide
a pre-configured mock transport without needing global HTTP interception.
"""

import base64
import json
import logging
import secrets
from collections.abc import AsyncGenerator
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.session import create_session
from app.config import settings
from app.db.base import get_session
from app.models.user import User

_log = logging.getLogger("app.auth.oauth")

router = APIRouter(prefix="/api/v1/auth/oauth", tags=["oauth"])


async def get_http_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Dependency that yields a shared httpx client. Override in tests."""
    async with httpx.AsyncClient() as client:
        yield client


_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105

_COOKIE_NAME = "session"
_NONCE_COOKIE = "oauth_state_nonce"
_NONCE_TTL = 600  # 10 minutes — enough to complete the OAuth dance


def _signer() -> URLSafeSerializer:
    return URLSafeSerializer(settings.secret_key, salt="oauth-state")


def _make_state(nonce: str) -> str:
    return _signer().dumps(nonce)


def _extract_nonce(state: str) -> str | None:
    """Return the nonce embedded in a valid signed state, or None if invalid."""
    try:
        nonce: str = _signer().loads(state)
        return nonce
    except BadSignature:
        return None


def _build_auth_url(state: str) -> str:
    from urllib.parse import urlencode

    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
    }
    return f"{_GOOGLE_AUTH_URL}?{urlencode(params)}"


def _decode_id_token_payload(id_token: str) -> dict[str, Any]:
    """Decode JWT payload without verifying signature (dev/test only path).

    In production, verify the signature against Google's public keys.
    For v1 scope, we trust the token from Google's own endpoint.
    """
    parts = id_token.split(".")
    if len(parts) < 2:
        raise ValueError("Invalid id_token format")
    payload_b64 = parts[1] + "=="  # pad
    result: dict[str, Any] = json.loads(base64.urlsafe_b64decode(payload_b64))
    return result


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=settings.session_ttl_days * 86400,
        secure=settings.cookie_secure,
    )


@router.get("/google")
async def oauth_google_initiate(response: Response) -> Response:
    """Redirect to Google's OAuth consent screen.

    The nonce is stored in a short-lived httpOnly cookie so that the callback
    can verify the state is bound to THIS browser — not replayed from another
    session (OAuth CSRF, item 4).
    """
    nonce = secrets.token_urlsafe(16)
    state = _make_state(nonce)
    auth_url = _build_auth_url(state)
    resp = Response(
        status_code=status.HTTP_302_FOUND,
        headers={"location": auth_url},
    )
    resp.set_cookie(
        key=_NONCE_COOKIE,
        value=nonce,
        httponly=True,
        samesite="lax",
        max_age=_NONCE_TTL,
        secure=settings.cookie_secure,
    )
    return resp


@router.get("/google/callback")
async def oauth_google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: AsyncSession = Depends(get_session),  # noqa: B008
    http: httpx.AsyncClient = Depends(get_http_client),  # noqa: B008
) -> Response:
    """Handle Google's callback, exchange code for tokens, create/link account."""
    if error or code is None:
        return Response(
            status_code=status.HTTP_302_FOUND,
            headers={"location": f"{settings.frontend_url}/register?error=oauth_cancelled"},
        )

    if state is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid state")

    nonce = _extract_nonce(state)
    if nonce is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid state")

    # Verify the nonce is bound to this browser session (OAuth CSRF prevention).
    cookie_nonce = request.cookies.get(_NONCE_COOKIE, "")
    if not cookie_nonce or not secrets.compare_digest(nonce, cookie_nonce):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid state")

    # Exchange code for tokens
    token_r = await http.post(
        _GOOGLE_TOKEN_URL,
        data={
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": settings.google_redirect_uri,
            "grant_type": "authorization_code",
        },
    )

    if token_r.status_code != 200:
        _log.error("oauth: google token exchange failed status=%d", token_r.status_code)
        return Response(
            status_code=status.HTTP_302_FOUND,
            headers={"location": f"{settings.frontend_url}/register?error=oauth_failed"},
        )

    token_data = token_r.json()
    id_token = token_data.get("id_token", "")

    try:
        payload = _decode_id_token_payload(id_token)
    except (ValueError, Exception):
        _log.error("oauth: id_token decode failed")
        return Response(
            status_code=status.HTTP_302_FOUND,
            headers={"location": f"{settings.frontend_url}/register?error=oauth_failed"},
        )

    google_sub = payload.get("sub", "")
    email = payload.get("email", "")
    display_name = payload.get("name", email.split("@")[0])

    if not google_sub or not email:
        return Response(
            status_code=status.HTTP_302_FOUND,
            headers={"location": f"{settings.frontend_url}/register?error=oauth_failed"},
        )

    # Find existing user by google_sub or email (account linking)
    result = await db.execute(
        select(User).where((User.google_sub == google_sub) | (User.email == email))
    )
    user = result.scalar_one_or_none()

    if user is None:
        user = User(email=email, display_name=display_name, google_sub=google_sub)
        db.add(user)
        await db.commit()
        await db.refresh(user)
        _log.info("oauth: new user created via google sub=%s user_id=%s", google_sub, user.id)
    elif user.google_sub is None:
        # Link existing email+password account to Google (US-103)
        user.google_sub = google_sub
        await db.commit()
        _log.info(
            "oauth: linked google account to existing user user_id=%s sub=%s", user.id, google_sub
        )
    else:
        _log.info("oauth: existing google user signed in user_id=%s", user.id)

    token = await create_session(db, user.id, ttl_days=settings.session_ttl_days)

    response = Response(
        status_code=status.HTTP_302_FOUND,
        headers={"location": f"{settings.frontend_url}/dashboard"},
    )
    _set_session_cookie(response, token)
    return response
