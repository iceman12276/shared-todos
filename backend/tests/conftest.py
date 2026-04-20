from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.db.base import _engine


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest_asyncio.fixture(scope="session")
async def db_engine() -> AsyncGenerator[AsyncEngine, None]:
    yield _engine
    await _engine.dispose()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(_engine, expire_on_commit=False)
    async with factory() as session:
        yield session
        # Truncate auth tables after each test for isolation.
        # CASCADE handles FK order automatically.
        await session.execute(
            text(
                "TRUNCATE TABLE sessions, password_reset_tokens, users RESTART IDENTITY CASCADE"
            )
        )
        await session.commit()
