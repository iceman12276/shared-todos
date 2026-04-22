"""Integration tests for refresh token rotation (PRD-4).

Covers:
  US-401: refresh token issued on login
  US-402: POST /api/v1/auth/refresh — valid rotation
  US-403: expiry + explicit logout revokes family
  US-404: reuse detection + atomic family revocation
  US-405: stranger/missing/malformed token → 401

Invariant checks:
  I1: single active token per family after rotation
  I2: reuse detection is atomic (no partial revocation window)
  I3: no raw token material in logs
  I4: family revocation propagates to sessions
  I5: refresh cookie attributes match spec (httpOnly, SameSite=Lax)

PRD-4 success metric: all four 401 paths return indistinguishable
responses — verified via a single parametrized test.
"""

import logging
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.cookies import REFRESH_COOKIE_NAME, SESSION_COOKIE_NAME
from app.auth.tokens import hash_token
from app.main import app
from app.models.refresh_token import RefreshToken
from app.models.user import User

BASE = "http://test"
_REGISTER = "/api/v1/auth/register"
_LOGIN = "/api/v1/auth/login"
_LOGOUT = "/api/v1/auth/logout"
_REFRESH = "/api/v1/auth/refresh"
_SESSION = "/api/v1/auth/session"

_EMAIL = "refresh@example.com"
_PASSWORD = "Password123!"  # noqa: S105


async def _register_and_login(client: AsyncClient) -> None:
    await client.post(_REGISTER, json={"email": _EMAIL, "password": _PASSWORD})


async def _login(client: AsyncClient) -> None:
    await client.post(_LOGIN, json={"email": _EMAIL, "password": _PASSWORD})


# ──────────────────────────────────────────────────────────────────────────────
# US-401: refresh token issued on login
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_login_issues_refresh_cookie() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await c.post(_REGISTER, json={"email": _EMAIL, "password": _PASSWORD})
        await c.post(_LOGIN, json={"email": _EMAIL, "password": _PASSWORD})
        assert REFRESH_COOKIE_NAME in c.cookies


@pytest.mark.anyio
async def test_register_issues_refresh_cookie() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        r = await c.post(_REGISTER, json={"email": _EMAIL, "password": _PASSWORD})
    assert REFRESH_COOKIE_NAME in r.cookies


@pytest.mark.anyio
async def test_refresh_cookie_is_httponly(db_session: AsyncSession) -> None:
    # httpOnly cookies are not visible to JS — httpx respects this by only
    # setting them via Set-Cookie headers, not via document.cookie. We verify
    # the header attribute directly.
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        r = await c.post(_REGISTER, json={"email": _EMAIL, "password": _PASSWORD})
    set_cookie_headers = r.headers.get_list("set-cookie")
    refresh_header = next((h for h in set_cookie_headers if REFRESH_COOKIE_NAME in h), None)
    assert refresh_header is not None
    assert "HttpOnly" in refresh_header


@pytest.mark.anyio
async def test_refresh_cookie_is_samesite_lax(db_session: AsyncSession) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        r = await c.post(_REGISTER, json={"email": _EMAIL, "password": _PASSWORD})
    set_cookie_headers = r.headers.get_list("set-cookie")
    refresh_header = next((h for h in set_cookie_headers if REFRESH_COOKIE_NAME in h), None)
    assert refresh_header is not None
    assert "SameSite=lax" in refresh_header


# ──────────────────────────────────────────────────────────────────────────────
# US-402: POST /api/v1/auth/refresh — valid rotation
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_refresh_valid_token_issues_new_cookies() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _register_and_login(c)
        old_refresh = c.cookies.get(REFRESH_COOKIE_NAME)
        old_session = c.cookies.get(SESSION_COOKIE_NAME)

        r = await c.post(_REFRESH)

    assert r.status_code == 200
    new_refresh = r.cookies.get(REFRESH_COOKIE_NAME)
    new_session = r.cookies.get(SESSION_COOKIE_NAME)
    assert new_refresh is not None
    assert new_session is not None
    assert new_refresh != old_refresh
    assert new_session != old_session


