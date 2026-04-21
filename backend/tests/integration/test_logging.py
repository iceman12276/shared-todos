"""Integration tests for logging infrastructure.

Verifies:
- App startup wires the root logger (configure_logging called in lifespan)
- Auth event loggers emit records at INFO on key flows
"""

import logging

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

BASE = "http://test"


@pytest.mark.asyncio
async def test_startup_configures_root_logger(caplog: pytest.LogCaptureFixture) -> None:
    """Root logger must be at INFO or lower after app startup."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        r = await c.get("/health")
    assert r.status_code == 200
    assert logging.getLogger().level <= logging.INFO


@pytest.mark.asyncio
async def test_register_emits_auth_log(caplog: pytest.LogCaptureFixture) -> None:
    """Successful register must emit an INFO record on app.auth logger."""
    with caplog.at_level(logging.INFO, logger="app.auth"):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
            r = await c.post(
                "/api/v1/auth/register",
                json={"email": "logtest@example.com", "password": "correcthorse1"},
            )
    assert r.status_code == 201
    auth_records = [r for r in caplog.records if r.name.startswith("app.auth")]
    assert any("register" in r.message.lower() for r in auth_records)


@pytest.mark.asyncio
async def test_login_failure_emits_auth_log(caplog: pytest.LogCaptureFixture) -> None:
    """Failed login must emit a WARNING record on app.auth logger."""
    with caplog.at_level(logging.WARNING, logger="app.auth"):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
            r = await c.post(
                "/api/v1/auth/login",
                json={"email": "nobody@example.com", "password": "wrongpass1"},
            )
    assert r.status_code == 401
    auth_records = [r for r in caplog.records if r.name.startswith("app.auth")]
    assert any("login" in r.message.lower() for r in auth_records)
