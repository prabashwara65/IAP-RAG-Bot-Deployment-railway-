"""Gmail SMTP delivery for one-time passcodes.

This module is the only place that talks to an SMTP server. Auth never logs
the message body, the OTP, or the mailbox password.
"""

from __future__ import annotations

import smtplib
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Protocol

from app.core.config import Settings
from app.domain.accounts import OtpPurpose

OTP_SUBJECT = {
    "signup": "Your OIAP verification code",
    "login": "Your OIAP sign-in code",
}


class Mailer(Protocol):
    def send_otp(self, *, to_email: str, code: str, purpose: OtpPurpose) -> None: ...


class SmtpMailError(RuntimeError):
    """Raised when Gmail SMTP cannot accept a message."""


def _compose_message(
    *,
    sender: str,
    to_email: str,
    code: str,
    purpose: OtpPurpose,
) -> EmailMessage:
    action = (
        "finish creating your account"
        if purpose == "signup"
        else "complete two-factor sign-in"
    )
    message = EmailMessage()
    message["Subject"] = OTP_SUBJECT[purpose]
    message["From"] = sender
    message["To"] = to_email
    message.set_content(
        f"Your OIAP HR Assistant code is {code}.\n\n"
        f"Use it to {action}. It expires in 10 minutes.\n\n"
        "If you did not request this, you can ignore the message.\n"
    )
    return message


class SmtpGmailMailer:
    """Send OTP messages through Gmail's SMTP submission endpoint."""

    def __init__(self, settings: Settings) -> None:
        self._host = settings.smtp_host
        self._port = settings.smtp_port
        self._username = (settings.smtp_username or "").strip()
        self._password = (
            settings.smtp_password.get_secret_value()
            if settings.smtp_password is not None
            else ""
        )
        self._sender = (settings.smtp_from or self._username).strip()
        self._use_tls = settings.smtp_use_tls

    def send_otp(self, *, to_email: str, code: str, purpose: OtpPurpose) -> None:
        if not self._username or not self._password or not self._sender:
            raise SmtpMailError("SMTP is not configured.")
        message = _compose_message(
            sender=self._sender,
            to_email=to_email,
            code=code,
            purpose=purpose,
        )
        try:
            with smtplib.SMTP(self._host, self._port, timeout=20) as smtp:
                if self._use_tls:
                    smtp.starttls()
                smtp.login(self._username, self._password)
                smtp.send_message(message)
        except Exception as error:
            raise SmtpMailError(f"SMTP send failed: {type(error).__name__}.") from error


@dataclass
class RecordingMailer:
    """Test double that records OTP deliveries without a network."""

    sent: list[tuple[str, str, OtpPurpose]] = field(default_factory=list)

    def send_otp(self, *, to_email: str, code: str, purpose: OtpPurpose) -> None:
        self.sent.append((to_email, code, purpose))


def mailer_from_settings(settings: Settings) -> Mailer | None:
    """Return a Gmail SMTP mailer when credentials are present."""
    if not settings.smtp_is_configured:
        return None
    return SmtpGmailMailer(settings)
