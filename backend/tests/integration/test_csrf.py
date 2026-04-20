"""CSRF double-submit cookie protection tests.

Mutating verbs (POST, PUT, PATCH, DELETE) on protected routes require
matching X-CSRF-Token header and csrf_token cookie.
"""
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

BASE = "http://test"


async def _register_and_get_csrf(c: AsyncClient) -> tuple[str, str]:
    """Register a user and return (session_token, csrf_token)."""
    r = await c.post(
        "/api/v1/auth/register",
        json={"email": "csrftest@example.com", "password": "correcthorsebattery1"},
    )
    assert r.status_code == 201
    session = r.cookies["session"]
    csrf = r.cookies.get("csrf_token", "")
    return session, csrf


@pytest.mark.asyncio
async def test_csrf_token_set_on_register() -> None:
    """Registration sets both session and csrf_token cookies."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        r = await c.post(
            "/api/v1/auth/register",
            json={"email": "csrftoken@example.com", "password": "correcthorsebattery1"},
        )
    assert r.status_code == 201
    assert "csrf_token" in r.cookies


@pytest.mark.asyncio
async def test_csrf_token_set_on_login() -> None:
    """Login sets csrf_token cookie."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await c.post(
            "/api/v1/auth/register",
            json={"email": "csrflogin@example.com", "password": "correcthorsebattery1"},
        )
        r = await c.post(
            "/api/v1/auth/login",
            json={"email": "csrflogin@example.com", "password": "correcthorsebattery1"},
        )
    assert "csrf_token" in r.cookies


@pytest.mark.asyncio
async def test_logout_without_csrf_token_succeeds() -> None:
    """Logout is exempt from CSRF (it's idempotent and safe to perform without header)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await c.post(
            "/api/v1/auth/register",
            json={"email": "csrflogout@example.com", "password": "correcthorsebattery1"},
        )
        r = await c.post("/api/v1/auth/logout")
    assert r.status_code == 204
