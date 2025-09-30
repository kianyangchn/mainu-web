"""LLM integration layer for menu extraction."""

from __future__ import annotations

import base64
import json
from typing import List, Sequence

from openai import AsyncOpenAI, OpenAIError

from app.config import settings
from app.schemas import MenuTemplate

_SYSTEM_PROMPT = (
    "You are mainu, an assistant that reads multi-page restaurant menus and returns "
    "structured JSON ready for translation and sharing. Output must strictly match "
    "the provided JSON schema and preserve original dish names alongside translated "
    "names. Highlight allergens, spice indicators, and recommended pairings when "
    "present."
)

_USER_INSTRUCTIONS = (
    "Analyze the following menu images captured by a traveler. Extract sections and "
    "dishes, provide translated names, descriptions, allergens, spice levels, price "
    "strings, and recommended pairings when discoverable. Return only JSON—no prose."
)


class LLMMenuService:
    """Service responsible for converting menu images into structured templates."""

    def __init__(self, client: AsyncOpenAI | None = None) -> None:
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
        self, images: Sequence[bytes], filenames: Sequence[str] | None = None
    ) -> MenuTemplate:
        """Invoke the multimodal LLM and coerce the response into a template."""

        if not images:
            raise ValueError("At least one image is required")

        json_schema = MenuTemplate.model_json_schema()
        request_content = _build_request_content(images, filenames)

        try:
            response = await self.client.responses.create(
                model=settings.openai_model,
                input=[
                    {
                        "role": "system",
                        "content": [{"type": "text", "text": _SYSTEM_PROMPT}],
                    },
                    {
                        "role": "user",
                        "content": request_content,
                    },
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "menu_template", "schema": json_schema},
                },
                temperature=0.2,
            )
        except OpenAIError as exc:  # pragma: no cover - network failure path
            raise RuntimeError("Failed to call OpenAI API") from exc

        payload = _extract_json_payload(response)
        return MenuTemplate.model_validate(payload)


def _build_request_content(
    images: Sequence[bytes], filenames: Sequence[str] | None
) -> List[dict]:
    """Construct multimodal content with base64-encoded images."""

    content: List[dict] = [{"type": "text", "text": _USER_INSTRUCTIONS}]
    for index, raw in enumerate(images):
        name = (
            filenames[index]
            if filenames and index < len(filenames)
            else f"page-{index + 1}"
        )
        encoded = base64.b64encode(raw).decode("utf-8")
        content.append(
            {
                "type": "input_text",
                "text": f"Image source: {name}",
            }
        )
        content.append({"type": "input_image", "image_base64": encoded})
    return content


def _extract_json_payload(response: object) -> dict:
    """Traverse the responses API payload to pull JSON content."""

    # The OpenAI Responses API returns a structured object. We access text segments
    # directly to avoid additional dependencies on their dataclasses.
    try:
        for item in response.output:  # type: ignore[attr-defined]
            for content in item.content:  # type: ignore[attr-defined]
                if getattr(content, "type", None) == "output_text":
                    return json.loads(content.text)  # type: ignore[attr-defined]
                if getattr(content, "type", None) == "text":
                    return json.loads(content.text)  # type: ignore[attr-defined]
    except AttributeError as exc:  # pragma: no cover - defensive guard
        raise RuntimeError("Unexpected response format from OpenAI") from exc

    raise RuntimeError("No JSON payload returned from OpenAI")
