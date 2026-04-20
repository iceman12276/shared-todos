"""Google OAuth integration tests with stubbed provider (US-103).

Uses FastAPI dependency override to inject a mock httpx client,
avoiding the need to intercept real network calls globally.
"""

import base64
import json
from collections.abc import AsyncGenerator, Generator
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.oauth import get_http_client
from app.main import app

BASE = "http://test"

FAKE_GOOGLE_SUB = "google-user-123"
FAKE_EMAIL = "oauthuser@gmail.com"
FAKE_DISPLAY_NAME = "OAuth User"

FAKE_ID_TOKEN_PAYLOAD = {
    "sub": FAKE_GOOGLE_SUB,
    "email": FAKE_EMAIL,
    "name": FAKE_DISPLAY_NAME,
    "email_verified": True,
}


def _make_fake_id_token() -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"RS256"}').rstrip(b"=").decode()
    payload = (
        base64.urlsafe_b64encode(json.dumps(FAKE_ID_TOKEN_PAYLOAD).encode()).rstrip(b"=").decode()
    )
    return f"{header}.{payload}.fakesig"


def _make_mock_http_client() -> httpx.AsyncClient:
    """Return an httpx client with a mock transport for Google endpoints."""

    def handler(request: httpx.Request) -> httpx.Response:
        if "oauth2.googleapis.com/token" in str(request.url):
            return httpx.Response(
                200,
                json={"id_token": _make_fake_id_token(), "access_token": "tok"},
            )
        if "googleapis.com/oauth2/v3/userinfo" in str(request.url):
            return httpx.Response(200, json=FAKE_ID_TOKEN_PAYLOAD)
        return httpx.Response(404)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.fixture(autouse=False)
def override_http_client() -> Generator[None, None, None]:
    mock_client = _make_mock_http_client()

    async def _get_mock_client() -> AsyncGenerator[httpx.AsyncClient, None]:
        yield mock_client

    app.dependency_overrides[get_http_client] = _get_mock_client
    yield
    app.dependency_overrides.pop(get_http_client, None)


@pytest.mark.asyncio
async def test_oauth_initiate_redirects_to_google() -> None:
    """GET /oauth/google returns a redirect to Google's auth URL."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        r = await c.get("/api/v1/auth/oauth/google", follow_redirects=False)
    assert r.status_code in (302, 307)
    location = r.headers["location"]
    assert "accounts.google.com" in location
    assert "state=" in location


@pytest.mark.asyncio
async def test_oauth_callback_invalid_state_rejected() -> None:
    """Callback with tampered state parameter is rejected (CSRF protection)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        r = await c.get(
            "/api/v1/auth/oauth/google/callback",
            params={"code": "some-code", "state": "tampered-state"},
            follow_redirects=False,
        )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_oauth_callback_creates_new_user_and_session(override_http_client: None) -> None:
    """New user arriving via OAuth gets an account + session cookie."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        init_r = await c.get("/api/v1/auth/oauth/google", follow_redirects=False)
        location = init_r.headers["location"]
        state = parse_qs(urlparse(location).query).get("state", [""])[0]

        r = await c.get(
            "/api/v1/auth/oauth/google/callback",
            params={"code": "fake-code", "state": state},
            follow_redirects=False,
        )
    assert r.status_code in (302, 307)
    assert "session" in r.cookies


@pytest.mark.asyncio
async def test_oauth_callback_links_existing_account(override_http_client: None) -> None:
    """If email+password account already exists, OAuth links to it — no duplicate."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        # Register with email+password first
        await c.post(
            "/api/v1/auth/register",
            json={"email": FAKE_EMAIL, "password": "correcthorsebattery1"},
        )

        # OAuth sign-in with same email
        init_r = await c.get("/api/v1/auth/oauth/google", follow_redirects=False)
        state = parse_qs(urlparse(init_r.headers["location"]).query).get("state", [""])[0]
        r = await c.get(
            "/api/v1/auth/oauth/google/callback",
            params={"code": "fake-code", "state": state},
            follow_redirects=False,
        )

    assert r.status_code in (302, 307)
    assert "session" in r.cookies

    # Verify no duplicate user was created
    from sqlalchemy import func, select

    from app.db.base import async_session_factory
    from app.models.user import User

    async with async_session_factory() as db:
        result = await db.execute(
            select(func.count()).select_from(User).where(User.email == FAKE_EMAIL)
        )
        count = result.scalar()
    assert count == 1


@pytest.mark.asyncio
async def test_oauth_callback_missing_state_cookie_rejected(
    override_http_client: None,
) -> None:
    """Callback without the oauth_state_nonce cookie is rejected — item 4.

    An attacker can initiate OAuth and send the URL to a victim. Without
    session-binding, the callback would succeed even in the victim's browser.
    The nonce cookie prevents this: it must be present and match the state.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        # Get a valid signed state from the initiate endpoint
        init_r = await c.get("/api/v1/auth/oauth/google", follow_redirects=False)
        state = parse_qs(urlparse(init_r.headers["location"]).query).get("state", [""])[0]

        # Simulate attacker sending URL to victim: clear the nonce cookie
        c.cookies.delete("oauth_state_nonce")

        r = await c.get(
            "/api/v1/auth/oauth/google/callback",
            params={"code": "fake-code", "state": state},
            follow_redirects=False,
        )
    assert r.status_code == 400
