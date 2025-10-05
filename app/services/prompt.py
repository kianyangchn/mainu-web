"""Prompt building helpers for OpenAI payload construction."""

from __future__ import annotations

from copy import deepcopy

__all__ = [
    "JSON_SCHEMA_NAME",
    "RESPONSE_JSON_SCHEMA",
    "build_response_object_schema",
    "build_text_format_config",
    "build_text_config",
    "build_reasoning_config",
    "STAGE_ONE_SYSTEM_INSTRUCTIONS",
    "STAGE_TWO_SYSTEM_INSTRUCTIONS"
]

STAGE_ONE_SYSTEM_INSTRUCTIONS = (
    "You are a meticulous transcription assistant for restaurant menus. "
    "You can recognize menus written in different languages. "
    "You can extract every dish exactly as written without translating names. "
    "You can also extract information such as dish category, price if available. "
    "Even the photo can be blurry, you always try your best."
)

STAGE_TWO_SYSTEM_INSTRUCTIONS = (
    "You are an traveller expert and language master. You are familiar with the language and food culture of the world. "
    "You are able to understand the menu and translate it into the target language. "
    "With knowledge of the food and cultural, you can explain the dishes well in any language. "
    "You should always follow the instructions and return in expected json format."
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
                    "The section in this menu if exists, something like appetizer, main dish, "
                    "soup, salad, etc. Translate to the output language with short words. By default `menu`"
                ),
            },
            "original_name": {
                "type": "string",
                "description": "Menu item name in the source language.",
            },
            "translated_name": {
                "type": "string",
                "description": "Menu item name translated into the target language (typically English).",
            },
            "description": {
                "type": "string",
                "description": "Supporting description or key ingredients.",
            },
            "price": {
                "type": "number",
                "description": "price of the dish",
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
    """Return JSON schema formatting config for OpenAI Responses API."""

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
