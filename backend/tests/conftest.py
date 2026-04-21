from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.auth.rate_limiter import _store as _rate_limit_store
from app.db.base import _engine

_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(_engine, expire_on_commit=False)

_TRUNCATE = text("TRUNCATE TABLE sessions, password_reset_tokens, users RESTART IDENTITY CASCADE")


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest_asyncio.fixture(scope="session")
async def db_engine() -> AsyncGenerator[AsyncEngine, None]:
    yield _engine
    await _engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _db_cleanup() -> AsyncGenerator[None, None]:
    """Truncate all auth tables before each test for isolation.

    autouse=True ensures this runs for every test without opt-in.
    Truncating BEFORE (not after) means a crash mid-test doesn't leave
    dirty state for the next run.
    """
    async with _factory() as session:
        await session.execute(_TRUNCATE)
        await session.commit()
    # Reset in-memory rate-limit store so tests don't bleed failed-attempt
    # counts into each other. The store is module-level state; DB truncate
    # alone does not clear it.
    _rate_limit_store.clear()
    yield


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with _factory() as session:
        yield session
