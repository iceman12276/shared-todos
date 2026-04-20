from collections.abc import AsyncGenerator
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, MetaData, Uuid
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# Standard constraint naming so Alembic autogenerate produces consistent names.
_naming_convention: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

_engine = create_async_engine(settings.database_url, echo=False)

async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    _engine, expire_on_commit=False
)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=_naming_convention)
    type_annotation_map = {
        UUID: Uuid(as_uuid=True),
        datetime: DateTime(timezone=True),
    }


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields one AsyncSession per request.

    Caller MUST explicitly ``await session.commit()`` to persist changes.
    Uncaught exceptions trigger rollback automatically via the async context manager.
    The framework manages the lifecycle; do not close the session manually.
    """
    async with async_session_factory() as session:
        yield session
