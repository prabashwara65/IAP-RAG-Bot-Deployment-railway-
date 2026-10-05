"""Typed application configuration."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

AppEnvironment = Literal["development", "test", "staging", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

DATABASE_DRIVERNAME = "postgresql+psycopg"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
DEFAULT_GEMINI_EMBEDDING_MODEL = "gemini-embedding-001"
DEFAULT_EMBEDDING_DIMENSION = 768
# Load `.env` from the repository root even if uvicorn is started elsewhere.
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILE = _REPOSITORY_ROOT / ".env"


class Settings(BaseSettings):
    """Validated application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = Field(
        default="office-intelligence-automation-platform-oiap",
        min_length=1,
        max_length=120,
    )
    app_env: AppEnvironment = "development"
    auto_activate_uploads: bool = True
    use_hybrid_search: bool = True
    app_version: str = Field(default="0.1.0", pattern=r"^\d+\.\d+\.\d+$")
    log_level: LogLevel = "INFO"
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )
    db_host: str = Field(default="localhost", min_length=1, max_length=255)
    db_port: int = Field(default=5432, ge=1, le=65535)
    db_name: str = Field(default="oiap", min_length=1, max_length=63)
    db_user: str = Field(default="oiap", min_length=1, max_length=63)
    db_password: SecretStr = SecretStr("change-me")
    database_pool_size: int = Field(default=5, ge=1, le=50)
    database_connect_timeout_seconds: int = Field(default=5, ge=1, le=60)
    embedding_dimension: int = Field(
        default=DEFAULT_EMBEDDING_DIMENSION, ge=1, le=65535
    )
    rate_limit_requests: int = Field(default=5, ge=1, le=10000)
    rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600)
    rate_limit_trusted_proxy_hops: int = Field(default=1, ge=0, le=8)
    gemini_api_key: SecretStr | None = None
    gemini_model: str = Field(
        default=DEFAULT_GEMINI_MODEL,
        min_length=1,
        max_length=120,
    )
    gemini_embedding_model: str = Field(
        default=DEFAULT_GEMINI_EMBEDDING_MODEL,
        min_length=1,
        max_length=120,
    )
    otp_ttl_seconds: int = Field(default=600, ge=60, le=3600)
    otp_pepper: SecretStr = SecretStr("oiap-dev-otp-pepper")
    session_ttl_seconds: int = Field(default=1_209_600, ge=300, le=31_536_000)
    data_directory: Path = _REPOSITORY_ROOT / "data"
    avatar_max_bytes: int = Field(default=2_097_152, ge=1024, le=10_485_760)
    document_max_bytes: int = Field(default=20_971_520, ge=1024, le=104_857_600)
    smtp_host: str = Field(default="smtp.gmail.com", min_length=1, max_length=255)
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from: str | None = None
    smtp_use_tls: bool = True

    calendar_timezone: str = "UTC"
    event_smtp_host: str = Field(default="smtp.gmail.com", min_length=1, max_length=255)
    event_smtp_port: int = Field(default=587, ge=1, le=65535)
    event_smtp_username: str | None = None
    event_smtp_password: SecretStr | None = None
    event_smtp_from: str | None = None
    event_smtp_use_tls: bool = True

    @field_validator("calendar_timezone")
    @classmethod
    def validate_calendar_timezone(cls, value: str) -> str:
        value = value.strip()
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError("CALENDAR_TIMEZONE must be a valid IANA timezone.") from error
        return value

    @field_validator("event_smtp_host")
    @classmethod
    def validate_event_smtp_host(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("EVENT_SMTP_HOST must not be blank.")
        return value

    @property
    def calendar_zone(self) -> ZoneInfo:
        return ZoneInfo(self.calendar_timezone)

    @property
    def event_smtp_is_configured(self) -> bool:
        username = (self.event_smtp_username or "").strip()
        sender = (self.event_smtp_from or username).strip()
        password = (
            self.event_smtp_password.get_secret_value().strip()
            if self.event_smtp_password is not None else ""
        )
        return bool(username and sender and password)

    @model_validator(mode="before")
    @classmethod
    def set_auto_activation_default(cls, values: Any) -> Any:
        """Enable demo auto-activation by default outside production."""
        if isinstance(values, dict) and "auto_activate_uploads" not in values:
            values["auto_activate_uploads"] = values.get("app_env", "development") in {
                "development",
                "test",
            }
        return values

    @field_validator(
        "app_name",
        "app_version",
        "db_host",
        "db_name",
        "db_user",
        "gemini_model",
        "gemini_embedding_model",
        "smtp_host",
        mode="before",
    )
    @classmethod
    def reject_blank_strings(cls, value: object) -> object:
        """Reject values that contain only whitespace."""
        if isinstance(value, str) and not value.strip():
            raise ValueError("value must not be blank")
        return value

    @field_validator("api_prefix")
    @classmethod
    def validate_api_prefix(cls, value: str) -> str:
        """Require one normalized, absolute API path prefix."""
        if not value.startswith("/"):
            raise ValueError("API_PREFIX must start with '/'")
        if value == "/" or value.endswith("/"):
            raise ValueError("API_PREFIX must not be '/' or end with '/'")
        if "//" in value or any(character.isspace() for character in value):
            raise ValueError("API_PREFIX must be a normalized path without whitespace")
        return value

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, values: list[str]) -> list[str]:
        """Validate explicit browser origins; wildcard origins are forbidden."""
        if not values:
            raise ValueError("CORS_ORIGINS must contain at least one origin")

        normalized: list[str] = []
        for value in values:
            if value == "*":
                raise ValueError("wildcard CORS origins are not allowed")
            parsed = urlsplit(value)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.username is not None
                or parsed.password is not None
                or parsed.query
                or parsed.fragment
                or parsed.path not in {"", "/"}
            ):
                raise ValueError(f"invalid CORS origin: {value!r}")
            normalized.append(value.rstrip("/"))

        if len(set(normalized)) != len(normalized):
            raise ValueError("CORS_ORIGINS must not contain duplicates")
        return normalized

    @property
    def database_url_object(self) -> URL:
        """Build the PostgreSQL connection URL from the separate settings.

        The raw password is handed to ``URL.create`` unescaped on purpose.
        SQLAlchemy owns the escaping and applies it once, when the URL is
        rendered, so encoding it here as well would double-encode every
        reserved character and produce a password the server rejects.
        """
        return URL.create(
            drivername=DATABASE_DRIVERNAME,
            username=self.db_user,
            password=self.db_password.get_secret_value(),
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )

    @property
    def database_url(self) -> SecretStr:
        """Return the rendered connection URL for consumers that need a string.

        Kept as a ``SecretStr`` because the rendered form embeds the password.
        This is the interface the engine factory and the Alembic environment
        already depend on, so neither has to know how the URL is assembled.
        """
        return SecretStr(
            self.database_url_object.render_as_string(hide_password=False)
        )

    @property
    def smtp_is_configured(self) -> bool:
        """True when Gmail SMTP can send OTP mail."""
        username = (self.smtp_username or "").strip()
        sender = (self.smtp_from or username).strip()
        password = (
            self.smtp_password.get_secret_value().strip()
            if self.smtp_password is not None
            else ""
        )
        return bool(username and password and sender)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return one immutable-by-convention settings instance per process."""
    return Settings()
