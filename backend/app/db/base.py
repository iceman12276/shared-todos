from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# Normalize sync psycopg3 URL to async dialect (CI sets postgresql+psycopg://).
_db_url = settings.database_url.replace("postgresql+psycopg://", "postgresql+psycopg_async://")

_engine = create_async_engine(_db_url, echo=False)

async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    _engine, expire_on_commit=False
)


class Base(DeclarativeBase):
    pass
