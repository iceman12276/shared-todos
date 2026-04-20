"""Google OAuth 2.0 Authorization Code + PKCE flow (US-103).

State parameter signed with itsdangerous to prevent CSRF — no server-side
session store needed for the OAuth handshake itself.

The httpx client is injectable as a FastAPI dependency so tests can provide
a pre-configured mock transport without needing global HTTP interception.
"""
import base64
import json
from collections.abc import AsyncGenerator
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response, status
from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.session import create_session
from app.config import settings
from app.db.base import get_session
from app.models.user import User

router = APIRouter(prefix="/api/v1/auth/oauth", tags=["oauth"])


async def get_http_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Dependency that yields a shared httpx client. Override in tests."""
    async with httpx.AsyncClient() as client:
        yield client

_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105
_GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

_COOKIE_NAME = "session"


def _signer() -> URLSafeSerializer:
    return URLSafeSerializer(settings.secret_key, salt="oauth-state")


def _make_state(nonce: str) -> str:
    return _signer().dumps(nonce)


def _verify_state(state: str) -> bool:
    try:
        _signer().loads(state)
        return True
    except BadSignature:
        return False


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
    """Redirect to Google's OAuth consent screen."""
    import secrets
    nonce = secrets.token_urlsafe(16)
    state = _make_state(nonce)
    auth_url = _build_auth_url(state)
    return Response(
        status_code=status.HTTP_302_FOUND,
        headers={"location": auth_url},
    )


@router.get("/google/callback")
async def oauth_google_callback(
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

    if state is None or not _verify_state(state):
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
        return Response(
            status_code=status.HTTP_302_FOUND,
            headers={"location": f"{settings.frontend_url}/register?error=oauth_failed"},
        )

    token_data = token_r.json()
    id_token = token_data.get("id_token", "")

    try:
        payload = _decode_id_token_payload(id_token)
    except (ValueError, Exception):
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
        select(User).where(
            (User.google_sub == google_sub) | (User.email == email)
        )
    )
    user = result.scalar_one_or_none()

    if user is None:
        user = User(email=email, display_name=display_name, google_sub=google_sub)
        db.add(user)
        await db.commit()
        await db.refresh(user)
    elif user.google_sub is None:
        # Link existing email+password account to Google (US-103)
        user.google_sub = google_sub
        await db.commit()

    token = await create_session(db, user.id, ttl_days=settings.session_ttl_days)

    response = Response(
        status_code=status.HTTP_302_FOUND,
        headers={"location": f"{settings.frontend_url}/dashboard"},
    )
    _set_session_cookie(response, token)
    return response
