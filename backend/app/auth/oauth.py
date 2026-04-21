"""Google OAuth 2.0 Authorization Code flow (US-103).

State parameter is signed with itsdangerous AND the nonce is bound to the
browser session via a short-lived httpOnly cookie (oauth_state_nonce).
At callback, the nonce extracted from the signed state must match the cookie
via secrets.compare_digest. This prevents the OAuth login-CSRF class of attack
where an attacker initiates the flow, then tricks the victim's browser into
completing the attacker's callback URL — binding the victim's account to the
attacker's identity. It does NOT guard against a fully-compromised browser
session (stolen cookies); that is out of scope for this flow.

The httpx client and ID token verifier are injectable FastAPI dependencies so
tests can substitute test doubles without mocking the google-auth library itself.
In production, verify_id_token_dep yields a function that calls
google.oauth2.id_token.verify_oauth2_token — which fetches Google's JWKS,
verifies RS256 signature, and checks iss/aud/exp.
"""

import logging
import secrets
from collections.abc import AsyncGenerator
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.cookies import set_auth_cookies
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


def _production_verify_id_token(id_token: str, client_id: str) -> dict[str, Any]:
    """Verify a Google ID token using google-auth (RS256 + iss/aud/exp checks)."""
    import google.auth.transport.requests
    import google.oauth2.id_token

    grequest = google.auth.transport.requests.Request()
    claims: dict[str, Any] = google.oauth2.id_token.verify_oauth2_token(  # type: ignore[no-untyped-call]
        id_token, grequest, client_id
    )
    return claims


async def verify_id_token_dep() -> AsyncGenerator[Any, None]:
    """FastAPI dependency that yields the active ID token verifier callable.

    Override in tests by replacing this dependency via app.dependency_overrides.
    In production, yields _production_verify_id_token which calls google-auth.
    """
    yield _production_verify_id_token


_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105

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
    verify_token: Any = Depends(verify_id_token_dep),  # noqa: B008
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
    id_token_str: str = token_data.get("id_token", "")

    try:
        payload = verify_token(id_token_str, settings.google_client_id)
    except ValueError as exc:
        _log.error("oauth: id_token verification failed error=%r", exc)
        return Response(
            status_code=status.HTTP_302_FOUND,
            headers={"location": f"{settings.frontend_url}/register?error=oauth_failed"},
        )

    # Require email_verified=True — unverified emails from Google Workspace custom
    # domains could be forged to link attacker-controlled accounts to existing users.
    if payload.get("email_verified") is not True:
        _log.warning("oauth: email_verified is not True, rejecting sub=%s", payload.get("sub"))
        return Response(
            status_code=status.HTTP_302_FOUND,
            headers={"location": f"{settings.frontend_url}/register?error=oauth_failed"},
        )

    google_sub = payload.get("sub", "")
    email = payload.get("email", "")
    display_name = payload.get("name", email.split("@")[0] if email else "")

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

    session_token = await create_session(db, user.id, ttl_days=settings.session_ttl_days)

    response = Response(
        status_code=status.HTTP_302_FOUND,
        headers={"location": f"{settings.frontend_url}/dashboard"},
    )
    set_auth_cookies(response, session_token)
    return response
