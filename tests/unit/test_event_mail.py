"""Isolated Event SMTP tests; every network connection is mocked."""

import smtplib
from datetime import UTC, date, datetime, time
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.models.events import CalendarEventModel
from app.services.event_mail import EventMailError, EventSmtpMailer, event_mailer_from_settings
from app.services.mail import SmtpGmailMailer


def settings(**changes):
    values = dict(
        smtp_host="otp.smtp.example",
        smtp_username="otp@example.com",
        smtp_password=SecretStr("synthetic-otp-password"),
        smtp_from="otp-sender@example.com",
        event_smtp_host="event.smtp.example",
        event_smtp_username="event@example.com",
        event_smtp_password=SecretStr("synthetic-event-password"),
        event_smtp_from="event-sender@example.com",
    )
    values.update(changes)
    return Settings(_env_file=None, **values)


def event(**changes):
    values = dict(
        id=uuid4(),
        user_id=uuid4(),
        title="Team Meeting",
        description="Discuss requirements",
        event_date=date(2099, 10, 12),
        event_time=time(10, 0),
        completed=True,
        confirmation_email_sent=False,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    values.update(changes)
    return CalendarEventModel(**values)


def smtp_fake(monkeypatch):
    smtp = MagicMock()
    smtp.__enter__.return_value = smtp
    smtp.send_message.return_value = {}
    constructor = MagicMock(return_value=smtp)
    monkeypatch.setattr("smtplib.SMTP", constructor)
    return smtp, constructor


def test_event_mail_uses_only_event_credentials_and_authenticated_recipient(monkeypatch):
    smtp, constructor = smtp_fake(monkeypatch)
    EventSmtpMailer(settings()).send_confirmation(to_email="signed-in@example.com", event=event())
    constructor.assert_called_once_with("event.smtp.example", 587, timeout=20)
    smtp.login.assert_called_once_with("event@example.com", "synthetic-event-password")
    message = smtp.send_message.call_args.args[0]
    assert message["From"] == "event-sender@example.com"
    assert message["To"] == "signed-in@example.com"
    assert message["Subject"] == "Event Scheduled: Team Meeting"
    assert message.get_content() == (
        "Hello,\n\n"
        "Your event has been successfully scheduled in Office Assistant.\n\n"
        "Event Details\n\n"
        "Title: Team Meeting\n"
        "Date: 12 October 2099\n"
        "Time: 10:00 AM\n\n"
        "Description:\nDiscuss requirements\n\n"
        "You can review this event anytime from the Events section in Office Assistant.\n\n"
        "Regards,\nOffice Assistant\n"
    )


def test_otp_sender_stays_independent_when_both_configurations_exist(monkeypatch):
    smtp, constructor = smtp_fake(monkeypatch)
    configured = settings()
    SmtpGmailMailer(configured).send_otp(
        to_email="signed-in@example.com", code="123456", purpose="login"
    )
    constructor.assert_called_once_with("otp.smtp.example", 587, timeout=20)
    smtp.login.assert_called_once_with("otp@example.com", "synthetic-otp-password")
    assert smtp.send_message.call_args.args[0]["From"] == "otp-sender@example.com"


def test_no_fallback_to_configured_otp_credentials(monkeypatch):
    smtp, constructor = smtp_fake(monkeypatch)
    configured = settings(event_smtp_username=None, event_smtp_password=None, event_smtp_from=None)
    assert configured.smtp_is_configured
    assert not configured.event_smtp_is_configured
    assert event_mailer_from_settings(configured) is None
    with pytest.raises(EventMailError):
        EventSmtpMailer(configured).send_confirmation(
            to_email="signed-in@example.com", event=event()
        )
    constructor.assert_not_called()
    smtp.send_message.assert_not_called()


@pytest.mark.parametrize("description", [None, "", "   "])
def test_missing_details_omitted_and_default_sender(monkeypatch, description):
    smtp, _ = smtp_fake(monkeypatch)
    EventSmtpMailer(settings(event_smtp_from=None)).send_confirmation(
        to_email="signed-in@example.com",
        event=event(description=description, event_time=None),
    )
    message = smtp.send_message.call_args.args[0]
    assert message["From"] == "event@example.com"
    body = message.get_content()
    assert "Description:" not in body
    assert "Time:" not in body
    assert "Timezone:" not in body
    assert "Not specified" not in body and "Not provided" not in body


def test_delivery_failure_is_curated(monkeypatch):
    smtp, _ = smtp_fake(monkeypatch)
    smtp.send_message.side_effect = smtplib.SMTPException("synthetic provider private text")
    with pytest.raises(EventMailError) as failure:
        EventSmtpMailer(settings()).send_confirmation(
            to_email="signed-in@example.com", event=event()
        )
    assert "private" not in str(failure.value)


def test_recipient_refusal_is_failure(monkeypatch):
    smtp, _ = smtp_fake(monkeypatch)
    smtp.send_message.return_value = {"signed-in@example.com": (550, b"synthetic refusal")}
    with pytest.raises(EventMailError):
        EventSmtpMailer(settings()).send_confirmation(
            to_email="signed-in@example.com", event=event()
        )


def test_cleanup_failure_after_acceptance_does_not_report_failed_delivery(monkeypatch):
    smtp, _ = smtp_fake(monkeypatch)
    smtp.close.side_effect = smtplib.SMTPServerDisconnected("synthetic closed connection")
    EventSmtpMailer(settings()).send_confirmation(to_email="signed-in@example.com", event=event())


def test_event_password_hidden_by_settings():
    configured = settings()
    assert "synthetic-event-password" not in repr(configured)
    assert "synthetic-otp-password" not in repr(configured)


def test_scheduled_notification_preserves_full_multiline_description(monkeypatch):
    smtp, _ = smtp_fake(monkeypatch)
    description = "Meeting agenda:\n" + "Full event details. " * 80 + "\nFinal instructions."
    EventSmtpMailer(settings(calendar_timezone="Asia/Colombo")).send_confirmation(
        to_email="signed-in@example.com",
        event=event(description=description, event_time=time(13, 20)),
    )
    message = smtp.send_message.call_args.args[0]
    body = message.get_content()
    assert description in body
    assert "Time: 1:20 PM" in body
    assert "Timezone:" not in body and "Asia/Colombo" not in body


@pytest.mark.parametrize(
    ("description", "event_time", "expected", "omitted"),
    [
        ("Full description", None, "Description:\nFull description", "Time:"),
        (None, time(8, 20), "Time: 8:20 AM", "Description:"),
    ],
)
def test_optional_sections_are_independent(monkeypatch, description, event_time, expected, omitted):
    smtp, _ = smtp_fake(monkeypatch)
    EventSmtpMailer(settings()).send_confirmation(
        to_email="signed-in@example.com",
        event=event(description=description, event_time=event_time),
    )
    body = smtp.send_message.call_args.args[0].get_content()
    assert expected in body
    assert omitted not in body
    assert "Timezone:" not in body
