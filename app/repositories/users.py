"""Account persistence contract without SQLAlchemy detail."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.domain.accounts import (
    OtpChallenge,
    OtpPurpose,
    SessionRecord,
    ThemePreference,
    TwoFactorMethod,
    UserAccount,
)


class UserAccountRepository(Protocol):
    def get_user_by_id(self, user_id: UUID) -> UserAccount | None: ...

    def get_user_by_email(self, email: str) -> UserAccount | None: ...

    def get_password_hash_by_email(self, email: str) -> str | None: ...

    def create_user(
        self,
        *,
        email: str,
        display_name: str,
        theme: ThemePreference,
        password_hash: str,
    ) -> UserAccount: ...

    def update_user(
        self,
        user_id: UUID,
        *,
        display_name: str | None = None,
        theme: ThemePreference | None = None,
        avatar_path: str | None = None,
        clear_avatar: bool = False,
    ) -> UserAccount: ...

    def update_password(self, user_id: UUID, password_hash: str) -> None: ...

    def get_totp_material(self, user_id: UUID) -> tuple[str | None, str | None]: ...

    def set_two_factor(
        self,
        user_id: UUID,
        *,
        method: TwoFactorMethod,
        totp_secret: str | None = None,
        totp_pending_secret: str | None = None,
        clear_totp_secret: bool = False,
        clear_pending_secret: bool = False,
    ) -> UserAccount: ...

    def create_otp(
        self,
        *,
        email: str,
        purpose: OtpPurpose,
        code_hash: str,
        expires_at: datetime,
        display_name: str | None,
        password_hash: str | None,
    ) -> OtpChallenge: ...

    def latest_open_otp(self, email: str) -> OtpChallenge | None: ...

    def consume_otp(self, otp_id: UUID) -> None: ...

    def increment_otp_attempts(self, otp_id: UUID) -> int: ...

    def create_session(
        self,
        *,
        user_id: UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> SessionRecord: ...

    def get_session_by_token_hash(self, token_hash: str) -> SessionRecord | None: ...

    def revoke_session(self, token_hash: str) -> None: ...
