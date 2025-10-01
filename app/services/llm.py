"""LLM integration layer for menu extraction."""

from __future__ import annotations

import json
from typing import Iterable, List, Sequence

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
        self,
        images: Sequence[bytes],
        filenames: Sequence[str] | None = None,
        content_types: Sequence[str] | None = None,
    ) -> MenuTemplate:
        """Invoke the multimodal LLM and coerce the response into a template."""

        if not images:
            raise ValueError("At least one image is required")

        file_ids = await self._upload_images(images, filenames, content_types)
        schema_text = json.dumps(MenuTemplate.model_json_schema())
        request_content = _build_request_content(file_ids, filenames, schema_text)

        try:
            response = await self.client.responses.create(
                model=settings.openai_model,
                input=[
                    {
                        "role": "system",
                        "content": [
                            {"type": "input_text", "text": _SYSTEM_PROMPT},
                        ],
                    },
                    {
                        "role": "user",
                        "content": request_content,
                    },
                ],
                temperature=0.2,
            )
        except OpenAIError as exc:  # pragma: no cover - network failure path
            raise RuntimeError("Failed to call OpenAI API") from exc
        finally:
            await self._delete_files(file_ids)

        payload = _extract_json_payload(response)
        return MenuTemplate.model_validate(payload)

    async def _upload_images(
        self,
        images: Sequence[bytes],
        filenames: Sequence[str] | None,
        content_types: Sequence[str] | None,
    ) -> List[str]:
        """Upload images to the Files API and return file IDs."""

        file_ids: List[str] = []
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
            upload = await self.client.files.create(
                file=(name, raw, content_type),
                purpose="vision",
            )
            file_ids.append(upload.id)
        return file_ids

    async def _delete_files(self, file_ids: Iterable[str]) -> None:
        for file_id in file_ids:
            try:
                await self.client.files.delete(file_id)
            except OpenAIError:  # pragma: no cover - best effort cleanup
                pass


def _build_request_content(
    file_ids: Sequence[str],
    filenames: Sequence[str] | None,
    schema_text: str,
) -> List[dict]:
    """Construct multimodal content referencing uploaded file IDs."""

    content: List[dict] = [
        {"type": "input_text", "text": _USER_INSTRUCTIONS},
        {
            "type": "input_text",
            "text": (
                "Return a JSON object matching this schema: "
                f"{schema_text}. Do not include extra text."
            ),
        },
    ]
    for index, file_id in enumerate(file_ids):
        name = (
            filenames[index]
            if filenames and index < len(filenames)
            else f"page-{index + 1}"
        )
        content.append(
            {
                "type": "input_text",
                "text": f"Image source: {name}",
            }
        )
        content.append({"type": "input_image", "image_file": {"file_id": file_id}})
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
