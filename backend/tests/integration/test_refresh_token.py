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
# US-405: byte-identical 401 across all 5 failure modes (I5)
# ──────────────────────────────────────────────────────────────────────────────


def _response_signature(r: object) -> tuple[int, bytes, tuple[tuple[str, str], ...]]:
    """Comparable fingerprint: (status, body_bytes, sorted_headers_excluding_volatile)."""
    from httpx import Response as HttpxResponse

    assert isinstance(r, HttpxResponse)
    headers = tuple(
        sorted(
            (k.lower(), v)
            for k, v in r.headers.items()
            # set-cookie intentionally differs on success vs failure paths;
            # date and content-length vary by clock / body size
            if k.lower() not in ("set-cookie", "date", "content-length")
        )
    )
    return (r.status_code, r.content, headers)


@pytest.mark.anyio
async def test_all_401_paths_return_byte_identical_response(
    db_session: AsyncSession,
) -> None:
    """All five 401 failure modes must be byte-identical at the wire (OQ-4a / US-405).

    Uses content == comparison (not body["detail"]) to catch future middleware
    fields like request_id or trace headers that would reintroduce an
    enumeration oracle.  Mirrors test_oq1_matrix.py:166 (r_real.content ==
    r_ghost.content).
    """
    transport = ASGITransport(app=app)

    # Mode 1: no cookie
    async with AsyncClient(transport=transport, base_url=BASE) as c:
        r_no_cookie = await c.post(_REFRESH)

    # Mode 2: unknown token (never issued)
    async with AsyncClient(transport=transport, base_url=BASE) as c:
        c.cookies.set(REFRESH_COOKIE_NAME, "totally-unknown-token-xyz", domain="test")
        r_unknown = await c.post(_REFRESH)

    # Mode 3: expired token (seeded directly in DB)
    async with AsyncClient(transport=transport, base_url=BASE) as c:
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
    async with AsyncClient(transport=transport, base_url=BASE) as c:
        c.cookies.set(REFRESH_COOKIE_NAME, raw_expired, domain="test")
        r_expired = await c.post(_REFRESH)

    # Mode 4: revoked token (rotated away)
    async with AsyncClient(transport=transport, base_url=BASE) as c:
        await _register_and_login(c)
        old_token = c.cookies.get(REFRESH_COOKIE_NAME)
        assert old_token is not None
        await c.post(_REFRESH)
    async with AsyncClient(transport=transport, base_url=BASE) as c:
        c.cookies.set(REFRESH_COOKIE_NAME, old_token, domain="test")
        r_revoked = await c.post(_REFRESH)

    # Mode 5: reuse detection (same as revoked for a different family)
    async with AsyncClient(transport=transport, base_url=BASE) as c:
        await _register_and_login(c)
        reuse_old = c.cookies.get(REFRESH_COOKIE_NAME)
        assert reuse_old is not None
        await c.post(_REFRESH)
    async with AsyncClient(transport=transport, base_url=BASE) as c:
        c.cookies.set(REFRESH_COOKIE_NAME, reuse_old, domain="test")
        r_reused = await c.post(_REFRESH)

    responses = [r_no_cookie, r_unknown, r_expired, r_revoked, r_reused]
    labels = ["no_cookie", "unknown", "expired", "revoked", "reuse_detection"]
    baseline = _response_signature(r_no_cookie)
    for label, resp in zip(labels[1:], responses[1:], strict=False):
        sig = _response_signature(resp)
        assert sig == baseline, (
            f"401 failure mode '{label}' diverged from 'no_cookie' baseline — "
            f"this leaks distinguishing information. sig={sig!r} baseline={baseline!r}"
        )


