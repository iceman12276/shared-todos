from collections.abc import AsyncGenerator

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.db.base import _engine


@pytest_asyncio.fixture
async def db_engine() -> AsyncEngine:
    return _engine


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(_engine, expire_on_commit=False)
    async with factory() as session:
        yield session
