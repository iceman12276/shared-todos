"""Rate limiting integration test: 11th failed login attempt → 429 (US-102)."""
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

BASE = "http://test"


@pytest.mark.asyncio
async def test_rate_limit_on_11th_failed_login() -> None:
    """After 10 failed attempts from the same IP, the 11th must return 429."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as client:
        # Register a real user so we don't get 401 before rate limit
        await client.post(
            "/api/v1/auth/register",
            json={"email": "ratelimit@example.com", "password": "correcthorsebattery1"},
        )
        for _ in range(10):
            r = await client.post(
                "/api/v1/auth/login",
                json={"email": "ratelimit@example.com", "password": "wrongpassword123"},
            )
            assert r.status_code == 401

        r11 = await client.post(
            "/api/v1/auth/login",
            json={"email": "ratelimit@example.com", "password": "wrongpassword123"},
        )
    assert r11.status_code == 429