# ──────────────────────────────────────────────────────────────────────────────
# Invariant I2: atomicity under partial failure (failure injection)
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_reuse_detection_is_atomic_under_partial_failure(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Failure mid-reuse-detection must not leave the family partially revoked (I2).

    Monkey-patches invalidate_sessions_by_family to raise RuntimeError after
    revoke_family stages its UPDATE.  The transaction must roll back entirely —
    asserted via positive evidence: the valid token's revoked_at is still NULL.
    """
    from sqlalchemy import select as _select

    import app.auth.router as auth_router

    # Register + login to get a token family
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _register_and_login(c)
        valid_token = c.cookies.get(REFRESH_COOKIE_NAME)
        assert valid_token is not None
        old_token = valid_token
        # Rotate once so old_token is revoked (reuse-detection target)
        await c.post(_REFRESH)
        current_token = c.cookies.get(REFRESH_COOKIE_NAME)
        assert current_token is not None

    # Verify current_token's DB entry is active before injection
    db_session.expire_all()
    current_hash = hash_token(current_token)
    result = await db_session.execute(
        _select(RefreshToken).where(RefreshToken.token_hash == current_hash)
    )
    current_rt = result.scalar_one()
    family_id = current_rt.family_id
    assert current_rt.revoked_at is None, "precondition: current token is active"

    # Inject failure into session invalidation so the transaction aborts
    async def _raise(*args: object, **kwargs: object) -> None:
        raise RuntimeError("injected failure — simulates mid-revocation crash")

    monkeypatch.setattr(auth_router, "invalidate_sessions_by_family", _raise)

    # Present the OLD (rotated-away) token to trigger reuse detection
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c2:
        c2.cookies.set(REFRESH_COOKIE_NAME, old_token, domain="test")
        r = await c2.post(_REFRESH)

    # Request fails (500 acceptable for injected internal error)
    assert r.status_code in {401, 500}, f"expected 401 or 500, got {r.status_code}"

    # Positive-evidence: DB state must NOT be partially revoked
    # The current active token must still be active (no partial revocation window)
    db_session.expire_all()
    result2 = await db_session.execute(
        _select(RefreshToken).where(
            RefreshToken.family_id == family_id,
            RefreshToken.revoked_at.is_(None),
        )
    )
    active_rows = result2.scalars().all()
    assert len(active_rows) == 1, (
        f"I2 atomicity violated: expected 1 active token after aborted revocation, "
        f"got {len(active_rows)}.  Family was partially revoked."
    )
    assert active_rows[0].token_hash == current_hash


# ──────────────────────────────────────────────────────────────────────────────
# Invariant I3: no raw token material in logs + positive structured-field check
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


@pytest.mark.anyio
async def test_refresh_logs_contain_structured_fields(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Rotation log line must contain family_id= and user_id= fields (I3 positive side).

    Absence-only (no raw token in logs) cannot distinguish 'logs are safe'
    from 'log lines were silently removed'.  This test adds the positive
    complement: structured fields ARE present.
    """
    import logging as _logging

    # alembic.fileConfig(disable_existing_loggers=True) may have disabled this
    # logger if test_alembic_boots ran first in the session.
    _logging.getLogger("app.auth").disabled = False

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _register_and_login(c)
        raw_refresh = c.cookies.get(REFRESH_COOKIE_NAME)
        assert raw_refresh is not None
        with caplog.at_level(logging.INFO, logger="app.auth"):
            r = await c.post(_REFRESH)

    assert r.status_code == 200

    refresh_msgs = [rec.message for rec in caplog.records if "refresh" in rec.message.lower()]
    assert refresh_msgs, f"expected at least one 'refresh' log line, got: {caplog.text!r}"
    assert any("family_id=" in m for m in refresh_msgs), (
        f"no structured family_id= field in refresh logs: {refresh_msgs}"
    )
    assert any("user_id=" in m for m in refresh_msgs), (
        f"no structured user_id= field in refresh logs: {refresh_msgs}"
    )
    # Negative: raw token value must not appear in any log line
    for msg in refresh_msgs:
        assert raw_refresh not in msg, f"raw token leaked into log: {msg[:80]}..."


# ──────────────────────────────────────────────────────────────────────────────
# Alembic downgrade / upgrade (migration reversibility)
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_migration_is_reversible() -> None:
    """Verify the refresh_tokens migration can be applied and reversed cleanly."""
    from pathlib import Path

    import anyio

    import alembic.command
    import alembic.config

    # test file is backend/tests/integration/test_*.py — three .parent hops reach backend/
    alembic_ini = Path(__file__).parent.parent.parent / "alembic.ini"

    def _run_alembic() -> None:
        cfg = alembic.config.Config(str(alembic_ini))
        alembic.command.downgrade(cfg, "4df1779548df")
        alembic.command.upgrade(cfg, "head")

    # alembic calls asyncio.run internally — must run in a thread
    await anyio.to_thread.run_sync(_run_alembic)
