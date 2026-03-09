"""
JARVIS AI — Tests for Configuration System
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest
import yaml

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import (
    Settings,
    JarvisConfig,
    AIConfig,
    SecurityConfig,
    LoggingConfig,
    get_settings,
    reload_settings,
)


class TestJarvisConfig:
    """Tests for JarvisConfig model."""

    def test_defaults(self):
        config = JarvisConfig()
        assert config.name == "JARVIS"
        assert config.version == "1.0.0"
        assert config.platform == "auto"
        assert config.debug is False

    def test_custom_values(self):
        config = JarvisConfig(name="FRIDAY", version="2.0.0", debug=True)
        assert config.name == "FRIDAY"
        assert config.version == "2.0.0"
        assert config.debug is True


class TestAIConfig:
    """Tests for AIConfig model."""

    def test_defaults(self):
        config = AIConfig()
        assert config.default_model == "ollama/llama3"
        assert config.temperature == 0.7
        assert config.max_tokens == 2048

    def test_openai_key(self):
        config = AIConfig(openai_api_key="sk-test-12345")
        assert config.openai_api_key == "sk-test-12345"


class TestSecurityConfig:
    """Tests for SecurityConfig model."""

    def test_defaults(self):
        config = SecurityConfig()
        assert config.confirmation_required is True
        assert config.max_retries == 3
        assert isinstance(config.blocked_commands, list)

    def test_blocked_commands(self):
        config = SecurityConfig(blocked_commands=["rm -rf /", "format c:"])
        assert len(config.blocked_commands) == 2
        assert "rm -rf /" in config.blocked_commands


class TestSettings:
    """Tests for the root Settings model."""

    def test_defaults(self):
        settings = Settings()
        assert settings.jarvis.name == "JARVIS"
        assert settings.ai.default_model == "ollama/llama3"
        assert settings.security.confirmation_required is True

    def test_resolve_platform(self):
        settings = Settings(jarvis=JarvisConfig(platform="linux"))
        assert settings.resolve_platform() == "linux"
        assert settings.is_linux is True
        assert settings.is_windows is False

    def test_auto_platform(self):
        settings = Settings(jarvis=JarvisConfig(platform="auto"))
        platform = settings.resolve_platform()
        assert platform in ("linux", "windows")


class TestSettingsLoader:
    """Tests for YAML config loading."""

    def test_load_from_yaml(self):
        """Test loading settings from a temporary YAML file."""
        config_data = {
            "jarvis": {
                "name": "TEST_JARVIS",
                "version": "0.0.1",
                "platform": "linux",
                "debug": True,
            },
            "ai": {
                "default_model": "test/model",
                "temperature": 0.5,
            },
            "security": {
                "confirmation_required": False,
                "blocked_commands": ["rm -rf /"],
            },
            "logging": {
                "level": "DEBUG",
            },
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(config_data, f)
            temp_path = f.name

        try:
            settings = reload_settings(temp_path)
            assert settings.jarvis.name == "TEST_JARVIS"
            assert settings.jarvis.version == "0.0.1"
            assert settings.ai.default_model == "test/model"
            assert settings.ai.temperature == 0.5
            assert settings.security.confirmation_required is False
            assert "rm -rf /" in settings.security.blocked_commands
        finally:
            os.unlink(temp_path)
            # Clear cache
            get_settings.cache_clear()

    def test_missing_config_file(self):
        """Test that missing config file raises error."""
        with pytest.raises(FileNotFoundError):
            reload_settings("/nonexistent/path.yaml")
        # Clear cache
        get_settings.cache_clear()

    def test_env_override(self):
        """Test environment variable override."""
        config_data = {
            "jarvis": {"name": "JARVIS"},
            "ai": {"default_model": "original/model"},
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(config_data, f)
            temp_path = f.name

        try:
            os.environ["JARVIS_AI__DEFAULT_MODEL"] = "overridden/model"
            settings = reload_settings(temp_path)
            assert settings.ai.default_model == "overridden/model"
        finally:
            os.unlink(temp_path)
            os.environ.pop("JARVIS_AI__DEFAULT_MODEL", None)
            get_settings.cache_clear()
