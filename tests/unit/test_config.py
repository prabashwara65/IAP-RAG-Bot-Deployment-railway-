"""Tests for typed application settings."""

import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import (
    DEFAULT_OPENAI_EMBEDDING_MODEL,
    DEFAULT_OPENAI_MODEL,
    Settings,
    get_settings,
)

SETTING_NAMES = (
    "APP_NAME",
    "APP_ENV",
    "APP_VERSION",
    "LOG_LEVEL",
    "API_PREFIX",
    "CORS_ORIGINS",
    "DB_HOST",
    "DB_PORT",
    "DB_NAME",
    "DB_USER",
    "DB_PASSWORD",
    "DATABASE_POOL_SIZE",
    "DATABASE_CONNECT_TIMEOUT_SECONDS",
    "EMBEDDING_DIMENSION",
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
    "OPENAI_EMBEDDING_MODEL",
)


def _clear_settings_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in SETTING_NAMES:
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()


def test_settings_load_safe_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_settings_environment(monkeypatch)

    settings = get_settings()

    assert settings.app_name == "office-intelligence-automation-platform-oiap"
    assert settings.app_env == "development"
    assert settings.app_version == "0.1.0"
    assert settings.log_level == "INFO"
    assert settings.api_prefix == "/api/v1"
    assert settings.cors_origins == ["http://localhost:3000"]
    assert settings.database_url.get_secret_value().startswith(
        "postgresql+psycopg://"
    )
    assert settings.database_pool_size == 5
    assert settings.database_connect_timeout_seconds == 5
    assert settings.embedding_dimension == 1536


def test_environment_variables_override_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_settings_environment(monkeypatch)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("API_PREFIX", "/test/v1")
    monkeypatch.setenv("CORS_ORIGINS", '["https://example.com"]')

    settings = get_settings()

    assert settings.app_env == "test"
    assert settings.log_level == "DEBUG"
    assert settings.api_prefix == "/test/v1"
    assert settings.cors_origins == ["https://example.com"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("app_env", "unknown"),
        ("app_version", "latest"),
        ("log_level", "VERBOSE"),
        ("api_prefix", "api/v1"),
        ("cors_origins", ["*"]),
        ("cors_origins", ["https://example.com/path"]),
    ],
)
def test_invalid_configuration_fails_clearly(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        Settings(**{field: value})  # type: ignore[arg-type]


def test_settings_cache_can_be_reset_for_environment_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_settings_environment(monkeypatch)
    first = get_settings()
    monkeypatch.setenv("APP_ENV", "test")

    assert get_settings() is first

    get_settings.cache_clear()
    assert get_settings().app_env == "test"


def test_openai_settings_default_safely_without_a_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defaults are read without any .env file so a real local .env cannot skew them."""
    _clear_settings_environment(monkeypatch)

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.openai_api_key is None
    assert settings.openai_model == DEFAULT_OPENAI_MODEL == "gpt-5-mini"
    assert (
        settings.openai_embedding_model
        == DEFAULT_OPENAI_EMBEDDING_MODEL
        == "text-embedding-3-small"
    )


def test_openai_environment_variables_override_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_settings_environment(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key-not-a-real-secret")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test-model")

    settings = get_settings()

    assert settings.openai_model == "gpt-test-model"
    assert settings.openai_api_key is not None
    assert settings.openai_api_key.get_secret_value() == "test-api-key-not-a-real-secret"


def test_the_openai_api_key_is_masked_in_representations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_settings_environment(monkeypatch)
    secret = "test-api-key-not-a-real-secret"
    monkeypatch.setenv("OPENAI_API_KEY", secret)

    settings = get_settings()

    assert isinstance(settings.openai_api_key, SecretStr)
    assert secret not in repr(settings)
    assert secret not in str(settings)
    assert secret not in str(settings.model_dump())


@pytest.mark.parametrize("openai_model", ["", "   "])
def test_a_blank_openai_model_is_rejected(openai_model: str) -> None:
    with pytest.raises(ValidationError):
        Settings(openai_model=openai_model)


@pytest.mark.parametrize("openai_embedding_model", ["", "   "])
def test_a_blank_openai_embedding_model_is_rejected(
    openai_embedding_model: str,
) -> None:
    with pytest.raises(ValidationError):
        Settings(openai_embedding_model=openai_embedding_model)


def test_the_openai_embedding_model_can_be_overridden_by_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_settings_environment(monkeypatch)
    monkeypatch.setenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large")
    monkeypatch.setenv("EMBEDDING_DIMENSION", "3072")

    settings = get_settings()

    assert settings.openai_embedding_model == "text-embedding-3-large"
    assert settings.embedding_dimension == 3072
