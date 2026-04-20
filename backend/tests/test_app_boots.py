import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.db.base import async_session_factory
from app.main import app


@pytest.mark.asyncio
async def test_health_endpoint_responds_200() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_app_can_connect_to_db() -> None:
    async with async_session_factory() as session:
        result = await session.execute(text("SELECT 1"))
        row = result.scalar()
    assert row == 1