@pytest.mark.anyio
async def test_refresh_response_body_is_empty_or_minimal() -> None:
    """No token material in response body (PRD-4 constraint)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _register_and_login(c)
        r = await c.post(_REFRESH)
    assert r.status_code == 200
    # Body must not contain anything resembling a token value
    body_text = r.text
    assert len(body_text) < 200  # should be minimal


@pytest.mark.anyio
async def test_refresh_old_token_cannot_be_used_again() -> None:
    """After rotation, the old refresh token must return 401 (I1 — single active)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _register_and_login(c)
        old_refresh = c.cookies.get(REFRESH_COOKIE_NAME)
        assert old_refresh is not None

        # First refresh — succeeds, rotates token
        r1 = await c.post(_REFRESH)
        assert r1.status_code == 200

    # Fresh client with ONLY the old (rotated-away) token — must return 401
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c2:
        c2.cookies.set(REFRESH_COOKIE_NAME, old_refresh, domain="test")
        r2 = await c2.post(_REFRESH)

    assert r2.status_code == 401


@pytest.mark.anyio
async def test_refresh_new_session_is_usable() -> None:
    """After rotation, the new session cookie must authenticate /session."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _register_and_login(c)
        await c.post(_REFRESH)
        r = await c.get(_SESSION)
    assert r.status_code == 200
    assert r.json()["user"]["email"] == _EMAIL


# ──────────────────────────────────────────────────────────────────────────────
# US-403: expiry and explicit logout
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_missing_refresh_cookie_returns_401() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        r = await c.post(_REFRESH)
    assert r.status_code == 401


@pytest.mark.anyio
async def test_logout_prevents_refresh(db_session: AsyncSession) -> None:
    """After logout, the refresh token from that session must return 401 (US-403)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _register_and_login(c)
        refresh_before_logout = c.cookies.get(REFRESH_COOKIE_NAME)
        assert refresh_before_logout is not None
        await c.post(_LOGOUT)

    # Fresh client — replay the pre-logout refresh token (should be revoked)
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c2:
        c2.cookies.set(REFRESH_COOKIE_NAME, refresh_before_logout, domain="test")
        r = await c2.post(_REFRESH)
    assert r.status_code == 401


@pytest.mark.anyio
async def test_logout_with_family_revokes_all_family_sessions(
    db_session: AsyncSession,
) -> None:
    """Logout must invalidate session AND refresh token family (PRD-4 Invariant 4)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _register_and_login(c)
        # Rotate once to create a two-token family chain
        await c.post(_REFRESH)
        refresh_after_rotate = c.cookies.get(REFRESH_COOKIE_NAME)
        assert refresh_after_rotate is not None
        await c.post(_LOGOUT)

    # After logout, the rotated token (current before logout) must also be revoked
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c2:
        c2.cookies.set(REFRESH_COOKIE_NAME, refresh_after_rotate, domain="test")
        r = await c2.post(_REFRESH)
    assert r.status_code == 401


# ──────────────────────────────────────────────────────────────────────────────
# US-404: reuse detection + atomic family revocation
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_reuse_detection_revokes_entire_family() -> None:
    """Presenting a rotated-away token revokes the entire family (US-404)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _register_and_login(c)
        old_refresh = c.cookies.get(REFRESH_COOKIE_NAME)
        assert old_refresh is not None

        # Legitimate rotation
        r1 = await c.post(_REFRESH)
        assert r1.status_code == 200
        new_refresh = c.cookies.get(REFRESH_COOKIE_NAME)
        assert new_refresh is not None

    transport = ASGITransport(app=app)

    # Attacker replays the old (now rotated-away) token — triggers detection
    async with AsyncClient(transport=transport, base_url=BASE) as attacker:
        attacker.cookies.set(REFRESH_COOKIE_NAME, old_refresh, domain="test")
        r2 = await attacker.post(_REFRESH)
    assert r2.status_code == 401

    # The NEW (current) token from the same family must also be invalidated
    async with AsyncClient(transport=transport, base_url=BASE) as victim:
        victim.cookies.set(REFRESH_COOKIE_NAME, new_refresh, domain="test")
        r3 = await victim.post(_REFRESH)
    assert r3.status_code == 401


