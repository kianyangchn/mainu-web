"""Share token service with in-memory and Postgres backends."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Tuple, Any, Optional

from sqlalchemy import DateTime, String, delete, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from app.config import settings
from app.db import Base, get_session_factory
from app.schemas import MenuTemplate


@dataclass(frozen=True)
class ShareRecord:
    """Metadata about a stored share token."""

    token: str
    template: MenuTemplate
    created_at: datetime
    expires_at: datetime

    @property
    def ttl_seconds(self) -> int:
        """Return remaining lifetime in whole seconds."""

        remaining = (self.expires_at - datetime.now(tz=timezone.utc)).total_seconds()
        return int(remaining) if remaining > 0 else 0


class ShareToken(Base):
    """SQLAlchemy mapping for persisted share tokens."""

    __tablename__ = "share_tokens"

    token: Mapped[str] = mapped_column(String(96), primary_key=True)
    template_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class InMemoryShareRepository:
    """Ephemeral repository used when no database is available."""

    def __init__(self) -> None:
        self._store: Dict[str, Tuple[MenuTemplate, datetime, datetime]] = {}

    async def store(
        self,
        token: str,
        template: MenuTemplate,
        created_at: datetime,
        expires_at: datetime,
    ) -> None:
        self._store[token] = (template, created_at, expires_at)

    async def fetch(self, token: str) -> ShareRecord | None:
        record = self._store.get(token)
        if not record:
            return None
        template, created_at, expires_at = record
        if datetime.now(tz=timezone.utc) > expires_at:
            self._store.pop(token, None)
            return None
        return ShareRecord(token, template, created_at, expires_at)

    async def purge(self) -> None:
        now = datetime.now(tz=timezone.utc)
        expired = [key for key, (_, _, expires_at) in self._store.items() if expires_at <= now]
        for key in expired:
            self._store.pop(key, None)

    def reset(self) -> None:
        self._store.clear()


class DatabaseShareRepository:
    """Persist share tokens in Postgres via SQLAlchemy."""

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    async def store(
        self,
        token: str,
        template: MenuTemplate,
        created_at: datetime,
        expires_at: datetime,
    ) -> None:
        async with self._session_factory() as session:
            record = ShareToken(
                token=token,
                template_json=template.model_dump(),
                created_at=created_at,
                expires_at=expires_at,
            )
            session.add(record)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                raise

    async def fetch(self, token: str) -> ShareRecord | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(ShareToken).where(ShareToken.token == token)
            )
            row: Optional[ShareToken] = result.scalar_one_or_none()
            if row is None:
                return None
            now = datetime.now(tz=timezone.utc)
            if row.expires_at <= now:
                await session.delete(row)
                await session.commit()
                return None
            template = MenuTemplate.model_validate(row.template_json)
            return ShareRecord(row.token, template, row.created_at, row.expires_at)

    async def purge(self) -> None:
        async with self._session_factory() as session:
            await session.execute(
                delete(ShareToken).where(ShareToken.expires_at <= datetime.now(tz=timezone.utc))
            )
            await session.commit()

    def reset(self) -> None:  # pragma: no cover - used only in tests
        """Database-backed stores do not support sync resets."""

        # Intentional no-op; tests rely on the in-memory backend.
        pass


class ShareService:
    """Store menu templates behind expiring share tokens."""

    def __init__(self) -> None:
        self._ttl = timedelta(minutes=settings.share_token_ttl_minutes)
        session_factory = get_session_factory()
        if session_factory is not None:
            self._repository = DatabaseShareRepository(session_factory)
        else:
            self._repository = InMemoryShareRepository()

    async def create_template(self, template: MenuTemplate) -> str:
        """Generate a token and persist the template."""

        token = _generate_token()
        created_at = datetime.now(tz=timezone.utc)
        expires_at = created_at + self._ttl
        await self._repository.store(token, template, created_at, expires_at)
        return token

    async def describe(self, token: str) -> ShareRecord | None:
        """Return metadata for a token when it is still valid."""

        return await self._repository.fetch(token)

    async def fetch_template(self, token: str) -> MenuTemplate | None:
        """Retrieve a template for active tokens."""

        record = await self.describe(token)
        return record.template if record else None

    async def purge_expired(self) -> None:
        """Remove expired templates eagerly."""

        await self._repository.purge()

    def reset(self) -> None:
        """Utility for tests to clear stored templates."""

        reset_fn = getattr(self._repository, "reset", None)
        if callable(reset_fn):
            reset_fn()


def _generate_token() -> str:
    from secrets import token_urlsafe

    return token_urlsafe(12)
