"""Tests for safe PostgreSQL configuration built from separate DB_* values."""

import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy.engine import make_url

from app.core.config import DATABASE_DRIVERNAME, Settings

DB_SETTING_NAMES = ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD")

# Structurally awkward on purpose: every character here is reserved somewhere in
# a URL. It is a synthetic value, not a credential.
SPECIAL_CHARACTER_PASSWORD = "abc[]:#%xyz"


def _settings(**overrides: object) -> Settings:
    """Build settings without reading a developer's real local .env file."""
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


def test_local_defaults_build_a_valid_psycopg_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in DB_SETTING_NAMES:
        monkeypatch.delenv(name, raising=False)

    settings = _settings()
    url = make_url(settings.database_url.get_secret_value())

    assert url.drivername == DATABASE_DRIVERNAME == "postgresql+psycopg"
    assert url.host == "localhost"
    assert url.port == 5432
    assert url.database == "oiap"
    assert url.username == "oiap"
    assert url.password == "change-me"


def test_each_database_part_reaches_the_generated_url() -> None:
    settings = _settings(
        db_host="db.example.test",
        db_port=6543,
        db_name="oiap_test",
        db_user="oiap_app",
        db_password=SecretStr("plain-test-password"),
    )
    url = make_url(settings.database_url.get_secret_value())

    assert url.host == "db.example.test"
    assert url.port == 6543
    assert url.database == "oiap_test"
    assert url.username == "oiap_app"
    assert url.password == "plain-test-password"


def test_environment_variables_supply_the_database_parts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mirrors how ECS injects RDS values as separate environment variables."""
    monkeypatch.setenv("DB_HOST", "oiap.abc123.eu-west-1.rds.amazonaws.com")
    monkeypatch.setenv("DB_PORT", "5432")
    monkeypatch.setenv("DB_NAME", "oiap")
    monkeypatch.setenv("DB_USER", "oiap_master")
    monkeypatch.setenv("DB_PASSWORD", SPECIAL_CHARACTER_PASSWORD)

    settings = _settings()
    url = make_url(settings.database_url.get_secret_value())

    assert url.host == "oiap.abc123.eu-west-1.rds.amazonaws.com"
    assert url.username == "oiap_master"
    assert url.password == SPECIAL_CHARACTER_PASSWORD


def test_a_password_with_url_special_characters_survives_rendering() -> None:
    """The password is escaped exactly once, so parsing recovers the original."""
    settings = _settings(db_password=SecretStr(SPECIAL_CHARACTER_PASSWORD))
    rendered = settings.database_url.get_secret_value()

    assert SPECIAL_CHARACTER_PASSWORD not in rendered
    assert "abc%5B%5D%3A%23%25xyz" in rendered
    assert make_url(rendered).password == SPECIAL_CHARACTER_PASSWORD


def test_the_url_object_carries_the_raw_unescaped_password() -> None:
    """SQLAlchemy escapes at render time, so the object must hold the raw value."""
    settings = _settings(db_password=SecretStr(SPECIAL_CHARACTER_PASSWORD))

    assert settings.database_url_object.password == SPECIAL_CHARACTER_PASSWORD
    assert settings.database_url_object.drivername == "postgresql+psycopg"


@pytest.mark.parametrize("db_port", [0, -1, 65536, "not-a-port"])
def test_an_invalid_database_port_is_rejected(db_port: object) -> None:
    with pytest.raises(ValidationError):
        _settings(db_port=db_port)


@pytest.mark.parametrize("field", ["db_host", "db_name", "db_user"])
@pytest.mark.parametrize("value", ["", "   "])
def test_a_blank_required_database_field_is_rejected(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        _settings(**{field: value})


def test_the_database_password_is_redacted_from_representations() -> None:
    password = "do-not-display-this-password"
    settings = _settings(db_password=SecretStr(password))

    assert isinstance(settings.db_password, SecretStr)
    assert password not in repr(settings)
    assert password not in str(settings)
    assert password not in str(settings.model_dump())
    assert password not in str(settings.database_url)


def test_the_rendered_url_is_not_serialized_with_the_settings() -> None:
    """``database_url`` is a property, so it never leaks through model_dump."""
    settings = _settings(db_password=SecretStr("another-test-password"))

    assert "database_url" not in settings.model_dump()
    assert "another-test-password" not in str(settings.model_dump())


def test_remaining_database_settings_are_still_validated() -> None:
    settings = _settings(
        database_pool_size=3,
        database_connect_timeout_seconds=2,
        embedding_dimension=4,
    )

    assert settings.database_pool_size == 3
    assert settings.database_connect_timeout_seconds == 2
    assert settings.embedding_dimension == 4