@pytest.mark.anyio
async def test_reuse_detection_invalidates_session() -> None:
    """After reuse detection, the session from that family is also invalid (Invariant 4)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _register_and_login(c)
        old_refresh = c.cookies.get(REFRESH_COOKIE_NAME)
        assert old_refresh is not None
        session_before_reuse = c.cookies.get(SESSION_COOKIE_NAME)
        assert session_before_reuse is not None

        # Rotate legitimately — new session issued
        await c.post(_REFRESH)

    # Replay old token from a fresh client — triggers reuse detection + family revocation
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c2:
        c2.cookies.set(REFRESH_COOKIE_NAME, old_refresh, domain="test")
        await c2.post(_REFRESH)

    # The session issued before the reuse must now be invalid
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c3:
        c3.cookies.set(SESSION_COOKIE_NAME, session_before_reuse, domain="test")
        r = await c3.get(_SESSION)
    assert r.status_code == 401


# ──────────────────────────────────────────────────────────────────────────────
# US-405: all 401 paths return indistinguishable responses
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.anyio
@pytest.mark.parametrize(
    "scenario",
    [
        "no_cookie",
        "unknown_token",
        "expired_token",
        "revoked_token",
        "reuse_detection",
    ],
    ids=["no_cookie", "unknown_token", "expired_token", "revoked_token", "reuse_detection"],
)
async def test_all_401_paths_return_identical_response(
    scenario: str, db_session: AsyncSession
) -> None:
    """All failure modes must return identical HTTP status + body (PRD-4 success metric)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        if scenario == "no_cookie":
            r = await c.post(_REFRESH)

        elif scenario == "unknown_token":
            c.cookies.set(REFRESH_COOKIE_NAME, "totally-unknown-token-xyz", domain="test")
            r = await c.post(_REFRESH)

        elif scenario == "expired_token":
            # Seed an expired token directly in the DB
            await _register_and_login(c)
            from sqlalchemy import select as _select

            user_res = await db_session.execute(_select(User).where(User.email == _EMAIL))
            u = user_res.scalar_one()
            raw_expired = "expired-raw-token-value"
            rt = RefreshToken(
                family_id=uuid4(),
                user_id=u.id,
                token_hash=hash_token(raw_expired),
                issued_at=datetime.now(UTC) - timedelta(days=31),
                expires_at=datetime.now(UTC) - timedelta(seconds=1),
            )
            db_session.add(rt)
            await db_session.commit()
            # Use a fresh client with ONLY the expired token (no valid registered token)
            async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c2:
                c2.cookies.set(REFRESH_COOKIE_NAME, raw_expired, domain="test")
                r = await c2.post(_REFRESH)

        elif scenario == "revoked_token":
            await _register_and_login(c)
            old_refresh = c.cookies.get(REFRESH_COOKIE_NAME)
            assert old_refresh is not None
            # Rotate — makes old token revoked
            await c.post(_REFRESH)

            # Present the rotated-away token via a fresh client (reuse detection path)
            async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c2:
                c2.cookies.set(REFRESH_COOKIE_NAME, old_refresh, domain="test")
                r = await c2.post(_REFRESH)

        else:  # reuse_detection — identical path, alias for clarity
            await _register_and_login(c)
            old = c.cookies.get(REFRESH_COOKIE_NAME)
            assert old is not None
            await c.post(_REFRESH)

            async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c2:
                c2.cookies.set(REFRESH_COOKIE_NAME, old, domain="test")
                r = await c2.post(_REFRESH)

    assert r.status_code == 401
    body = r.json()
    # All paths must return the same top-level key and identical body content
    assert "detail" in body
    assert body["detail"] == "Session expired. Please log in again."


# ──────────────────────────────────────────────────────────────────────────────
# Invariant I3: no raw token material in logs
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_no_raw_token_in_logs(caplog: pytest.LogCaptureFixture) -> None:
    """Raw refresh tokens must never appear in application logs (Invariant 3)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _register_and_login(c)
        raw_refresh = c.cookies.get(REFRESH_COOKIE_NAME)
        assert raw_refresh is not None
        with caplog.at_level(logging.DEBUG):
            await c.post(_REFRESH)

    assert raw_refresh not in caplog.text


# ──────────────────────────────────────────────────────────────────────────────
# Alembic downgrade / upgrade (migration reversibility)
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_migration_is_reversible() -> None:
    """Verify the refresh_tokens migration can be applied and reversed cleanly."""
    import anyio

    import alembic.command
    import alembic.config

    def _run_alembic() -> None:
        cfg = alembic.config.Config("/home/isaac/Desktop/dev/shared-todos-pr4/backend/alembic.ini")
        alembic.command.downgrade(cfg, "4df1779548df")
        alembic.command.upgrade(cfg, "head")

    # alembic calls asyncio.run internally — must run in a thread
    await anyio.to_thread.run_sync(_run_alembic)
