"""
JARVIS AI — Configuration System

Loads settings from config/settings.yaml and validates them using Pydantic.
Environment variables can override any setting using the JARVIS_ prefix.

Usage:
    from config import get_settings
    settings = get_settings()
    print(settings.jarvis.name)  # "JARVIS"
"""

from __future__ import annotations

import os
import platform
import sys
from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field


# ── Project root ──────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "settings.yaml"


# ── Pydantic Models ──────────────────────────────────────────

class JarvisConfig(BaseModel):
    """General JARVIS identity & runtime settings."""
    name: str = "JARVIS"
    version: str = "1.0.0"
    codename: str = "Friday"
    platform: str = "auto"
    debug: bool = False


class AIConfig(BaseModel):
    """AI / LLM configuration."""
    default_model: str = "ollama/llama3"
    fallback_model: str = "ollama/mistral"
    openai_api_key: str = ""
    ollama_host: str = "http://localhost:11434"
    temperature: float = 0.7
    max_tokens: int = 2048
    timeout_seconds: int = 30


class SecurityConfig(BaseModel):
    """Security & permission configuration."""
    confirmation_required: bool = True
    max_retries: int = 3
    blocked_commands: list[str] = Field(default_factory=list)
    safe_commands: list[str] = Field(default_factory=list)
    risk_levels: dict[str, str] = Field(default_factory=dict)


class SpeechConfig(BaseModel):
    """Voice architecture processing parameters."""
    enabled: bool = False
    wake_word: str = "jarvis"
    porcupine_access_key: str = ""
    stt_engine: str = "whisper"
    tts_engine: str = "edge-tts"
    tts_voice: str = "en-GB-RyanNeural"
    tts_rate: str = "+0%"


class LoggingConfig(BaseModel):
    """Logging configuration."""
    level: str = "INFO"
    file: str = "logs/jarvis.log"
    rotation: str = "10 MB"
    retention: str = "7 days"
    format: str = (
        "{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | "
        "{name}:{function}:{line} | {message}"
    )
    colorize: bool = True


class InputConfig(BaseModel):
    """Input mode configuration."""
    mode: str = "text"
    history_file: str = "logs/.jarvis_history"
    max_history: int = 1000


class ResourceConfig(BaseModel):
    """Resource management limits."""
    max_cpu_percent: int = 80
    max_memory_percent: int = 85
    max_concurrent_tasks: int = 5
    task_timeout_seconds: int = 300


class Settings(BaseModel):
    """Root settings container — the single source of truth."""
    jarvis: JarvisConfig = Field(default_factory=JarvisConfig)
    ai: AIConfig = Field(default_factory=AIConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    speech: SpeechConfig = Field(default_factory=SpeechConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    input: InputConfig = Field(default_factory=InputConfig)
    resources: ResourceConfig = Field(default_factory=ResourceConfig)

    def resolve_platform(self) -> str:
        """Resolve 'auto' platform to the actual OS."""
        if self.jarvis.platform == "auto":
            system = platform.system().lower()
            return "linux" if system == "linux" else "windows"
        return self.jarvis.platform

    @property
    def is_linux(self) -> bool:
        return self.resolve_platform() == "linux"

    @property
    def is_windows(self) -> bool:
        return self.resolve_platform() == "windows"

    @property
    def log_path(self) -> Path:
        return PROJECT_ROOT / self.logging.file

    @property
    def history_path(self) -> Path:
        return PROJECT_ROOT / self.input.history_file


# ── Loader ────────────────────────────────────────────────────

def _load_yaml(path: Path) -> dict:
    """Load YAML configuration file."""
    if not path.exists():
        raise FileNotFoundError(
            f"Configuration file not found: {path}\n"
            f"Expected at: {path.resolve()}"
        )
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _apply_env_overrides(raw: dict) -> dict:
    """
    Override config values with environment variables.
    Convention: JARVIS_<SECTION>__<KEY>  (double underscore for nesting)

    Example:
        JARVIS_AI__DEFAULT_MODEL=gpt-4o  →  ai.default_model = "gpt-4o"
        JARVIS_SECURITY__CONFIRMATION_REQUIRED=false
    """
    prefix = "JARVIS_"
    for key, value in os.environ.items():
        if not key.startswith(prefix):
            continue
        parts = key[len(prefix):].lower().split("__")
        if len(parts) == 2:
            section, field = parts
            if section in raw and isinstance(raw[section], dict):
                # Type coercion for booleans
                if value.lower() in ("true", "1", "yes"):
                    value = True
                elif value.lower() in ("false", "0", "no"):
                    value = False
                raw[section][field] = value
    return raw


@lru_cache(maxsize=1)
def get_settings(config_path: Optional[str] = None) -> Settings:
    """
    Load, validate, and cache the application settings.

    Args:
        config_path: Optional override path to settings.yaml

    Returns:
        Validated Settings instance (cached after first call)
    """
    path = Path(config_path) if config_path else CONFIG_PATH
    raw = _load_yaml(path)
    raw = _apply_env_overrides(raw)
    return Settings(**raw)


def reload_settings(config_path: Optional[str] = None) -> Settings:
    """Force reload settings (clears cache)."""
    get_settings.cache_clear()
    return get_settings(config_path)


# ── Convenience ───────────────────────────────────────────────

__all__ = [
    "Settings",
    "JarvisConfig",
    "AIConfig",
    "SecurityConfig",
    "SpeechConfig",
    "LoggingConfig",
    "InputConfig",
    "ResourceConfig",
    "get_settings",
    "reload_settings",
    "PROJECT_ROOT",
]
