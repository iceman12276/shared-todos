"""Integration tests for register and login endpoints (US-101, US-102)."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

BASE = "http://test"


@pytest.fixture
def client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url=BASE)


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient) -> None:
    async with client as c:
        r = await c.post(
            "/api/v1/auth/register",
            json={"email": "bob@example.com", "password": "correcthorsebattery1"},
        )
    assert r.status_code == 201
    data = r.json()
    assert "user" in data
    assert data["user"]["email"] == "bob@example.com"
    assert "session" in r.cookies


@pytest.mark.asyncio
async def test_register_sets_session_cookie(client: AsyncClient) -> None:
    async with client as c:
        r = await c.post(
            "/api/v1/auth/register",
            json={"email": "cookie@example.com", "password": "correcthorsebattery1"},
        )
    assert "session" in r.cookies
    cookie = r.cookies["session"]
    assert len(cookie) > 20


@pytest.mark.asyncio
async def test_register_password_too_short(client: AsyncClient) -> None:
    async with client as c:
        r = await c.post(
            "/api/v1/auth/register",
            json={"email": "short@example.com", "password": "tooshort"},
        )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_register_invalid_email(client: AsyncClient) -> None:
    async with client as c:
        r = await c.post(
            "/api/v1/auth/register",
            json={"email": "not-an-email", "password": "correcthorsebattery1"},
        )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_register_duplicate_email_no_enumeration(client: AsyncClient) -> None:
    """A duplicate email returns 201 with the same non-revealing message — no enumeration."""
    async with client as c:
        await c.post(
            "/api/v1/auth/register",
            json={"email": "dup@example.com", "password": "correcthorsebattery1"},
        )
        r2 = await c.post(
            "/api/v1/auth/register",
            json={"email": "dup@example.com", "password": "anotherpassword12"},
        )
    # Must not be 409/400 — must return non-enumeration response
    assert r2.status_code == 201
    assert "user" not in r2.json() or r2.json().get("user") is None


@pytest.mark.asyncio
async def test_register_duplicate_email_cookies_match_success_branch(
    client: AsyncClient,
) -> None:
    """Duplicate-email register must set cookies identical to a fresh register.

    Without this, an attacker can distinguish 'email exists' from 'email free'
    by checking for Set-Cookie: session in the response headers (item 2).
    """
    async with client as c:
        r1 = await c.post(
            "/api/v1/auth/register",
            json={"email": "sidechannel@example.com", "password": "correcthorsebattery1"},
        )
        r2 = await c.post(
            "/api/v1/auth/register",
            json={"email": "sidechannel@example.com", "password": "anotherpassword12"},
        )
    # Both responses must set session and csrf_token cookies
    assert "session" in r1.cookies
    assert "csrf_token" in r1.cookies
    assert "session" in r2.cookies, "duplicate-email branch must also set session cookie"
    assert "csrf_token" in r2.cookies, "duplicate-email branch must also set csrf_token cookie"


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient) -> None:
    async with client as c:
        await c.post(
            "/api/v1/auth/register",
            json={"email": "login@example.com", "password": "correcthorsebattery1"},
        )
        r = await c.post(
            "/api/v1/auth/login",
            json={"email": "login@example.com", "password": "correcthorsebattery1"},
        )
    assert r.status_code == 200
    assert "session" in r.cookies


@pytest.mark.asyncio
async def test_login_wrong_password_generic_error(client: AsyncClient) -> None:
    async with client as c:
        await c.post(
            "/api/v1/auth/register",
            json={"email": "loginbad@example.com", "password": "correcthorsebattery1"},
        )
        r = await c.post(
            "/api/v1/auth/login",
            json={"email": "loginbad@example.com", "password": "wrongpassword123"},
        )
    assert r.status_code == 401
    # Must not distinguish between wrong email and wrong password
    body = r.json()
    assert "detail" in body
    assert "email" not in body["detail"].lower() or "password" not in body["detail"].lower()


@pytest.mark.asyncio
async def test_login_nonexistent_email_same_as_wrong_password(client: AsyncClient) -> None:
    """Anti-enumeration: nonexistent email returns same 401 as wrong password."""
    async with client as c:
        r = await c.post(
            "/api/v1/auth/login",
            json={"email": "ghost@example.com", "password": "correcthorsebattery1"},
        )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_logout_invalidates_session(client: AsyncClient) -> None:
    async with client as c:
        await c.post(
            "/api/v1/auth/register",
            json={"email": "logout@example.com", "password": "correcthorsebattery1"},
        )
        login_r = await c.post(
            "/api/v1/auth/login",
            json={"email": "logout@example.com", "password": "correcthorsebattery1"},
        )
        # Logout — must include CSRF header (logout is not exempt)
        csrf: str = login_r.cookies.get("csrf_token") or ""
        logout_r = await c.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf})
        assert logout_r.status_code == 204
        # Old cookie should now be unauthorized
        old_cookie = login_r.cookies["session"]
        c.cookies.set("session", old_cookie)
        session_r = await c.get("/api/v1/auth/session")
    assert session_r.status_code == 401


@pytest.mark.asyncio
async def test_get_session_authenticated(client: AsyncClient) -> None:
    async with client as c:
        await c.post(
            "/api/v1/auth/register",
            json={"email": "me@example.com", "password": "correcthorsebattery1"},
        )
        r = await c.get("/api/v1/auth/session")
    assert r.status_code == 200
    assert r.json()["user"]["email"] == "me@example.com"


@pytest.mark.asyncio
async def test_get_session_unauthenticated(client: AsyncClient) -> None:
    async with client as c:
        r = await c.get("/api/v1/auth/session")
    assert r.status_code == 401
