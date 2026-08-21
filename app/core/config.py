"""Typed application configuration."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

AppEnvironment = Literal["development", "test", "staging", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

DATABASE_DRIVERNAME = "postgresql+psycopg"
DEFAULT_OPENAI_MODEL = "gpt-5-mini"
DEFAULT_OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"


class Settings(BaseSettings):
    """Validated application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
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
    embedding_dimension: int = Field(default=1536, ge=1, le=65535)
    rate_limit_requests: int = Field(default=5, ge=1, le=10000)
    rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600)
    rate_limit_trusted_proxy_hops: int = Field(default=1, ge=0, le=8)
    openai_api_key: SecretStr | None = None
    openai_model: str = Field(
        default=DEFAULT_OPENAI_MODEL,
        min_length=1,
        max_length=120,
    )
    openai_embedding_model: str = Field(
        default=DEFAULT_OPENAI_EMBEDDING_MODEL,
        min_length=1,
        max_length=120,
    )

    @field_validator(
        "app_name",
        "app_version",
        "db_host",
        "db_name",
        "db_user",
        "openai_model",
        "openai_embedding_model",
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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return one immutable-by-convention settings instance per process."""
    return Settings()
