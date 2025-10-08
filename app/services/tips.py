"""Travel and cuisine tip service for enhancing loading experiences."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional

import httpx
from openai import AsyncOpenAI, OpenAIError

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Tip:
    """Structured payload describing a single loading-state insight."""

    title: str
    body: str
    image_url: str | None = None
    source_name: str | None = None
    source_url: str | None = None


class WikivoyageProvider:
    """Fetch cuisine tips from the Wikivoyage MediaWiki API."""

    _BASE_URL_TEMPLATE = "https://{lang}.wikivoyage.org/w/api.php"

    def __init__(self, *, timeout: float = 4.0) -> None:
        self._timeout = timeout

    async def fetch(self, topic: str, language: str, *, limit: int = 3) -> List[Tip]:
        """Return a list of Wikivoyage extracts for the requested topic."""

        language_chain = _language_fallback(language)
        for lang in language_chain:
            tips = await self._fetch_for_language(topic, lang, limit=limit)
            if tips:
                return tips
        return []

    async def _fetch_for_language(
        self,
        topic: str,
        language: str,
        *,
        limit: int,
    ) -> List[Tip]:
        url = self._BASE_URL_TEMPLATE.format(lang=language)
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            search_params = {
                "action": "query",
                "format": "json",
                "list": "search",
                "srsearch": topic,
                "srlimit": limit,
                "srwhat": "text",
            }
            search_response = await client.get(url, params=search_params)
            search_response.raise_for_status()
            search_data = search_response.json()
            search_results = search_data.get("query", {}).get("search", [])
            if not search_results:
                return []

            page_ids = [str(result.get("pageid")) for result in search_results if result.get("pageid")]
            if not page_ids:
                return []

            details_params = {
                "action": "query",
                "format": "json",
                "prop": "extracts|pageimages|info",
                "exintro": "",
                "explaintext": "",
                "piprop": "thumbnail",
                "pithumbsize": 640,
                "pilicense": "any",
                "inprop": "url",
                "pageids": "|".join(page_ids[:limit]),
            }
            details_response = await client.get(url, params=details_params)
            details_response.raise_for_status()
            details_data = details_response.json()

        tips: List[Tip] = []
        pages = details_data.get("query", {}).get("pages", {})
        for page in pages.values():
            title = str(page.get("title") or "").strip()
            extract = str(page.get("extract") or "").strip()
            if not title or not extract:
                continue

            body = _truncate(extract, 360)
            thumbnail = _get_nested(page, ["thumbnail", "source"])
            source_url = page.get("fullurl")

            tips.append(
                Tip(
                    title=title,
                    body=body,
                    image_url=thumbnail,
                    source_name=f"Wikivoyage ({language})",
                    source_url=source_url,
                )
            )

        return tips[:limit]


class LLMTipProvider:
    """Generate fallback tips using a lightweight LLM call."""

    def __init__(self, client: AsyncOpenAI | None = None) -> None:
        self._client = client

    @property
    def client(self) -> AsyncOpenAI:
        if self._client is None:
            if not settings.openai_api_key:
                raise RuntimeError("OPENAI_API_KEY is required for LLM tip generation")
            self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        return self._client

    async def generate(
        self,
        topic: str,
        language: str,
        *,
        limit: int,
    ) -> List[Tip]:
        prompt_topic = topic or "travel dining"
        try:
            response = await self.client.responses.create(
                model="gpt-5-nano",
                input=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": (
                                    "Provide concise dining facts or etiquette tips about "
                                    f"{prompt_topic}. Respond in {language}. "
                                    "Return JSON array with up to "
                                    f"{limit} items. Each item must have 'title' and 'body' fields, "
                                    "body <= 35 words."
                                ),
                            }
                        ],
                    }
                ],
                text={"verbosity": "low"},
                max_output_tokens=350,
            )
        except OpenAIError as exc:  # pragma: no cover - network failure path
            logger.warning("LLM tip generation failed: %s", exc)
            return []

        output = _extract_output_text(response)
        try:
            payload = json.loads(output)
        except json.JSONDecodeError:
            logger.debug("Failed to parse LLM tip payload: %s", output)
            return []

        tips: List[Tip] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            body = str(item.get("body") or "").strip()
            if not title or not body:
                continue
            tips.append(Tip(title=title, body=body))

        return tips[:limit]


class TipService:
    """Aggregate provider that caches tips for a topic and language."""

    def __init__(
        self,
        wiki_provider: WikivoyageProvider | None = None,
        llm_provider: LLMTipProvider | None = None,
        *,
        cache_ttl: timedelta | None = None,
    ) -> None:
        self._wiki = wiki_provider or WikivoyageProvider()
        self._llm = llm_provider or LLMTipProvider()
        self._cache_ttl = cache_ttl or timedelta(hours=6)
        self._cache: Dict[tuple[str, str], tuple[datetime, List[Tip]]] = {}

    async def get_tips(
        self,
        topic: str | None,
        language: str | None,
        *,
        limit: int = 6,
    ) -> List[Tip]:
        key = self._cache_key(topic, language)
        cached = self._cache.get(key)
        now = datetime.utcnow()
        if cached and now - cached[0] < self._cache_ttl:
            return cached[1][:limit]

        topic_name = topic or "global cuisine"
        lang = _normalise_language(language)

        results: List[Tip] = []
        wiki_task = asyncio.create_task(
            self._wiki.fetch(topic_name, lang, limit=min(3, limit))
        )
        wiki_tips: List[Tip] = []
        try:
            wiki_tips = await wiki_task
        except (httpx.HTTPError, asyncio.TimeoutError) as exc:
            logger.info("Wikivoyage tips failed: %s", exc)

        results.extend(wiki_tips)

        if len(results) < limit:
            try:
                llm_tips = await self._llm.generate(
                    topic_name,
                    language or "English",
                    limit=limit - len(results),
                )
            except RuntimeError:
                llm_tips = []
            results.extend(llm_tips)

        if len(results) < limit:
            results.extend(self._fallback_tips(language, limit=limit - len(results)))

        trimmed = results[:limit]
        self._cache[key] = (now, trimmed)
        return trimmed

    def _cache_key(self, topic: str | None, language: str | None) -> tuple[str, str]:
        normalised_topic = (topic or "global").strip().lower()
        normalised_lang = _normalise_language(language)
        return normalised_topic, normalised_lang

    def _fallback_tips(self, language: str | None, *, limit: int) -> List[Tip]:
        if limit <= 0:
            return []

        language_hint = (language or "").split("-")[0].lower()
        basics = [
            Tip(
                title="Check the menu",
                body="Ask which dishes are the restaurant's signature and whether there are seasonal specials tonight.",
            ),
            Tip(
                title="Mind local etiquette",
                body="Observe how locals share plates and pace courses; matching their rhythm is usually appreciated.",
            ),
            Tip(
                title="Payments",
                body="Carry a small amount of local currency in case the card terminal is offline or tips are cash only.",
            ),
            Tip(
                title="Dietary callouts",
                body="Flag allergies early—mention them when you order and again when dishes arrive to avoid surprises.",
            ),
            Tip(
                title="Phrase to try",
                body="Learn one polite ordering phrase in the local language; staff respond warmly to the effort.",
            ),
        ]

        if language_hint in {"ja", "ko", "zh"}:
            basics.append(
                Tip(
                    title="Share-style dining",
                    body="Meals often arrive family-style; plan to order extra dishes for the table rather than one per person.",
                )
            )

        return basics[:limit]


def _language_fallback(language: str | None) -> Iterable[str]:
    primary = _normalise_language(language)
    if primary == "en":
        return ("en",)
    return (primary, "en")


def _normalise_language(language: str | None) -> str:
    if not language:
        return "en"
    return language.split("-")[0].lower() or "en"


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    trimmed = value[: limit - 1].rsplit(" ", 1)[0]
    return f"{trimmed}…"


def _get_nested(data: Dict[str, Any], path: List[str]) -> Optional[str]:
    cursor: Any = data
    for key in path:
        if not isinstance(cursor, dict):
            return None
        cursor = cursor.get(key)
    if isinstance(cursor, str):
        return cursor
    return None


def _extract_output_text(response: object) -> str:
    try:
        output_text = response.output_text  # type: ignore[attr-defined]
    except AttributeError as exc:  # pragma: no cover - defensive guard
        raise RuntimeError("OpenAI response missing output_text") from exc

    if not output_text:
        raise RuntimeError("OpenAI response returned empty output_text")
    return str(output_text).strip()
