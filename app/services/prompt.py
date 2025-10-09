"""Prompt building helpers for OpenAI payload construction."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import List, Sequence

__all__ = [
    "JSON_SCHEMA_NAME",
    "LANGUAGE_MARKER",
    "PromptRequest",
    "RESPONSE_JSON_SCHEMA",
    "build_reasoning_config",
    "build_response_object_schema",
    "build_prompt",
    "build_text_config",
    "build_text_format_config",
]

LANGUAGE_MARKER = "The menu is written in: "


@dataclass(frozen=True)
class PromptRequest:
    """Container describing a single Responses API prompt."""

    instructions: str
    content: List[dict[str, str]]


SYSTEM_INSTRUCTIONS = (
    "You are a meticulous transcription assistant for restaurant menus. "
    "You can recognize the menu language, remember dish names exactly as written, and "
    "preserve the original ordering even if the photos are low quality. "
    "You can understand regional dishes, can translate them into the requested language, "
    "and can summarise flavour, ingredients, and preparation details in a single approachable sentence. "
    "Your final goal is to sutrcture the required menu information into desired json format. "
    "Some dishes can be on the side of the menu, do not miss any sections and dishes."
)

JSON_SCHEMA_NAME = "menu_items"

RESPONSE_JSON_SCHEMA: dict[str, object] = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "section": {
                "type": "string",
                "description": (
                    "Translated section label such as appetisers, mains, desserts. "
                    "Fallback to 'Menu' when no grouping is provided."
                ),
            },
            "original_name": {
                "type": "string",
                "description": "Menu item name in the source language.",
            },
            "translated_name": {
                "type": "string",
                "description": "Menu item name translated into the output language.",
            },
            "description": {
                "type": "string",
                "description": "Translate of the original description or one sentence describing ingredients, preparation, and flavour.",
            },
            "price": {
                "type": "number",
                "description": "Price number exactly as seen without currency text.",
            },
        },
        "required": [
            "section",
            "original_name",
            "translated_name",
            "description",
            "price",
        ],
        "additionalProperties": False,
    },
    "minItems": 1,
}


def build_prompt(
    file_ids: Sequence[str],
    *,
    output_language: str,
) -> PromptRequest:
    """Return the stage-one prompt for transcription and language detection."""

    if not file_ids:
        raise ValueError("Stage one prompt requires at least one uploaded file id.")

    language_hint = (
        "First, detect the primary language used throughout the menu. "
        "Remember the menu is written in this language. "
        "This language is an important information to further processing the menu"
    )

    transcription_rule = (
        "Then extract dishes information from ALL the pages. "
        "Keep the section, dish name, (description if there's any) and price of each dishes. "
        "If a section title is missing, use 'Menu'. Keep dish names in the original "
        "language without translation. When prices are missing, write 'N/A'. "
        "Sometimes the dish name can come with some description, keep it as it is."
        " Do not prepend bullets or numbering and do not translate anything in this stage."
        "Do not miss any dish information."
    )

    structure_rule = (
        "Based on the extracted text, you can construct a structured menu. "
        f"Translate section names into {output_language}. "
        f"Translate dish titles into {output_language} but keep the original names available in the JSON. "
        f"If there's any description, translate it into the {output_language}. "
        "But if there's no description on the menu, write a natural one-sentence description in the "
        f"{output_language} describing key ingredients, preparation details, and flavour. "
        "Do not overdescribe the dishes, do not add quality, quantity, or price details that are not present on the menu. "
        "If price is listed as 'N/A', keep it as 'N/A'. "
    )
    json_rule = (
        "Last step, respond strictly with JSON that matches the provided schema. "
        "Do not include any explanatory text before or after the JSON."
    )

    content: List[dict[str, str]] = [
        {"type": "input_text", "text": language_hint},
        {"type": "input_text", "text": transcription_rule},
        {"type": "input_text", "text": structure_rule},
        {"type": "input_text", "text": json_rule},
    ]
    for file_id in file_ids:
        content.append({"type": "input_image", "file_id": file_id})

    return PromptRequest(
        instructions=SYSTEM_INSTRUCTIONS,
        content=content,
    )

def build_response_object_schema() -> dict[str, object]:
    """Return top-level object schema required by OpenAI Responses."""

    return {
        "type": "object",
        "properties": {
            "items": deepcopy(RESPONSE_JSON_SCHEMA),
        },
        "required": ["items"],
        "additionalProperties": False,
    }


def build_text_format_config() -> dict[str, object]:
    """Return JSON schema formatting config for the OpenAI Responses API."""

    return {
        "type": "json_schema",
        "name": JSON_SCHEMA_NAME,
        "schema": build_response_object_schema(),
        "strict": True,
    }


def build_text_config() -> dict[str, object]:
    """Return text configuration for the OpenAI Responses API."""

    return {
        "format": build_text_format_config(),
        "verbosity": "low",
    }


def build_reasoning_config() -> dict[str, object]:
    """Return reasoning configuration for the OpenAI Responses API."""

    return {"effort": "low"}
