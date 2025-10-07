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
    "STAGE_ONE_SYSTEM_INSTRUCTIONS",
    "STAGE_TWO_SYSTEM_INSTRUCTIONS",
    "build_reasoning_config",
    "build_response_object_schema",
    "build_stage_one_prompt",
    "build_stage_two_prompt",
    "build_text_config",
    "build_text_format_config",
]

LANGUAGE_MARKER = "The menu is written in: "


@dataclass(frozen=True)
class PromptRequest:
    """Container describing a single Responses API prompt."""

    instructions: str
    content: List[dict[str, str]]


STAGE_ONE_SYSTEM_INSTRUCTIONS = (
    "You are a meticulous transcription assistant for restaurant menus. "
    "Recognize the menu language, copy dish names exactly as written, and "
    "preserve the original ordering even if the photos are low quality."
)

STAGE_TWO_SYSTEM_INSTRUCTIONS = (
    "You are a culinary translator. You understand regional dishes, can translate "
    "them into the requested language, and can summarise flavour, ingredients, and "
    "preparation details in a single approachable sentence."
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
                "description": "One sentence describing ingredients, preparation, and flavour.",
            },
            "price": {
                "type": ["number", "string"],
                "description": "Price exactly as seen (may be numeric, currency text, or 'N/A').",
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


def build_stage_one_prompt(
    file_ids: Sequence[str],
) -> PromptRequest:
    """Return the stage-one prompt for transcription and language detection."""

    if not file_ids:
        raise ValueError("Stage one prompt requires at least one uploaded file id.")

    language_hint = (
        "Detect the primary language used throughout the menu. After you finish "
        f"listing dishes, append a final line that reads '{LANGUAGE_MARKER} <language name>'."
    )

    transcription_rule = (
        "For each dish you see, output one line formatted exactly as "
        "'<section> | <dish name> | <price>'. Repeat the section for each dish. "
        "If a section title is missing, use 'Menu'. Keep dish names in the original "
        "language without translation. When prices are missing, write 'N/A'. Do not "
        "prepend bullets or numbering and do not translate anything in this stage."
    )

    content: List[dict[str, str]] = [
        {"type": "input_text", "text": language_hint},
        {"type": "input_text", "text": transcription_rule},
    ]
    for file_id in file_ids:
        content.append({"type": "input_image", "file_id": file_id})

    return PromptRequest(
        instructions=STAGE_ONE_SYSTEM_INSTRUCTIONS,
        content=content,
    )


def build_stage_two_prompt(
    transcription: str,
    *,
    output_language: str,
) -> PromptRequest:
    """Return the stage-two prompt that transforms transcription into menu JSON."""

    structure_rule = (
        "Using the transcription between the delimiters below, construct a structured menu. "
        "Each source line follows '<section> | <dish name> | <price>'. "
        f"Translate section names and dish titles into {output_language} but keep the original "
        "names available in the JSON. Write a natural one-sentence description in the "
        f"{output_language} describing key ingredients, preparation details, and flavour. "
        "If price is listed as 'N/A', keep it as 'N/A'. Make use of any language markers present "
        f"in the transcription (such as lines beginning with '{LANGUAGE_MARKER}') to choose appropriate terminology."
    )
    json_rule = (
        "Respond strictly with JSON that matches the provided schema. "
        "Do not include any explanatory text before or after the JSON."
    )
    safe_transcription = transcription.strip() or "No dishes were extracted."
    transcription_block = (
        "--- transcription start ---\n"
        f"{safe_transcription}\n"
        "--- transcription end ---"
    )

    content: List[dict[str, str]] = [
        {"type": "input_text", "text": structure_rule},
        {"type": "input_text", "text": transcription_block},
        {"type": "input_text", "text": json_rule},
    ]

    return PromptRequest(
        instructions=STAGE_TWO_SYSTEM_INSTRUCTIONS,
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
