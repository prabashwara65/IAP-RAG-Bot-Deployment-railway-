"""Event-only SMTP delivery. Existing OTP mail and SMTP settings are untouched."""

from __future__ import annotations

import smtplib
from contextlib import suppress
from email.message import EmailMessage
from typing import Protocol

from app.core.config import Settings
from app.models.events import CalendarEventModel


class EventMailError(RuntimeError):
    """Curated failure; provider messages and credentials never reach the API."""


class EventMailer(Protocol):
    def send_confirmation(self, *, to_email: str, event: CalendarEventModel) -> None: ...


class EventSmtpMailer:
    def __init__(self, settings: Settings) -> None:
        self._host = settings.event_smtp_host
        self._port = settings.event_smtp_port
        self._username = (settings.event_smtp_username or "").strip()
        self._password = (
            settings.event_smtp_password.get_secret_value().strip()
            if settings.event_smtp_password is not None
            else ""
        )
        self._sender = (settings.event_smtp_from or self._username).strip()
        self._use_tls = settings.event_smtp_use_tls
        self._timezone = settings.calendar_timezone

    def send_confirmation(self, *, to_email: str, event: CalendarEventModel) -> None:
        if not self._username or not self._password or not self._sender:
            raise EventMailError("Event email is not configured.")
        message = EmailMessage()
        message["Subject"] = f"Event Scheduled: {event.title}"
        message["From"] = self._sender
        message["To"] = to_email
        body = (
            "Hello,\n\n"
            "Your event has been successfully scheduled in Office Assistant."
            "\n\nEvent Details"
            f"\n\nTitle: {event.title}"
            f"\nDate: {event.event_date.day} {event.event_date.strftime('%B %Y')}"
        )
        if event.event_time is not None:
            when = event.event_time.strftime("%I:%M %p").lstrip("0")
            body += f"\nTime: {when}"
        if event.description and event.description.strip():
            body += f"\n\nDescription:\n{event.description}"
        body += (
            "\n\nYou can review this event anytime from the Events section in Office Assistant."
            "\n\nRegards,\nOffice Assistant"
        )
        message.set_content(body + "\n")
        smtp: smtplib.SMTP | None = None
        try:
            smtp = smtplib.SMTP(self._host, self._port, timeout=20)
            if self._use_tls:
                smtp.starttls()
            smtp.login(self._username, self._password)
            if smtp.send_message(message):
                raise EventMailError("Event email could not be sent.")
        except Exception as error:
            raise EventMailError("Event email could not be sent.") from error
        finally:
            if smtp is not None:
                # Successful SMTP acceptance must survive a failed close.
                with suppress(OSError, smtplib.SMTPException):
                    smtp.close()


def event_mailer_from_settings(settings: Settings) -> EventSmtpMailer | None:
    if not settings.event_smtp_is_configured:
        return None
    return EventSmtpMailer(settings)
