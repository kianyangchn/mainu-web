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


# SYSTEM_INSTRUCTIONS = (
#     "You are a meticulous transcription assistant for restaurant menus. "
#     "You can recognize the menu language, remember dish names exactly as written, and "
#     "preserve the original ordering even if the photos are low quality. "
#     "You can understand regional dishes, can translate them into the requested language, "
#     "and can summarise flavour, ingredients, and preparation details in a single approachable sentence. "
#     "Your final goal is to sutrcture the required menu information into desired json format. "
#     "Some dishes can be on the side of the menu, do not miss any sections and dishes."
# )

SYSTEM_INSTRUCTIONS = (
    "You are a meticulous transcription assistant for restaurant menus. Given photos of a menu, your responsibilities are to extract menu information and structure it into JSON format. "
#     "- Accurately recognize the original language of the menu. "
#     "- Transcribe all dishes information exactly as written, preserving the original ordering even if the photos are of low quality. "
#     "- Identify and transcribe every section, dish and price, including those listed on the sides of the menu image, ensuring that no sections or dishes are omitted. "
#     "- Understand regional and specialty dishes, offering translations into any requested language(s). "
#     "- For each dish, provide a single, approachable sentence summarizing its flavor, ingredients, and preparation details using contextual clues. "
    
#     "After transcribing and producing the output, validate that all menu items and sections are present, fields contain appropriate placeholder values where necessary, and ordering is preserved. If any inconsistency or probable omission is detected, self-correct before returning the final output. "
#     "Your final goal is to represent the menu information as an array of explicit JSON objects, each detailing a menu item while preserving its original order as displayed in the menu image. "
# )
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
                    "Translate section name into the output language."
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
        "If there's english information, use it as the primary language. "
        "Remember the menu is written in this language. "
        "This language is an important information to further processing the menu. "
    )

    transcription_rule = (
        "Then extract dishes information from ALL the pages. "
        "Keep the section, dish name and price of each items. "
        "If a section title is missing, use the 'Menu' as the section. "
        "Keep dish names in the original language without translation ."
        "When prices are missing, uses 'N/A'. "
        "Sometimes the dish name can come with some description, keep it as it is."
        " Do not prepend bullets or numbering and do not translate anything in this stage."
        "Don't miss any drinks, sides, sauces, desserts, etc. They can be on the side of the menu. "
    )

    structure_rule = (
        "Based on the items in the photos, build a structured menu. "
        "Keep the original dish name as written on the menu in the original_name field in the JSON. "
        f"Translate dish titles into {output_language} and keep it in the translated_name field in the JSON. "
        f"If there's any description, translate it into the {output_language}. "
        "But if there's no description on the menu, write a natural one-sentence description in the "
        f"{output_language} describing key ingredients, preparation details, and flavour. "
        "Do not overdescribe the dishes, do not add quality, quantity, or price details that are not present on the menu. "
        "If price is listed as 'N/A', keep it as 'N/A'. "
        f"Translate section names into {output_language} and store it in the section field in the JSON. "
        "Do not treat a section as a dish. "
    )
    json_rule = (
        "Last step, respond strictly with JSON that matches the provided schema. "
        "Do not include any explanatory text before or after the JSON."
    )
    double_check = (
        "Double check the language used in the output json. "
        f"Don't forget to translate section name, translated name and description into {output_language}. "
        "DO NOT treat a section as a dish and put section name in the dish related field"
    )

    content: List[dict[str, str]] = [
        {"type": "input_text", "text": language_hint},
        # {"type": "input_text", "text": transcription_rule},
        {"type": "input_text", "text": structure_rule},
        {"type": "input_text", "text": json_rule},
        {"type": "input_text", "text": double_check},
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

    return {"effort": "minimal"}
