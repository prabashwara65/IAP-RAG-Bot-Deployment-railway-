"""Gmail SMTP mailer: composition, configuration, and test doubles."""

import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.services.mail import (
    RecordingMailer,
    SmtpGmailMailer,
    SmtpMailError,
    mailer_from_settings,
)


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


def test_mailer_from_settings_is_absent_without_credentials() -> None:
    assert mailer_from_settings(_settings()) is None


def test_mailer_from_settings_uses_gmail_when_configured() -> None:
    settings = _settings(
        smtp_username="ada@gmail.com",
        smtp_password=SecretStr("app-password-not-real"),
        smtp_from="ada@gmail.com",
    )
    mailer = mailer_from_settings(settings)
    assert isinstance(mailer, SmtpGmailMailer)


def test_smtp_mailer_refuses_empty_credentials() -> None:
    mailer = SmtpGmailMailer(_settings())
    with pytest.raises(SmtpMailError):
        mailer.send_otp(to_email="ada@example.com", code="123456", purpose="login")


def test_recording_mailer_keeps_the_otp_for_tests() -> None:
    mailer = RecordingMailer()
    mailer.send_otp(to_email="ada@example.com", code="654321", purpose="signup")
    assert mailer.sent == [("ada@example.com", "654321", "signup")]
