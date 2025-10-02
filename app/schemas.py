"""Shared pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from typing import List

from pydantic import BaseModel, Field


class MenuDish(BaseModel):
    """Dish-level metadata returned by the LLM."""

    original_name: str = Field(description="Name as seen on the original menu")
    translated_name: str = Field(description="Localized name surfaced to diners")
    description: str = Field(
        description="Short dish explanation in the output language"
    )
    price: str | None = Field(default=None, description="Price extracted from the menu")


class MenuSection(BaseModel):
    """Top-level grouping of dishes."""

    title: str
    dishes: List[MenuDish]


class MenuTemplate(BaseModel):
    """Structured response contract consumed by the front end."""

    status: str = Field(default="completed")
    original_language: str | None = None
    sections: List[MenuSection] = Field(default_factory=list)


class MenuProcessingResponse(BaseModel):
    """Response payload after processing uploaded menus."""

    template: MenuTemplate
    share_token: str
    share_url: str | None = None
    share_expires_at: datetime = Field(
        description="Absolute expiry timestamp for the share link in UTC."
    )
    share_expires_in_seconds: int = Field(
        description="Seconds remaining before the share link expires."
    )
    detected_language: str | None = Field(
        default=None,
        description="Temporary debug field exposing the derived output language. Remove before GA.",
    )
