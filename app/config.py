"""Application configuration."""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven settings for the web app."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-5-nano"
    share_token_ttl_minutes: int = 1440  # 24 hours per PRD


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings instance."""

    return Settings()


settings = get_settings()
