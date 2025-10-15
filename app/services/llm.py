"""LLM integration layer for menu extraction."""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, List, Sequence

from openai import AsyncOpenAI, OpenAIError

from app.config import settings
from app.schemas import MenuDish, MenuSection, MenuTemplate
from app.services.prompt import (
    build_prompt,
    build_reasoning_config,
    build_text_config,
)

@dataclass(frozen=True)
class MenuGenerationResult:
    """Structured result produced by the LLM generation flow."""

    template: MenuTemplate


class LLMMenuService:
    """Service responsible for converting menu images into structured templates."""

    def __init__(
        self,
        client: AsyncOpenAI | None = None,
    ) -> None:
        self._client = client

    @property
    def client(self) -> AsyncOpenAI:
        """Lazily instantiate an OpenAI client."""

        if self._client is None:
            if not settings.openai_api_key:
                raise RuntimeError("OPENAI_API_KEY is required to process menus")
            self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        return self._client

    async def generate_menu_template(
        self,
        images: Sequence[bytes],
        filenames: Sequence[str] | None = None,
        content_types: Sequence[str] | None = None,
        *,
        output_language: str | None = None,
    ) -> MenuGenerationResult:
        """Invoke the multimodal LLM and coerce the response into a template."""

        if not images:
            raise ValueError("At least one image is required")

        file_ids = await self._upload_images(images, filenames, content_types)
        try:
            payload = await self._run_extract_request(file_ids, output_language or settings.default_output_language)
        except OpenAIError as exc:  # pragma: no cover - network failure path
            raise RuntimeError("Failed to call OpenAI API") from exc
        finally:
            await self._delete_files(file_ids)

        template = _build_menu_template(payload)
        return MenuGenerationResult(template=template)

    async def generate_quick_suggestions(
        self,
        images: Sequence[bytes],
        filenames: Sequence[str] | None = None,
        content_types: Sequence[str] | None = None,
        *,
        output_language: str | None = None,
    ) -> str:
        """Produce a short, friendly intro of dishes quickly.

        Uses a fast, lightweight model with minimal reasoning to surface
        a handful of dish suggestions while the full extraction runs.
        Returns a plain text snippet suitable for inline display.
        """

        if not images:
            raise ValueError("At least one image is required")

        file_ids = await self._upload_images(images, filenames, content_types)
        try:
            text = await self._run_quick_suggest_request(
                file_ids,
                output_language or settings.default_output_language,
            )
        except OpenAIError as exc:  # pragma: no cover - network failure path
            raise RuntimeError("Failed to call OpenAI API for suggestions") from exc
        finally:
            await self._delete_files(file_ids)

        return text

    async def _upload_images(
        self,
        images: Sequence[bytes],
        filenames: Sequence[str] | None,
        content_types: Sequence[str] | None,
    ) -> List[str]:
        """Upload images to the Files API and return file IDs."""

        uploads = []
        for index, raw in enumerate(images):
            name = (
                filenames[index]
                if filenames and index < len(filenames)
                else f"menu-page-{index + 1}.jpg"
            )
            content_type = (
                content_types[index]
                if content_types and index < len(content_types)
                else "image/jpeg"
            )
            uploads.append(
                self.client.files.create(
                    file=(name, raw, content_type),
                    purpose="vision",
                )
            )

        results = await asyncio.gather(*uploads)
        return [upload.id for upload in results]

    async def _delete_files(self, file_ids: Iterable[str]) -> None:
        if not file_ids:
            return

        async def _delete(file_id: str) -> None:
            try:
                await self.client.files.delete(file_id)
            except OpenAIError:  # pragma: no cover - best effort cleanup
                pass

        await asyncio.gather(
            *(_delete(file_id) for file_id in file_ids),
            return_exceptions=True,
        )


    async def _run_extract_request(self, file_ids: Sequence[str], output_language: str) -> str:
        """Run pipeline to collect menu information."""

        if not file_ids:
            return ""

        prompt = build_prompt(file_ids, output_language=output_language)

        response = await self.client.responses.create(
            model=settings.openai_model,
            instructions=prompt.instructions,
            input=[{"role": "user", "content": prompt.content}],
            text=build_text_config(),
            reasoning=build_reasoning_config(),
        )

        return _extract_json_payload(response)

    async def _run_quick_suggest_request(
        self, file_ids: Sequence[str], output_language: str
    ) -> str:
        """Call fast model to produce a brief textual suggestion.

        Keeps the prompt small and uses minimal reasoning for latency.
        """
        if not file_ids:
            return ""

        # Keep this lightweight: a short instruction and the images.
        instructions = (
            f"You are a local resident and I'm your friend."
            f"Any recommendations in this menu? answer using {output_language} "
            "Use emoji to make it more engaging. Don't ask me any questions in the end. "
        )

        content: List[dict[str, str]] = [
            {
                "type": "input_text",
                "text": f"answer using {output_language}",
            }
        ]
        for file_id in file_ids:
            content.append({"type": "input_image", "file_id": file_id})

        response = await self.client.responses.create(
            model="gpt-5-nano",  # fast, low-latency model for side-call
            instructions=instructions,
            input=[{"role": "user", "content": content}],
            text={"verbosity": "medium"},
            reasoning={"effort": "minimal"},
        )

        return _extract_output_text(response)


def _extract_json_payload(response: object) -> dict:
    """Traverse the responses API payload to pull JSON content."""

    output_text = _extract_output_text(response)
    return json.loads(output_text)


def _extract_output_text(response: object) -> str:
    """Return the textual content for a Responses API call."""

    try:
        output_text = response.output_text  # type: ignore[attr-defined]
    except AttributeError as exc:  # pragma: no cover - defensive guard
        raise RuntimeError("OpenAI response missing output_text") from exc

    if not output_text:
        raise RuntimeError("OpenAI response returned empty output_text")
    return str(output_text).strip()


def _build_menu_template(payload: dict) -> MenuTemplate:
    """Convert the raw payload into the MenuTemplate structure."""

    if not isinstance(payload, dict) or "items" not in payload:
        raise RuntimeError(f"OpenAI response missing 'items' payload: {payload}")

    sections: defaultdict[str, List[MenuDish]] = defaultdict(list)
    for item in payload.get("items", []):
        if not isinstance(item, dict):
            continue

        section = str(item.get("section") or "Menu")
        original_name = str(item.get("original_name") or "").strip()
        translated_name = str(item.get("translated_name") or "").strip()
        description = str(item.get("description") or "").strip()
        price = _format_price(item.get("price"))

        if not original_name or not translated_name or not description:
            continue

        sections[section].append(
            MenuDish(
                original_name=original_name,
                translated_name=translated_name,
                description=description,
                price=price,
            )
        )

    section_models = [
        MenuSection(title=title, dishes=dishes) for title, dishes in sections.items()
    ]

    return MenuTemplate(sections=section_models)


def _format_price(value: object) -> str | None:
    """Format numeric prices into display-friendly strings."""

    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, int) or (
            hasattr(value, "is_integer") and value.is_integer()
        ):
            return f"{int(value)}"
        return f"{value:.2f}"
    return str(value)
