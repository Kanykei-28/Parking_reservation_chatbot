"""Tests for typed application configuration."""

from pathlib import Path

import pytest

from parking_chatbot.config import Settings, get_settings


def test_settings_load_with_safe_defaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    settings = Settings()

    assert settings.app_name == "Parking Reservation Chatbot"
    assert settings.environment == "development"
    assert settings.database_path == Path("data/dynamic/parking.db")
    assert settings.admin_approval_base_url == "http://127.0.0.1:8000"
    assert settings.openai_api_key is None


def test_environment_variables_override_defaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("DATABASE_PATH", "data/dynamic/test.db")
    monkeypatch.setenv("ADMIN_APPROVAL_BASE_URL", "http://admin.test:9000")

    settings = Settings()

    assert settings.environment == "test"
    assert settings.log_level == "DEBUG"
    assert settings.database_path == Path("data/dynamic/test.db")
    assert settings.admin_approval_base_url == "http://admin.test:9000"


def test_sensitive_fields_are_hidden(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    secret = "foundation-test-secret"
    monkeypatch.setenv("OPENAI_API_KEY", secret)

    settings = Settings()

    assert secret not in repr(settings)
    assert secret not in str(settings)
    assert "openai_api_key" not in repr(settings)


def test_get_settings_returns_cached_instance(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    assert get_settings() is get_settings()

    get_settings.cache_clear()
