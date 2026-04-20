"""CSRF double-submit cookie protection tests.

Mutating verbs (POST, PUT, PATCH, DELETE) on protected routes require
matching X-CSRF-Token header and csrf_token cookie.
Login and register are exempt (no session yet).
"""
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

BASE = "http://test"


async def _register(c: AsyncClient, email: str) -> tuple[str, str]:
    """Register a user and return (session_token, csrf_token)."""
    r = await c.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correcthorsebattery1"},
    )
    assert r.status_code == 201
    return r.cookies["session"], r.cookies["csrf_token"]


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
async def test_logout_without_csrf_header_rejected() -> None:
    """Logout requires CSRF — forced-logout is a real attack."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        _, _ = await _register(c, "csrflogout_reject@example.com")
        r = await c.post("/api/v1/auth/logout")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_logout_with_matching_csrf_header_succeeds() -> None:
    """Logout with matching X-CSRF-Token header succeeds."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        _, csrf = await _register(c, "csrflogout_ok@example.com")
        r = await c.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_protected_post_without_csrf_rejected() -> None:
    """POST to a protected endpoint without CSRF header returns 403."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _register(c, "csrfguard@example.com")
        r = await c.post(
            "/api/v1/auth/password-reset/request",
            json={"email": "csrfguard@example.com"},
        )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_protected_post_with_mismatched_csrf_rejected() -> None:
    """POST with mismatched X-CSRF-Token (cookie ≠ header) returns 403."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _register(c, "csrfmismatch@example.com")
        r = await c.post(
            "/api/v1/auth/password-reset/request",
            json={"email": "csrfmismatch@example.com"},
            headers={"X-CSRF-Token": "wrong-token"},
        )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_protected_post_with_matching_csrf_succeeds() -> None:
    """POST with matching X-CSRF-Token header passes CSRF check."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        _, csrf = await _register(c, "csrfpass@example.com")
        r = await c.post(
            "/api/v1/auth/password-reset/request",
            json={"email": "csrfpass@example.com"},
            headers={"X-CSRF-Token": csrf},
        )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_register_exempt_from_csrf() -> None:
    """Register is exempt — no session cookie exists yet."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        r = await c.post(
            "/api/v1/auth/register",
            json={"email": "csrfexempt@example.com", "password": "correcthorsebattery1"},
        )
    assert r.status_code == 201


@pytest.mark.asyncio
async def test_login_exempt_from_csrf() -> None:
    """Login is exempt — no session exists yet, so no CSRF token to match."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await c.post(
            "/api/v1/auth/register",
            json={"email": "csrfloginexempt@example.com", "password": "correcthorsebattery1"},
        )
        r = await c.post(
            "/api/v1/auth/login",
            json={"email": "csrfloginexempt@example.com", "password": "correcthorsebattery1"},
        )
    assert r.status_code == 200
