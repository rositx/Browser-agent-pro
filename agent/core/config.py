"""
Browser-Agent-Pro Configuration Module
=======================================
Centralised configuration using pydantic-settings.
Reads from environment variables and .env file with validation.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── LLM API Keys (optional until Phase 2) ──────────────────────────
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None

    # ── Logging ─────────────────────────────────────────────────────────
    log_level: str = "INFO"

    # ── Browser Settings ────────────────────────────────────────────────
    headless: bool = False
    default_viewport_width: int = 1440
    default_viewport_height: int = 900
    default_locale: str = "en-US"
    default_timezone: str = "America/New_York"

    # ── Paths ───────────────────────────────────────────────────────────
    profile_dir: Path = Path("./profiles")
    knowledge_base_dir: Path = Path("./knowledge_base")
    manifest_dir: Path = Path("./manifests")

    # ── Agent Limits ────────────────────────────────────────────────────
    max_steps: int = 60

    # ── Stealth Timing (milliseconds) ───────────────────────────────────
    human_delay_base_ms: int = 500
    typing_delay_min_ms: int = 40
    typing_delay_max_ms: int = 120

    # ── Validators ──────────────────────────────────────────────────────

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in allowed:
            raise ValueError(
                f"Invalid log level '{v}'. Must be one of: {', '.join(sorted(allowed))}"
            )
        return upper

    @field_validator("default_viewport_width")
    @classmethod
    def validate_viewport_width(cls, v: int) -> int:
        if not (800 <= v <= 3840):
            raise ValueError(f"Viewport width {v} out of range (800–3840)")
        return v

    @field_validator("default_viewport_height")
    @classmethod
    def validate_viewport_height(cls, v: int) -> int:
        if not (600 <= v <= 2160):
            raise ValueError(f"Viewport height {v} out of range (600–2160)")
        return v

    @field_validator("typing_delay_min_ms", "typing_delay_max_ms")
    @classmethod
    def validate_typing_delay(cls, v: int) -> int:
        if v < 0:
            raise ValueError("Typing delay cannot be negative")
        return v

    @field_validator("max_steps")
    @classmethod
    def validate_max_steps(cls, v: int) -> int:
        if v < 1:
            raise ValueError("max_steps must be at least 1")
        return v

    # ── Lifecycle ───────────────────────────────────────────────────────

    def model_post_init(self, __context: object) -> None:
        """Ensure required directories exist on startup."""
        for dir_path in (self.profile_dir, self.manifest_dir):
            dir_path.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return a cached singleton Settings instance.

    Call this instead of constructing Settings() directly to ensure
    configuration is loaded exactly once.
    """
    return Settings()
