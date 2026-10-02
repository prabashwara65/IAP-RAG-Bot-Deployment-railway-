"""Gmail SMTP delivery for one-time passcodes.

This module is the only place that talks to an SMTP server. Auth never logs
the message body, the OTP, or the mailbox password.
"""

from __future__ import annotations

import smtplib
from dataclasses import dataclass, field
from email.message import EmailMessage
from html import escape
from typing import Protocol

from app.core.config import Settings
from app.domain.accounts import OtpPurpose

OTP_SUBJECT = {
    "signup": "Your OIAP verification code",
    "login": "Your OIAP sign-in code",
}


class Mailer(Protocol):
    def send_otp(
        self,
        *,
        to_email: str,
        code: str,
        purpose: OtpPurpose,
        user_name: str | None = None,
    ) -> None: ...


class SmtpMailError(RuntimeError):
    """Raised when Gmail SMTP cannot accept a message."""


def _compose_message(
    *,
    sender: str,
    to_email: str,
    code: str,
    purpose: OtpPurpose,
    user_name: str | None = None,
    expires_in_seconds: int = 600,
) -> EmailMessage:
    name = (user_name or "").strip() or "there"
    instruction = (
        "Use this code to verify your email and complete your sign-up:"
        if purpose == "signup"
        else "Use this code to complete your two-factor sign-in:"
    )
    minutes, seconds = divmod(expires_in_seconds, 60)
    if seconds == 0:
        lifetime = f"{minutes} minute{'s' if minutes != 1 else ''}"
    else:
        lifetime = f"{expires_in_seconds} seconds"
    expiry_notice = (
        f"This code expires in {lifetime}. "
        "If you did not request this, you can ignore this email."
    )

    message = EmailMessage()
    message["Subject"] = OTP_SUBJECT[purpose]
    message["From"] = sender
    message["To"] = to_email
    message.set_content(
        f"Hi {name},\n\n"
        f"{instruction}\n\n"
        f"{code}\n\n"
        f"{expiry_notice}\n\n"
        "OIAP HR Assistant\n"
    )
    message.add_alternative(
        f"""\
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OIAP verification code</title>
</head>
<body style="margin:0; padding:0; background-color:#121212;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
           style="background-color:#121212;">
        <tr>
            <td align="center" style="padding:24px 12px;">
                <table role="presentation" width="100%" cellspacing="0"
                       cellpadding="0" border="0"
                       style="max-width:600px; background-color:#121212;">
                    <tr>
                        <td style="padding:0 12px;
                                   font-family:Georgia, 'Times New Roman', serif;">
                            <p style="margin:0 0 22px; font-size:24px;
                                      line-height:1.4; color:#f5f5f5;">
                                Hi {escape(name)},
                            </p>
                            <p style="margin:0 0 34px; font-size:23px;
                                      line-height:1.4; color:#f5f5f5;">
                                {escape(instruction)}
                            </p>
                            <p style="margin:0 0 30px; font-size:50px; line-height:1.2;
                                      font-weight:bold; letter-spacing:8px; color:#00B4D8;">
                                {escape(code)}
                            </p>
                            <p style="margin:0 0 46px; font-size:19px;
                                      line-height:1.4; color:#bdbdbd;">
                                {escape(expiry_notice)}
                            </p>
                            <p style="margin:0; font-size:18px;
                                      line-height:1.4; color:#888888;">
                                OIAP HR Assistant
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
""",
        subtype="html",
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
        self._otp_ttl_seconds = settings.otp_ttl_seconds

    def send_otp(
        self,
        *,
        to_email: str,
        code: str,
        purpose: OtpPurpose,
        user_name: str | None = None,
    ) -> None:
        if not self._username or not self._password or not self._sender:
            raise SmtpMailError("SMTP is not configured.")
        message = _compose_message(
            sender=self._sender,
            to_email=to_email,
            code=code,
            purpose=purpose,
            user_name=user_name,
            expires_in_seconds=self._otp_ttl_seconds,
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

    def send_otp(
        self,
        *,
        to_email: str,
        code: str,
        purpose: OtpPurpose,
        user_name: str | None = None,
    ) -> None:
        self.sent.append((to_email, code, purpose))


def mailer_from_settings(settings: Settings) -> Mailer | None:
    """Return a Gmail SMTP mailer when credentials are present."""
    if not settings.smtp_is_configured:
        return None
    return SmtpGmailMailer(settings)
