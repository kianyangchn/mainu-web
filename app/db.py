"""Database utilities for async SQLAlchemy access."""

from __future__ import annotations

from typing import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base

from app.config import settings

Base = declarative_base()

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None

if settings.database_url:
    _engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)


def get_engine() -> AsyncEngine | None:
    """Return the configured async engine, if a database URL is set."""

    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession] | None:
    """Return the async session factory when database access is available."""

    return _session_factory


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency for acquiring an async session."""

    if _session_factory is None:
        raise RuntimeError(
            "Database access requested but DATABASE_URL is not configured."
        )

    async with _session_factory() as session:
        yield session
