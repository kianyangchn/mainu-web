"""Internationalisation helpers for template rendering."""

from __future__ import annotations

import gettext
from gettext import gettext as _
from functools import lru_cache
from pathlib import Path
from typing import Callable, Iterable, Tuple

DEFAULT_LOCALE = "en"
SUPPORTED_LOCALES = ("en", "zh_Hans", "zh_Hant")
_HTML_LANG_CODES = {
    "en": "en",
    "zh_Hans": "zh-Hans",
    "zh_Hant": "zh-Hant",
}
_UI_LANGUAGE_LABELS = {
    "en": _("English"),
    "zh_Hans": _("简体中文"),
    "zh_Hant": _("繁體中文"),
}


def negotiate_locale(accept_language_header: str | None) -> str:
    """Pick the best supported locale from the Accept-Language header."""
    if not accept_language_header:
        return DEFAULT_LOCALE

    for tag, _quality in _parse_accept_language(accept_language_header):
        normalized = _map_to_supported_locale(tag)
        if normalized:
            return normalized
    return DEFAULT_LOCALE


def determine_locale(
    cookie_locale: str | None, accept_language_header: str | None
) -> str:
    """Resolve the UI locale from cookie overrides or Accept-Language."""
    normalized = normalize_locale(cookie_locale)
    if normalized:
        return normalized
    return negotiate_locale(accept_language_header)


def get_html_lang(locale: str) -> str:
    """Return the lang attribute value for the given locale."""
    return _HTML_LANG_CODES.get(locale, "en")


def normalize_locale(selection: str | None) -> str | None:
    """Normalise a locale selection into a supported value."""
    if not selection:
        return None
    selection = selection.strip()
    if not selection:
        return None
    if selection in SUPPORTED_LOCALES:
        return selection
    return _map_to_supported_locale(selection)


def get_gettext_functions(locale: str) -> Tuple[Callable[[str], str], Callable[[str, str, int], str]]:
    """Return gettext/ngettext callables for the requested locale."""
    translations = _load_translations(locale)
    return translations.gettext, translations.ngettext


@lru_cache(maxsize=None)
def _load_translations(locale: str) -> gettext.NullTranslations:
    localedir = Path(__file__).parent / "locales"
    return gettext.translation(
        "messages",
        localedir=str(localedir),
        languages=[locale],
        fallback=True,
    )


def _parse_accept_language(header_value: str) -> Iterable[Tuple[str, float]]:
    parts = [segment.strip() for segment in header_value.split(",") if segment.strip()]
    preferences: list[tuple[str, float, int]] = []
    for index, part in enumerate(parts):
        if ";" not in part:
            preferences.append((part, 1.0, index))
            continue
        tag, *params = [item.strip() for item in part.split(";") if item.strip()]
        quality = 1.0
        for param in params:
            if param.startswith("q="):
                try:
                    quality = float(param[2:]) if len(param) > 2 else 0.0
                except ValueError:
                    quality = 0.0
        preferences.append((tag, quality, index))
    ordered = sorted(preferences, key=lambda item: (-item[1], item[2]))
    return [(tag, quality) for tag, quality, _index in ordered]


def _map_to_supported_locale(tag: str) -> str | None:
    cleaned = tag.strip().replace("_", "-").lower()
    if not cleaned:
        return None

    if cleaned.startswith("en"):
        return "en"

    if cleaned.startswith("zh"):
        if "hant" in cleaned or cleaned.endswith("-tw") or cleaned.endswith("-hk") or cleaned.endswith("-mo"):
            return "zh_Hant"
        return "zh_Hans"

    return None


def list_supported_ui_locales() -> list[tuple[str, str]]:
    """Return configured UI locales with their display labels."""
    return [(code, _UI_LANGUAGE_LABELS.get(code, code)) for code in SUPPORTED_LOCALES]


def is_supported_locale(locale: str | None) -> bool:
    return bool(locale and locale in SUPPORTED_LOCALES)


def get_locale_label(locale: str) -> str:
    return _UI_LANGUAGE_LABELS.get(locale, locale)
