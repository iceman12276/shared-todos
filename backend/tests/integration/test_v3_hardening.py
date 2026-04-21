"""v3 test hardening: 3 CRIT gaps from PR #2 v2 validation report.

CRIT-1: Google-only account password-reset anti-enum — router.py:148 unreached
CRIT-2: Multi-device session invalidation on password reset — single-cookie fixture
CRIT-3: Narrowed-except invariant — future re-broadening would silently pass
"""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.oauth import verify_id_token_dep
from app.main import app

BASE = "http://test"


# ---------------------------------------------------------------------------
# CRIT-1: Google-only account password-reset anti-enum
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_password_reset_request_google_only_account_opaque() -> None:
    """Google-only account: reset request returns 200, no PasswordResetToken created.

    Locks in the router.py:148 branch — a refactor removing it would silently
    allow enumeration or raise an error instead of returning the opaque message.
    """
    from sqlalchemy import select

    from app.db.base import async_session_factory
    from app.models.password_reset_token import PasswordResetToken
    from app.models.user import User

    # Seed a google-only user (no password_hash)
    async with async_session_factory() as db:
        user = User(
            email="googleonly@example.com",
            display_name="Google Only",
            google_sub="google-sub-gotest-001",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        user_id = user.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        r = await c.post(
            "/api/v1/auth/password-reset/request",
            json={"email": "googleonly@example.com"},
        )

    # Anti-enum: always 200, same body regardless of account type
    assert r.status_code == 200
    assert "message" in r.json()

    # No PasswordResetToken row must have been created
    async with async_session_factory() as db:
        result = await db.execute(
            select(PasswordResetToken).where(PasswordResetToken.user_id == user_id)
        )
        prt = result.scalar_one_or_none()
    assert prt is None, "Google-only account must not create a PasswordResetToken row"


# ---------------------------------------------------------------------------
# CRIT-2: Multi-device session invalidation on password reset
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_password_reset_invalidates_all_sessions_multi_device() -> None:
    """Completing a password reset must invalidate sessions on ALL devices.

    Two separate clients each login independently. One client completes a
    password reset. Both clients' session cookies must be rejected afterwards.
    US-107 multi-device guarantee.
    """
    from sqlalchemy import select

    from app.auth.tokens import generate_reset_token, hash_token
    from app.db.base import async_session_factory
    from app.models.password_reset_token import PasswordResetToken
    from app.models.user import User

    email = "multidevice@example.com"
    password = "correcthorsebattery1"  # noqa: S105

    transport = ASGITransport(app=app)

    # Device A: register (creates account + first session)
    async with AsyncClient(transport=transport, base_url=BASE) as device_a:
        r_a = await device_a.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password},
        )
        assert r_a.status_code == 201
        csrf_a: str = r_a.cookies.get("csrf_token") or ""
        session_a = r_a.cookies["session"]

    # Device B: login to get its own session
    async with AsyncClient(transport=transport, base_url=BASE) as device_b:
        r_b = await device_b.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        assert r_b.status_code == 200
        session_b = r_b.cookies["session"]

    # Verify both sessions are independently valid before reset
    async with AsyncClient(transport=transport, base_url=BASE) as c:
        c.cookies.set("session", session_a)
        assert (await c.get("/api/v1/auth/session")).status_code == 200

    async with AsyncClient(transport=transport, base_url=BASE) as c:
        c.cookies.set("session", session_b)
        assert (await c.get("/api/v1/auth/session")).status_code == 200

    # Create a reset token for the user
    async with async_session_factory() as db:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one()
        reset_token = generate_reset_token()
        prt = PasswordResetToken(
            user_id=user.id,
            token_hash=hash_token(reset_token),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        db.add(prt)
        await db.commit()

    # Device A completes the reset
    async with AsyncClient(transport=transport, base_url=BASE) as c:
        c.cookies.set("session", session_a)
        c.cookies.set("csrf_token", csrf_a)
        r_reset = await c.post(
            "/api/v1/auth/password-reset/complete",
            json={"token": reset_token, "new_password": "newpassword123456"},
            headers={"X-CSRF-Token": csrf_a},
        )
    assert r_reset.status_code == 200

    # Both sessions must now be invalid
    async with AsyncClient(transport=transport, base_url=BASE) as c:
        c.cookies.set("session", session_a)
        r_a_after = await c.get("/api/v1/auth/session")
    assert r_a_after.status_code == 401, "Device A session must be invalidated after reset"

    async with AsyncClient(transport=transport, base_url=BASE) as c:
        c.cookies.set("session", session_b)
        r_b_after = await c.get("/api/v1/auth/session")
    assert r_b_after.status_code == 401, "Device B session must be invalidated after reset"


# ---------------------------------------------------------------------------
# CRIT-3: Narrowed-except invariant — RuntimeError must not become redirect
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_oauth_callback_unexpected_exception_returns_500_not_redirect() -> None:
    """Verifier raising RuntimeError must produce HTTP 500, NOT a 302 redirect.

    The hotfix at 9c4faf0 narrowed except to ValueError only. This test locks
    in that invariant:
    - assert r.status_code == 500: proves FastAPI's ServerErrorMiddleware caught
      the unhandled RuntimeError and returned an error response
    - assert r.status_code != 302: documents the specific invariant — the old
      `except Exception` swallowed the RuntimeError and returned a 302 redirect

    Uses raise_app_exceptions=False so httpx converts unhandled app exceptions
    to HTTP 500 responses (matching real server behavior) rather than re-raising
    them into the test process.
    """
    from urllib.parse import parse_qs
    from urllib.parse import urlparse as _urlparse

    import httpx

    from app.auth.oauth import get_http_client

    def _runtime_error_verifier(id_token: str, client_id: str) -> dict[str, Any]:
        raise RuntimeError("unexpected internal error from JWKS fetch or transport")

    async def _runtime_verify_dep() -> AsyncGenerator[Any, None]:
        yield _runtime_error_verifier

    def _handler(request: httpx.Request) -> httpx.Response:
        if "oauth2.googleapis.com/token" in str(request.url):
            return httpx.Response(
                200,
                json={"id_token": "any.token.value", "access_token": "tok"},
            )
        return httpx.Response(404)

    mock_http_client = httpx.AsyncClient(transport=httpx.MockTransport(_handler))

    async def _get_mock_http() -> AsyncGenerator[httpx.AsyncClient, None]:
        yield mock_http_client

    # raise_app_exceptions=False: callback 500 becomes an HTTP response, not a raised exception
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url=BASE) as c:
        # Override only HTTP client to get the state nonce (no verifier override yet)
        app.dependency_overrides[get_http_client] = _get_mock_http
        init_r = await c.get("/api/v1/auth/oauth/google", follow_redirects=False)
        assert init_r.status_code in (302, 307)
        state = parse_qs(_urlparse(init_r.headers["location"]).query).get("state", [""])[0]

        # Inject broken verifier AFTER nonce — same client keeps the nonce cookie
        app.dependency_overrides[verify_id_token_dep] = _runtime_verify_dep

        try:
            r = await c.get(
                "/api/v1/auth/oauth/google/callback",
                params={"code": "fake-code", "state": state},
                follow_redirects=False,
            )
        finally:
            app.dependency_overrides.pop(get_http_client, None)
            app.dependency_overrides.pop(verify_id_token_dep, None)

    assert r.status_code == 500, (
        f"Unexpected verifier exception must produce HTTP 500, got {r.status_code}. "
        f"If 302: except was re-broadened to catch Exception (swallows error → redirect)."
    )
    assert r.status_code != 302, (
        "302 here means except was broadened to catch Exception — narrowed-except invariant broken."
    )
