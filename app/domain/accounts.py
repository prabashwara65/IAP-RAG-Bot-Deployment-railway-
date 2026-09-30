"""Account, OTP, and session records used by the auth service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

ThemePreference = Literal["light", "dark", "system"]
OtpPurpose = Literal["signup", "login", "totp_login"]
TwoFactorMethod = Literal["none", "email_otp", "totp"]

THEME_VALUES: tuple[ThemePreference, ...] = ("light", "dark", "system")
TWO_FACTOR_METHODS: tuple[TwoFactorMethod, ...] = ("none", "email_otp", "totp")


@dataclass(frozen=True)
class UserAccount:
    """One signed-in person identified by email."""

    id: UUID
    email: str
    display_name: str
    theme: ThemePreference
    avatar_path: str | None
    created_at: datetime
    two_factor_method: TwoFactorMethod = "email_otp"


@dataclass(frozen=True)
class OtpChallenge:
    """A single-use verification code issued for signup or login."""

    id: UUID
    email: str
    purpose: OtpPurpose
    code_hash: str
    display_name: str | None
    password_hash: str | None
    expires_at: datetime
    attempt_count: int
    consumed_at: datetime | None


@dataclass(frozen=True)
class SessionRecord:
    """A bearer session bound to one user until expiry or logout."""

    id: UUID
    user_id: UUID
    token_hash: str
    expires_at: datetime
    revoked_at: datetime | None
