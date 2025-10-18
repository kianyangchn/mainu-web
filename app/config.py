"""Application configuration."""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven settings for the web app."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-5-mini"
    quick_suggestion_model: str = "gpt-5-nano"
    quick_suggestion_timeout_seconds: int = 12
    default_output_language: str = "English"
    share_token_ttl_minutes: int = 240  # 4 hours default
    database_url: Optional[str] = None


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings instance."""

    return Settings()


settings = get_settings()
