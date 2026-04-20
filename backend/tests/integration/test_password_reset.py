"""Password reset flow integration tests (US-106, US-107)."""
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

BASE = "http://test"


@pytest.fixture
def client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url=BASE)


async def _register_and_login(client: AsyncClient, email: str) -> str:
    """Helper: register a user and return the session token."""
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correcthorsebattery1"},
    )
    assert r.status_code == 201
    return r.cookies["session"]


@pytest.mark.asyncio
async def test_reset_request_opaque_for_registered_email() -> None:
    """Reset request always returns 200 regardless of email existence."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await c.post(
            "/api/v1/auth/register",
            json={"email": "reset@example.com", "password": "correcthorsebattery1"},
        )
        r = await c.post(
            "/api/v1/auth/password-reset/request",
            json={"email": "reset@example.com"},
        )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_reset_request_opaque_for_nonexistent_email(client: AsyncClient) -> None:
    """Same 200 response for nonexistent email — no enumeration."""
    async with client as c:
        r = await c.post(
            "/api/v1/auth/password-reset/request",
            json={"email": "ghost@example.com"},
        )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_reset_validate_valid_token(client: AsyncClient) -> None:
    """A freshly-issued token validates successfully."""
    from app.auth.tokens import generate_reset_token, hash_token
    from datetime import datetime, timedelta, timezone
    from app.db.base import async_session_factory
    from app.models.password_reset_token import PasswordResetToken
    from app.models.user import User
    from sqlalchemy import select

    async with async_session_factory() as db:
        result = await db.execute(select(User).where(User.email == "validatetoken@example.com"))
        user = result.scalar_one_or_none()
        if user is None:
            user = User(email="validatetoken@example.com", display_name="v", password_hash="x")
            db.add(user)
            await db.commit()
            await db.refresh(user)
        token = generate_reset_token()
        prt = PasswordResetToken(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        db.add(prt)
        await db.commit()

    async with client as c:
        r = await c.get(f"/api/v1/auth/password-reset/validate?token={token}")
    assert r.status_code == 200
    assert r.json()["valid"] is True


@pytest.mark.asyncio
async def test_reset_validate_invalid_token(client: AsyncClient) -> None:
    async with client as c:
        r = await c.get("/api/v1/auth/password-reset/validate?token=tampered-token")
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_reset_complete_success_invalidates_all_sessions() -> None:
    """Completing a reset invalidates all existing sessions (US-107)."""
    from app.auth.tokens import generate_reset_token, hash_token
    from datetime import datetime, timedelta, timezone
    from app.db.base import async_session_factory
    from app.models.password_reset_token import PasswordResetToken
    from app.models.user import User
    from sqlalchemy import select

    email = "resetcomplete@example.com"
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        # Register + login to get a session
        login_r = await c.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "correcthorsebattery1"},
        )
        old_session_token = login_r.cookies["session"]

        # Create a reset token directly in DB
        async with async_session_factory() as db:
            result = await db.execute(select(User).where(User.email == email))
            user = result.scalar_one()
            token = generate_reset_token()
            prt = PasswordResetToken(
                user_id=user.id,
                token_hash=hash_token(token),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            )
            db.add(prt)
            await db.commit()

        # Complete the reset
        r = await c.post(
            "/api/v1/auth/password-reset/complete",
            json={"token": token, "new_password": "newpassword123456"},
        )
        assert r.status_code == 200

        # Old session must be invalidated
        c.cookies.set("session", old_session_token)
        session_r = await c.get("/api/v1/auth/session")
    assert session_r.status_code == 401


@pytest.mark.asyncio
async def test_reset_complete_used_token_rejected(client: AsyncClient) -> None:
    """Re-using a reset token returns an error."""
    from app.auth.tokens import generate_reset_token, hash_token
    from datetime import datetime, timedelta, timezone
    from app.db.base import async_session_factory
    from app.models.password_reset_token import PasswordResetToken
    from app.models.user import User
    from sqlalchemy import select

    email = "tokenreuse@example.com"
    async with client as c:
        await c.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "correcthorsebattery1"},
        )
        async with async_session_factory() as db:
            result = await db.execute(select(User).where(User.email == email))
            user = result.scalar_one()
            token = generate_reset_token()
            prt = PasswordResetToken(
                user_id=user.id,
                token_hash=hash_token(token),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            )
            db.add(prt)
            await db.commit()

        # First use: success
        r1 = await c.post(
            "/api/v1/auth/password-reset/complete",
            json={"token": token, "new_password": "newpassword123456"},
        )
        assert r1.status_code == 200

        # Second use: error
        r2 = await c.post(
            "/api/v1/auth/password-reset/complete",
            json={"token": token, "new_password": "anotherpassword123"},
        )
    assert r2.status_code == 400
