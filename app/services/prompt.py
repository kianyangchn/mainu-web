"""Prompt building helpers for OpenAI payload construction."""

from __future__ import annotations

from copy import deepcopy

__all__ = [
    "SYSTEM_INSTRUCTIONS",
    "JSON_SCHEMA_NAME",
    "RESPONSE_JSON_SCHEMA",
    "build_response_object_schema",
    "build_text_format_config",
    "build_text_config",
    "build_reasoning_config",
    "build_user_prompt",
]

SYSTEM_INSTRUCTIONS = (
    "You convert raw OCR menu text into structured menu data. Follow these rules strictly: "
    "1) Extract distinct dish names from the text. "
    "2) Preserve the original dish wording in `original_name` and translate it into the requested "
    "output language for `translated_name`. "
    "3) For each dish, write a short descriptive sentence in the output language that includes "
    "typical ingredients, preparation method, and expected flavour profile (for example sweet, "
    "savory, spicy). Use natural phrasing rather than bullet lists."
    "4) extract the price of each dishes if listed in menu "
    "5) extract the section if exsits, e.g. main dish; dessert; soup; etc. Translate to the short words. By default `menu` "
    "6) Return only a JSON array and ensure every object contains `section`, `original_name`, `translated_name`, "
    "`description` and `price`. No extra commentary or keys."
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


def build_user_prompt(lang_in: str | None, lang_out: str) -> str:
    """Return the prompt used for OpenAI call."""

    language_hint = [
        f"Input language: {lang_in if lang_in else 'unspecified (detect automatically)'}",
        f"Output language: {lang_out}",
    ]
    return (
        "Review all the menu pages. Combine related lines when appropriate and produce "
        "a JSON array of menu items that follows the schema.\n"
        + "\n".join(language_hint)
    )
