"""Upload session persistence for reusing OpenAI file IDs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import DateTime, Integer, String, delete, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.config import settings
from app.db import Base, get_session_factory


@dataclass(frozen=True)
class UploadSessionRecord:
    """Persisted metadata required to reuse uploaded files."""

    token: str
    file_ids: List[str]
    filenames: List[str]
    content_types: List[str]
    created_at: datetime
    expires_at: datetime
    retry_count: int = 0

    @property
    def ttl_seconds(self) -> int:
        """Return remaining lifetime in seconds."""

        remaining = (self.expires_at - datetime.now(tz=timezone.utc)).total_seconds()
        return int(remaining) if remaining > 0 else 0


class UploadSession(Base):
    """SQLAlchemy mapping for persisted upload sessions."""

    __tablename__ = "upload_sessions"

    token: Mapped[str] = mapped_column(String(96), primary_key=True)
    file_ids: Mapped[List[str]] = mapped_column(JSONB, nullable=False)
    filenames: Mapped[List[str]] = mapped_column(JSONB, nullable=False)
    content_types: Mapped[List[str]] = mapped_column(JSONB, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class InMemoryUploadRepository:
    """Ephemeral backing store used for local development and tests."""

    def __init__(self) -> None:
        self._store: Dict[str, Tuple[UploadSessionRecord, datetime]] = {}

    async def store(self, record: UploadSessionRecord) -> None:
        self._store[record.token] = (record, record.expires_at)

    async def fetch(self, token: str) -> UploadSessionRecord | None:
        entry = self._store.get(token)
        if not entry:
            return None
        record, expires_at = entry
        if expires_at <= datetime.now(tz=timezone.utc):
            self._store.pop(token, None)
            return None
        return record

    async def delete(self, token: str) -> None:
        self._store.pop(token, None)

    async def purge(self) -> List[UploadSessionRecord]:
        now = datetime.now(tz=timezone.utc)
        expired_records: List[UploadSessionRecord] = []
        expired_tokens = [
            token for token, (_, expires_at) in self._store.items() if expires_at <= now
        ]
        for token in expired_tokens:
            record_tuple = self._store.pop(token, None)
            if record_tuple:
                expired_records.append(record_tuple[0])
        return expired_records

    async def increment_retry(self, token: str) -> int:
        entry = self._store.get(token)
        if not entry:
            raise KeyError(token)
        record, expires_at = entry
        updated = UploadSessionRecord(
            token=record.token,
            file_ids=record.file_ids,
            filenames=record.filenames,
            content_types=record.content_types,
            created_at=record.created_at,
            expires_at=record.expires_at,
            retry_count=record.retry_count + 1,
        )
        self._store[token] = (updated, expires_at)
        return updated.retry_count

    def reset(self) -> None:  # pragma: no cover - test helper
        self._store.clear()


class DatabaseUploadRepository:
    """Persist upload sessions in Postgres."""

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    async def store(self, record: UploadSessionRecord) -> None:
        async with self._session_factory() as session:
            row = UploadSession(
                token=record.token,
                file_ids=record.file_ids,
                filenames=record.filenames,
                content_types=record.content_types,
                retry_count=record.retry_count,
                created_at=record.created_at,
                expires_at=record.expires_at,
            )
            session.add(row)
            await session.commit()

    async def fetch(self, token: str) -> UploadSessionRecord | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(UploadSession).where(UploadSession.token == token)
            )
            row: Optional[UploadSession] = result.scalar_one_or_none()
            if row is None:
                return None
            now = datetime.now(tz=timezone.utc)
            if row.expires_at <= now:
                await session.delete(row)
                await session.commit()
                return None
            return UploadSessionRecord(
                token=row.token,
                file_ids=list(row.file_ids),
                filenames=list(row.filenames),
                content_types=list(row.content_types),
                created_at=row.created_at,
                expires_at=row.expires_at,
                retry_count=row.retry_count,
            )

    async def delete(self, token: str) -> None:
        async with self._session_factory() as session:
            await session.execute(
                delete(UploadSession).where(UploadSession.token == token)
            )
            await session.commit()

    async def purge(self) -> List[UploadSessionRecord]:
        async with self._session_factory() as session:
            now = datetime.now(tz=timezone.utc)
            result = await session.execute(
                select(UploadSession).where(UploadSession.expires_at <= now)
            )
            rows = result.scalars().all()
            if not rows:
                return []
            await session.execute(
                delete(UploadSession).where(UploadSession.expires_at <= now)
            )
            await session.commit()
            return [
                UploadSessionRecord(
                    token=row.token,
                    file_ids=list(row.file_ids),
                    filenames=list(row.filenames),
                    content_types=list(row.content_types),
                    created_at=row.created_at,
                    expires_at=row.expires_at,
                    retry_count=row.retry_count,
                )
                for row in rows
            ]

    async def increment_retry(self, token: str) -> int:
        async with self._session_factory() as session:
            result = await session.execute(
                update(UploadSession)
                .where(UploadSession.token == token)
                .values(retry_count=UploadSession.retry_count + 1)
                .returning(UploadSession.retry_count)
            )
            row = result.first()
            if row is None:
                raise KeyError(token)
            await session.commit()
            return int(row[0])

    def reset(self) -> None:  # pragma: no cover - tests rely on memory store
        pass


class UploadSessionService:
    """High-level coordinator for upload session persistence."""

    def __init__(self) -> None:
        self._ttl = timedelta(minutes=max(1, settings.upload_session_ttl_minutes))
        session_factory = get_session_factory()
        if session_factory is not None:
            self._repository: InMemoryUploadRepository | DatabaseUploadRepository = (
                DatabaseUploadRepository(session_factory)
            )
        else:
            self._repository = InMemoryUploadRepository()

    async def create_session(
        self,
        file_ids: Sequence[str],
        filenames: Sequence[str],
        content_types: Sequence[str],
    ) -> str:
        token = _generate_token()
        created_at = datetime.now(tz=timezone.utc)
        expires_at = created_at + self._ttl
        record = UploadSessionRecord(
            token=token,
            file_ids=list(file_ids),
            filenames=list(filenames),
            content_types=list(content_types),
            created_at=created_at,
            expires_at=expires_at,
            retry_count=0,
        )
        await self._repository.store(record)
        return token

    async def describe(self, token: str) -> UploadSessionRecord | None:
        return await self._repository.fetch(token)

    async def increment_retry(self, token: str) -> int:
        return await self._repository.increment_retry(token)

    async def delete(self, token: str) -> None:
        await self._repository.delete(token)

    async def purge_expired(self) -> List[UploadSessionRecord]:
        return await self._repository.purge()

    def reset(self) -> None:  # pragma: no cover - tests only
        reset_fn = getattr(self._repository, "reset", None)
        if callable(reset_fn):
            reset_fn()


def _generate_token() -> str:
    from secrets import token_urlsafe

    return token_urlsafe(16)
