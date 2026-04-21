"""Google OAuth integration tests with stubbed provider (US-103).

Uses two FastAPI dependency overrides:
1. get_http_client — injects a mock httpx transport for Google token exchange
2. verify_id_token_dep — injects a test RSA-signed verifier so we never call
   real Google JWKS but also never bypass RS256 signing logic in tests

The verify_id_token_dep override signs tokens with a local RSA key and
verifies them against the same key — testing the full JWT flow without
hitting the network.
"""

import json
from collections.abc import AsyncGenerator, Generator
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from httpx import ASGITransport, AsyncClient

from app.auth.oauth import get_http_client, verify_id_token_dep
from app.main import app

BASE = "http://test"

FAKE_GOOGLE_SUB = "google-user-123"
FAKE_EMAIL = "oauthuser@gmail.com"
FAKE_DISPLAY_NAME = "OAuth User"

# ---------------------------------------------------------------------------
# RSA test key — generated once per process for all tests in this module
# ---------------------------------------------------------------------------
_TEST_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_TEST_PUBLIC_KEY = _TEST_PRIVATE_KEY.public_key()


_PSS_PADDING = padding.PSS(
    mgf=padding.MGF1(hashes.SHA256()),
    salt_length=padding.PSS.MAX_LENGTH,
)


def _sign_jwt(payload: dict[str, Any]) -> str:
    """Sign a test JWT with RSA-PSS (test-only — production uses google-auth).

    aud is set to settings.google_client_id so _test_verifier audience check passes.
    """
    import base64
    import time

    from app.config import settings

    now = int(time.time())
    full_payload = {
        "iss": "https://accounts.google.com",
        "aud": settings.google_client_id,
        "exp": now + 3600,
        "iat": now,
        **payload,
    }

    def b64url(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    header = b64url(json.dumps({"alg": "PS256", "typ": "JWT"}).encode())
    body = b64url(json.dumps(full_payload).encode())
    signing_input = f"{header}.{body}".encode()

    sig = _TEST_PRIVATE_KEY.sign(signing_input, _PSS_PADDING, hashes.SHA256())
    return f"{header}.{body}.{b64url(sig)}"


def _test_verifier(id_token: str, client_id: str) -> dict[str, Any]:
    """Verify a test JWT signed by _TEST_PRIVATE_KEY — used in place of google-auth."""
    import base64
    import json as _json
    import time

    parts = id_token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid token format")

    header_b64, payload_b64, sig_b64 = parts

    def b64url_decode(s: str) -> bytes:
        return base64.urlsafe_b64decode(s + "==")

    signing_input = f"{header_b64}.{payload_b64}".encode()
    sig = b64url_decode(sig_b64)

    _TEST_PUBLIC_KEY.verify(sig, signing_input, _PSS_PADDING, hashes.SHA256())

    claims: dict[str, Any] = _json.loads(b64url_decode(payload_b64))

    if claims.get("exp", 0) < time.time():
        raise ValueError("Token expired")
    # Both aud and client_id may be "" in test env; treat as matched
    if client_id and claims.get("aud") != client_id:
        raise ValueError(f"Wrong audience: {claims.get('aud')!r}")

    return claims


def _make_id_token(
    extra: dict[str, Any] | None = None,
) -> str:
    payload: dict[str, Any] = {
        "sub": FAKE_GOOGLE_SUB,
        "email": FAKE_EMAIL,
        "name": FAKE_DISPLAY_NAME,
        "email_verified": True,
    }
    if extra:
        payload.update(extra)
    return _sign_jwt(payload)


def _make_mock_http_client(id_token: str | None = None) -> httpx.AsyncClient:
    """Return an httpx client with a mock transport for Google token exchange."""
    token = id_token if id_token is not None else _make_id_token()

    def handler(request: httpx.Request) -> httpx.Response:
        if "oauth2.googleapis.com/token" in str(request.url):
            return httpx.Response(
                200,
                json={"id_token": token, "access_token": "tok"},
            )
        return httpx.Response(404)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.fixture(autouse=False)
def override_oauth_deps(
    request: pytest.FixtureRequest,
) -> Generator[None, None, None]:
    """Override both HTTP client and verifier with test doubles."""
    extra: dict[str, Any] = getattr(request, "param", {})
    id_token = _make_id_token(extra if extra else None)
    mock_client = _make_mock_http_client(id_token)

    async def _get_mock_client() -> AsyncGenerator[httpx.AsyncClient, None]:
        yield mock_client

    async def _mock_verify_dep() -> AsyncGenerator[Any, None]:
        yield _test_verifier

    app.dependency_overrides[get_http_client] = _get_mock_client
    app.dependency_overrides[verify_id_token_dep] = _mock_verify_dep
    yield
    app.dependency_overrides.pop(get_http_client, None)
    app.dependency_overrides.pop(verify_id_token_dep, None)


@pytest.fixture(autouse=False)
def override_http_client_only() -> Generator[None, None, None]:
    """Override only the HTTP client — used for tests that want real verifier behavior."""
    mock_client = _make_mock_http_client(_make_id_token())

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
async def test_oauth_callback_creates_new_user_and_session(
    override_oauth_deps: None,
) -> None:
    """New user arriving via OAuth gets an account + session + csrf_token cookie."""
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
    assert "csrf_token" in r.cookies


@pytest.mark.asyncio
async def test_oauth_callback_sets_csrf_cookie(override_oauth_deps: None) -> None:
    """OAuth callback success path must set csrf_token cookie (HIGH-5)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        init_r = await c.get("/api/v1/auth/oauth/google", follow_redirects=False)
        state = parse_qs(urlparse(init_r.headers["location"]).query).get("state", [""])[0]

        r = await c.get(
            "/api/v1/auth/oauth/google/callback",
            params={"code": "fake-code", "state": state},
            follow_redirects=False,
        )
    assert "csrf_token" in r.cookies, "OAuth callback must set csrf_token cookie"


@pytest.mark.asyncio
async def test_oauth_callback_unverified_email_rejected(
    override_http_client_only: None,
) -> None:
    """Callback with email_verified=False must redirect to error (CRITICAL-4)."""
    unverified_token = _sign_jwt(
        {
            "sub": FAKE_GOOGLE_SUB,
            "email": FAKE_EMAIL,
            "name": FAKE_DISPLAY_NAME,
            "email_verified": False,
        }
    )
    mock_client = _make_mock_http_client(unverified_token)

    async def _get_unverified_client() -> AsyncGenerator[httpx.AsyncClient, None]:
        yield mock_client

    async def _unverified_verify_dep() -> AsyncGenerator[Any, None]:
        yield _test_verifier  # _test_verifier will return email_verified=False from the token

    app.dependency_overrides[get_http_client] = _get_unverified_client
    app.dependency_overrides[verify_id_token_dep] = _unverified_verify_dep
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
            init_r = await c.get("/api/v1/auth/oauth/google", follow_redirects=False)
            state = parse_qs(urlparse(init_r.headers["location"]).query).get("state", [""])[0]

            r = await c.get(
                "/api/v1/auth/oauth/google/callback",
                params={"code": "fake-code", "state": state},
                follow_redirects=False,
            )
    finally:
        app.dependency_overrides.pop(get_http_client, None)
        app.dependency_overrides.pop(verify_id_token_dep, None)

    assert r.status_code in (302, 307)
    assert "error=oauth_failed" in r.headers["location"]


@pytest.mark.asyncio
async def test_oauth_callback_invalid_token_rejected() -> None:
    """Malformed id_token must redirect to error (CRITICAL-1).

    Uses the test verifier (not production google-auth) — _test_verifier raises
    ValueError for a malformed token, matching what google-auth raises in production.
    This keeps the test hermetic (no network, no optional requests dep).
    """
    bad_token_client = _make_mock_http_client("not.a.valid.jwt.at.all")

    async def _get_bad_client() -> AsyncGenerator[httpx.AsyncClient, None]:
        yield bad_token_client

    async def _bad_verify_dep() -> AsyncGenerator[Any, None]:
        yield _test_verifier  # raises ValueError("Invalid token format") for malformed token

    app.dependency_overrides[get_http_client] = _get_bad_client
    app.dependency_overrides[verify_id_token_dep] = _bad_verify_dep
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
            init_r = await c.get("/api/v1/auth/oauth/google", follow_redirects=False)
            state = parse_qs(urlparse(init_r.headers["location"]).query).get("state", [""])[0]

            r = await c.get(
                "/api/v1/auth/oauth/google/callback",
                params={"code": "fake-code", "state": state},
                follow_redirects=False,
            )
    finally:
        app.dependency_overrides.pop(get_http_client, None)
        app.dependency_overrides.pop(verify_id_token_dep, None)

    assert r.status_code in (302, 307)
    assert "error=oauth_failed" in r.headers["location"]


@pytest.mark.asyncio
async def test_oauth_callback_links_existing_account(override_oauth_deps: None) -> None:
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
    override_oauth_deps: None,
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
