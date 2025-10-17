"""Static dataset loaders for templates and services."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final, List


_STATIC_ROOT: Final[Path] = Path(__file__).parent / "static"
_MATCHED_PHOTO_PATH: Final[Path] = _STATIC_ROOT / "matched_photo.json"


def _load_matched_photo_feed() -> List[dict[str, Any]]:
    try:
        raw = _MATCHED_PHOTO_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    valid_items: list[dict[str, Any]] = []
    for item in data:
        if isinstance(item, dict) and isinstance(item.get("photo_image_url"), str):
            valid_items.append(item)
    return valid_items


_MATCHED_PHOTO_FEED: Final[List[dict[str, Any]]] = _load_matched_photo_feed()


def get_matched_photo_feed() -> List[dict[str, Any]]:
    """Return the cached matched photo feed loaded at startup."""

    return list(_MATCHED_PHOTO_FEED)

