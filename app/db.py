"""Database utilities for async SQLAlchemy access."""

from __future__ import annotations

from typing import AsyncIterator

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from app.config import settings

Base = declarative_base()

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None

def _ensure_async_driver(raw_url: str) -> str:
    """Return a SQLAlchemy URL string using an async driver when possible."""

    url = make_url(raw_url)
    backend = url.get_backend_name()
    drivername = url.drivername

    if backend in {"postgresql", "postgres"} and "+asyncpg" not in drivername:
        drivername = f"{backend}+asyncpg"
        url = url.set(drivername=drivername)

    return url.render_as_string(hide_password=False)


if settings.database_url:
    normalised_url = _ensure_async_driver(settings.database_url)
    _engine = create_async_engine(normalised_url, pool_pre_ping=True)
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
