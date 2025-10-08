"""Lightweight reverse geocoding service for contextual tips."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Place:
    """Structured city/country pair returned by reverse geocoding."""

    city: str | None
    country: str | None


class LocationService:
    """Fetch human-readable places using the public Nominatim API."""

    _BASE_URL = "https://nominatim.openstreetmap.org/reverse"

    def __init__(self, *, timeout: float = 4.0, cache_ttl: timedelta | None = None) -> None:
        self._timeout = timeout
        self._cache_ttl = cache_ttl or timedelta(hours=6)
        self._cache: Dict[Tuple[float, float], Tuple[datetime, Place]] = {}
        self._lock = asyncio.Lock()

    async def reverse_geocode(self, latitude: float, longitude: float) -> Place:
        """Return the nearest city/country for the provided co-ordinates."""

        key = (round(latitude, 3), round(longitude, 3))
        async with self._lock:
            cached = self._cache.get(key)
            if cached and datetime.utcnow() - cached[0] <= self._cache_ttl:
                return cached[1]

        params = {
            "lat": f"{latitude:.6f}",
            "lon": f"{longitude:.6f}",
            "format": "json",
            "addressdetails": 1,
        }
        headers = {
            "User-Agent": "mainu-web/0.1 (https://mainu.app)",
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout, headers=headers) as client:
                response = await client.get(self._BASE_URL, params=params)
                response.raise_for_status()
        except httpx.HTTPError as exc:  # pragma: no cover - network failure path
            logger.info("Reverse geocode failed: %s", exc)
            place = Place(city=None, country=None)
        else:
            payload = response.json()
            address = payload.get("address") or {}
            place = Place(
                city=_extract_city(address),
                country=_safe_str(address.get("country")),
            )

        async with self._lock:
            self._cache[key] = (datetime.utcnow(), place)
        return place


def _extract_city(address: dict) -> Optional[str]:
    for field in ("city", "town", "village", "municipality", "county", "state"):
        value = address.get(field)
        if value:
            text = _safe_str(value)
            if text:
                return text
    return None


def _safe_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
