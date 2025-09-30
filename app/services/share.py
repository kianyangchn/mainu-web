"""In-memory share token service."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, Tuple

from app.config import settings
from app.schemas import MenuTemplate


class ShareService:
    """Store menu templates behind expiring share tokens."""

    def __init__(self) -> None:
        self._templates: Dict[str, Tuple[MenuTemplate, datetime]] = {}
        self._ttl = timedelta(minutes=settings.share_token_ttl_minutes)

    def store_template(self, token: str, template: MenuTemplate) -> None:
        """Persist the template with a known token."""

        self._templates[token] = (template, datetime.now(tz=timezone.utc))

    def create_template(self, template: MenuTemplate) -> str:
        """Generate a token and persist the template."""

        token = _generate_token()
        self.store_template(token, template)
        return token

    def fetch_template(self, token: str) -> MenuTemplate | None:
        """Retrieve a template, expiring stale entries."""

        record = self._templates.get(token)
        if not record:
            return None
        template, created_at = record
        if datetime.now(tz=timezone.utc) - created_at > self._ttl:
            self._templates.pop(token, None)
            return None
        return template

    def purge_expired(self) -> None:
        """Remove expired templates eagerly."""

        now = datetime.now(tz=timezone.utc)
        expired = [
            key
            for key, (_, created) in self._templates.items()
            if now - created > self._ttl
        ]
        for key in expired:
            self._templates.pop(key, None)

    def reset(self) -> None:
        """Utility for tests to clear stored templates."""

        self._templates.clear()


def _generate_token() -> str:
    from secrets import token_urlsafe

    return token_urlsafe(12)
