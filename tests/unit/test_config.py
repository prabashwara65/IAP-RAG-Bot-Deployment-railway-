"""Tests for typed application settings."""

from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import (
    _ENV_FILE,
    DEFAULT_EMBEDDING_DIMENSION,
    DEFAULT_GEMINI_EMBEDDING_MODEL,
    DEFAULT_GEMINI_MODEL,
    Settings,
    get_settings,
)

SETTING_NAMES = (
    "APP_NAME",
    "APP_ENV",
    "AUTO_ACTIVATE_UPLOADS",
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
    "GEMINI_API_KEY",
    "GEMINI_MODEL",
    "GEMINI_EMBEDDING_MODEL",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USERNAME",
    "SMTP_PASSWORD",
    "SMTP_FROM",
    "SMTP_USE_TLS",
)


def _clear_settings_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in SETTING_NAMES:
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()


def test_the_env_file_is_resolved_from_the_repository_root() -> None:
    """Settings must not depend on the process working directory."""
    repository_root = Path(__file__).resolve().parents[2]
    assert _ENV_FILE.is_absolute()
    assert _ENV_FILE == repository_root / ".env"


def test_settings_load_safe_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_settings_environment(monkeypatch)

    settings = get_settings()

    assert settings.app_name == "office-intelligence-automation-platform-oiap"
    assert settings.app_env == "development"
    assert settings.auto_activate_uploads is True
    assert settings.app_version == "0.1.0"
    assert settings.log_level == "INFO"
    assert settings.api_prefix == "/api/v1"
    assert settings.cors_origins == ["http://localhost:3000"]
    assert settings.database_url.get_secret_value().startswith(
        "postgresql+psycopg://"
    )
    assert settings.database_pool_size == 5
    assert settings.database_connect_timeout_seconds == 5
    assert settings.embedding_dimension == DEFAULT_EMBEDDING_DIMENSION == 768


def test_environment_variables_override_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_settings_environment(monkeypatch)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("API_PREFIX", "/test/v1")
    monkeypatch.setenv("CORS_ORIGINS", '["https://example.com"]')
    monkeypatch.setenv("AUTO_ACTIVATE_UPLOADS", "false")

    settings = get_settings()

    assert settings.app_env == "test"
    assert settings.log_level == "DEBUG"
    assert settings.api_prefix == "/test/v1"
    assert settings.cors_origins == ["https://example.com"]
    assert settings.auto_activate_uploads is False


@pytest.mark.parametrize(
    ("app_env", "expected"),
    [("development", True), ("test", True), ("staging", False), ("production", False)],
)
def test_auto_activation_defaults_by_environment(app_env: str, expected: bool) -> None:
    settings = Settings(_env_file=None, app_env=app_env)  # type: ignore[call-arg]

    assert settings.auto_activate_uploads is expected


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


def test_gemini_settings_default_safely_without_a_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defaults are read without any .env file so a real local .env cannot skew them."""
    _clear_settings_environment(monkeypatch)

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.gemini_api_key is None
    assert settings.gemini_model == DEFAULT_GEMINI_MODEL == "gemini-2.5-flash"
    assert (
        settings.gemini_embedding_model
        == DEFAULT_GEMINI_EMBEDDING_MODEL
        == "gemini-embedding-001"
    )


def test_gemini_environment_variables_override_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_settings_environment(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "test-api-key-not-a-real-secret")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-test-model")

    settings = get_settings()

    assert settings.gemini_model == "gemini-test-model"
    assert settings.gemini_api_key is not None
    assert settings.gemini_api_key.get_secret_value() == "test-api-key-not-a-real-secret"


def test_the_gemini_api_key_is_masked_in_representations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_settings_environment(monkeypatch)
    secret = "test-api-key-not-a-real-secret"
    monkeypatch.setenv("GEMINI_API_KEY", secret)

    settings = get_settings()

    assert isinstance(settings.gemini_api_key, SecretStr)
    assert secret not in repr(settings)
    assert secret not in str(settings)
    assert secret not in str(settings.model_dump())


@pytest.mark.parametrize("gemini_model", ["", "   "])
def test_a_blank_gemini_model_is_rejected(gemini_model: str) -> None:
    with pytest.raises(ValidationError):
        Settings(gemini_model=gemini_model)


@pytest.mark.parametrize("gemini_embedding_model", ["", "   "])
def test_a_blank_gemini_embedding_model_is_rejected(
    gemini_embedding_model: str,
) -> None:
    with pytest.raises(ValidationError):
        Settings(gemini_embedding_model=gemini_embedding_model)


def test_the_gemini_embedding_model_can_be_overridden_by_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_settings_environment(monkeypatch)
    monkeypatch.setenv("GEMINI_EMBEDDING_MODEL", "text-embedding-004")
    monkeypatch.setenv("EMBEDDING_DIMENSION", "768")

    settings = get_settings()

    assert settings.gemini_embedding_model == "text-embedding-004"
    assert settings.embedding_dimension == 768


def test_gmail_smtp_defaults_are_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_settings_environment(monkeypatch)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.smtp_host == "smtp.gmail.com"
    assert settings.smtp_port == 587
    assert settings.smtp_use_tls is True
    assert settings.smtp_is_configured is False


def test_gmail_smtp_is_configured_when_credentials_are_present() -> None:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        smtp_username="ada@gmail.com",
        smtp_password=SecretStr("app-password-not-real"),
        smtp_from="ada@gmail.com",
    )
    assert settings.smtp_is_configured is True


def test_the_smtp_password_is_masked_in_representations() -> None:
    secret = "app-password-not-real"
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        smtp_username="ada@gmail.com",
        smtp_password=SecretStr(secret),
        smtp_from="ada@gmail.com",
    )
    assert secret not in repr(settings)
    assert secret not in str(settings)
    assert secret not in str(settings.model_dump())
