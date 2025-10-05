"""LLM integration layer for menu extraction."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, List, Sequence

from openai import AsyncOpenAI, OpenAIError

from app.config import settings
from app.schemas import MenuDish, MenuSection, MenuTemplate
from app.services.prompt import (
    build_reasoning_config,
    build_text_config,
    STAGE_ONE_SYSTEM_INSTRUCTIONS,
    STAGE_TWO_SYSTEM_INSTRUCTIONS
)

@dataclass(frozen=True)
class MenuGenerationResult:
    """Structured result produced by the LLM generation flow."""

    template: MenuTemplate
    detected_input_language: str | None


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
        *,
        input_language: str | None = None,
        output_language: str | None = None,
    ) -> MenuGenerationResult:
        """Invoke the multimodal LLM and coerce the response into a template."""

        if not images:
            raise ValueError("At least one image is required")

        detected_input_language: str | None = None

        file_ids = await self._upload_images(images, filenames, content_types)
        try:
            transcription = await self._extract_menu_transcription(file_ids, input_language)

            stage_two_content = _build_stage_two_content(
                transcription=transcription,
                lang_out=output_language or settings.default_output_language
            )

            response = await self.client.responses.create(
                model=settings.openai_model,
                instructions=STAGE_TWO_SYSTEM_INSTRUCTIONS,
                input=[
                    {
                        "role": "user",
                        "content": stage_two_content,
                    }
                ],
                text=build_text_config(),
                reasoning=build_reasoning_config(),
            )
        except OpenAIError as exc:  # pragma: no cover - network failure path
            raise RuntimeError("Failed to call OpenAI API") from exc
        finally:
            await self._delete_files(file_ids)

        payload = _extract_json_payload(response)
        template = _build_menu_template(payload)
        return MenuGenerationResult(
            template=template,
            detected_input_language=(detected_input_language or "").strip() or None,
        )

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

    async def _extract_menu_transcription(self,file_ids: Sequence[str], lang_in: str | None) -> str:
        """Use the LLM to extract raw dish lines from the provided images."""

        if not file_ids:
            return ""

        content = _build_stage_one_content(file_ids, lang_in)

        response = await self.client.responses.create(
            model=settings.openai_model,
            instructions=STAGE_ONE_SYSTEM_INSTRUCTIONS,
            input=[{"role": "user", "content": content}],
            reasoning=build_reasoning_config(),
        )

        output_text = getattr(response, "output_text", None)
        if not output_text:
            raise RuntimeError("OpenAI response returned empty output_text")
        return str(output_text).strip()


def _build_stage_one_content(file_ids: Sequence[str], lang_in: str | None) -> List[dict]:
    """Construct the request payload for the transcription stage."""
    if lang_in:
        language_hint = f"Review every photos of the menu written in {lang_in}"
        language_tag = ""
    else:
        language_hint = (
            "Review every attached menu photo. First recognize the language used to write the menu. "
            "If there're several languages, choose the most common one. "
        )
        language_tag = (
            "After listing all dishes, "
            "append a final line that reads exactly 'the menu is written in <language of the "
            "menu you recognized>'."
        )
    recognize_rule = (
    "Then for each dish you see, output a single "
    "line formatted as '<section> | <dish name> | <price>'. Repeat the section "
    "for each dish; if no section is provided, use 'Menu'. Keep dish names in the "
    "original language and do not translate anything. Use 'N/A' when the price is "
    "missing. Do not add numbering or bullet characters. "
    )
    content: List[dict] = [
        {"type": "input_text", "text": language_hint},
        {"type": "input_text", "text": recognize_rule},
    ]
    if language_tag:
        content.append({"type": "input_text", "text": language_tag})
    for file_id in file_ids:
        content.append({"type": "input_image", "file_id": file_id})
    return content


def _build_stage_two_content(transcription: str, lang_out: str) -> List[dict]:
    """Prepare the second-stage request using text-only input."""

    intro = (
        "Use the following transcription of menu sections, dish names, and prices "
        "that was extracted from images to build a structured menu data." 
        "Each line follows '<section> | <dish name> | "
        "<price>' and prices may be 'N/A' when unavailable. "
        "The langauge of the menu is declared in the end of the transcription. "
    )
    safe_transcription = transcription.strip() or "No dish lines were extracted."
    safe_transcription = (
        f"--- transcription start --- \n {safe_transcription} \n --- transcription end --- \n"
    )
    structure_rule = (
        "To structure menu data. Follow these rules strictly: "
        "1) Extract distinct dish names from the text. "
        "2) PRESERVE the original dish wording in `original_name` and translate it into  "
        f"{lang_out} for `translated_name`. "
        f"3) For each dish, write a short descriptive sentence in the {lang_out} that includes "
        "typical ingredients, preparation method, and expected flavour profile (for example sweet, "
        "savory, spicy). Use natural phrasing rather than bullet lists."
        "4) extract the price of each dishes if listed. By default 0 "
        "5) extract the section if exsits, e.g. main dish; dessert; soup; etc. Translate to the short words. By default `menu` "
        "Return only a JSON array and ensure every object contains `section`, `original_name`, `translated_name`, "
        "`description` and `price`. No extra commentary or keys."
    )

    content: List[dict] = [
        {"type": "input_text", "text": intro},
        {"type": "input_text", "text": safe_transcription},
        {"type": "input_text", "text": structure_rule},
    ]
    return content


def _extract_json_payload(response: object) -> dict:
    """Traverse the responses API payload to pull JSON content."""

    try:
        output_text = response.output_text  # type: ignore[attr-defined]
    except AttributeError as exc:  # pragma: no cover - defensive guard
        raise RuntimeError("OpenAI response missing output_text") from exc

    if not output_text:
        raise RuntimeError("OpenAI response returned empty output_text")

    return json.loads(output_text)


def _build_menu_template(payload: dict) -> MenuTemplate:
    """Convert the raw payload into the MenuTemplate structure."""

    if not isinstance(payload, dict) or "items" not in payload:
        raise RuntimeError("OpenAI response missing 'items' payload")

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
