"""In-memory account store for auth tests that must not touch PostgreSQL."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.domain.accounts import (
    OtpChallenge,
    OtpPurpose,
    SessionRecord,
    ThemePreference,
    TwoFactorMethod,
    UserAccount,
)


class MemoryUserAccountRepository:
    def __init__(self) -> None:
        self.users: dict[UUID, UserAccount] = {}
        self.password_hashes: dict[UUID, str] = {}
        self.totp_secrets: dict[UUID, str | None] = {}
        self.totp_pending: dict[UUID, str | None] = {}
        self.otps: dict[UUID, OtpChallenge] = {}
        self.sessions: dict[str, SessionRecord] = {}

    def get_user_by_id(self, user_id: UUID) -> UserAccount | None:
        return self.users.get(user_id)

    def get_user_by_email(self, email: str) -> UserAccount | None:
        for user in self.users.values():
            if user.email == email:
                return user
        return None

    def get_password_hash_by_email(self, email: str) -> str | None:
        user = self.get_user_by_email(email)
        if user is None:
            return None
        return self.password_hashes.get(user.id)

    def create_user(
        self,
        *,
        email: str,
        display_name: str,
        theme: ThemePreference,
        password_hash: str,
    ) -> UserAccount:
        user = UserAccount(
            id=uuid4(),
            email=email,
            display_name=display_name,
            theme=theme,
            avatar_path=None,
            created_at=datetime.now(UTC),
        )
        self.users[user.id] = user
        self.password_hashes[user.id] = password_hash
        return user

    def update_user(
        self,
        user_id: UUID,
        *,
        display_name: str | None = None,
        theme: ThemePreference | None = None,
        avatar_path: str | None = None,
        clear_avatar: bool = False,
    ) -> UserAccount:
        user = self.users[user_id]
        path = user.avatar_path if avatar_path is None else avatar_path
        updated = UserAccount(
            id=user.id,
            email=user.email,
            display_name=user.display_name if display_name is None else display_name,
            theme=user.theme if theme is None else theme,
            avatar_path=None if clear_avatar else path,
            created_at=user.created_at,
            two_factor_method=user.two_factor_method,
        )
        self.users[user_id] = updated
        return updated

    def get_totp_material(self, user_id: UUID) -> tuple[str | None, str | None]:
        if user_id not in self.users:
            raise LookupError("user_not_found")
        return self.totp_secrets.get(user_id), self.totp_pending.get(user_id)

    def set_two_factor(
        self,
        user_id: UUID,
        *,
        method: TwoFactorMethod,
        totp_secret: str | None = None,
        totp_pending_secret: str | None = None,
        clear_totp_secret: bool = False,
        clear_pending_secret: bool = False,
    ) -> UserAccount:
        user = self.users[user_id]
        secret = self.totp_secrets.get(user_id)
        pending = self.totp_pending.get(user_id)
        if clear_totp_secret:
            secret = None
        elif totp_secret is not None:
            secret = totp_secret
        if clear_pending_secret:
            pending = None
        elif totp_pending_secret is not None:
            pending = totp_pending_secret
        self.totp_secrets[user_id] = secret
        self.totp_pending[user_id] = pending
        updated = UserAccount(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            theme=user.theme,
            avatar_path=user.avatar_path,
            created_at=user.created_at,
            two_factor_method=method,
        )
        self.users[user_id] = updated
        return updated

    def update_password(self, user_id: UUID, password_hash: str) -> None:
        if user_id not in self.users:
            raise LookupError("user_not_found")
        self.password_hashes[user_id] = password_hash

    def create_otp(
        self,
        *,
        email: str,
        purpose: OtpPurpose,
        code_hash: str,
        expires_at: datetime,
        display_name: str | None,
        password_hash: str | None,
    ) -> OtpChallenge:
        now = datetime.now(UTC)
        for otp_id, otp in list(self.otps.items()):
            if otp.email == email and otp.consumed_at is None:
                self.otps[otp_id] = OtpChallenge(
                    id=otp.id,
                    email=otp.email,
                    purpose=otp.purpose,
                    code_hash=otp.code_hash,
                    display_name=otp.display_name,
                    password_hash=otp.password_hash,
                    expires_at=otp.expires_at,
                    attempt_count=otp.attempt_count,
                    consumed_at=now,
                )
        challenge = OtpChallenge(
            id=uuid4(),
            email=email,
            purpose=purpose,
            code_hash=code_hash,
            display_name=display_name,
            password_hash=password_hash,
            expires_at=expires_at,
            attempt_count=0,
            consumed_at=None,
        )
        self.otps[challenge.id] = challenge
        return challenge

    def latest_open_otp(self, email: str) -> OtpChallenge | None:
        open_codes = [
            otp
            for otp in self.otps.values()
            if otp.email == email and otp.consumed_at is None
        ]
        if not open_codes:
            return None
        return max(open_codes, key=lambda item: item.expires_at)

    def consume_otp(self, otp_id: UUID) -> None:
        otp = self.otps[otp_id]
        self.otps[otp_id] = OtpChallenge(
            id=otp.id,
            email=otp.email,
            purpose=otp.purpose,
            code_hash=otp.code_hash,
            display_name=otp.display_name,
            password_hash=otp.password_hash,
            expires_at=otp.expires_at,
            attempt_count=otp.attempt_count,
            consumed_at=datetime.now(UTC),
        )

    def increment_otp_attempts(self, otp_id: UUID) -> int:
        otp = self.otps[otp_id]
        updated = OtpChallenge(
            id=otp.id,
            email=otp.email,
            purpose=otp.purpose,
            code_hash=otp.code_hash,
            display_name=otp.display_name,
            password_hash=otp.password_hash,
            expires_at=otp.expires_at,
            attempt_count=otp.attempt_count + 1,
            consumed_at=otp.consumed_at,
        )
        self.otps[otp_id] = updated
        return updated.attempt_count

    def create_session(
        self,
        *,
        user_id: UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> SessionRecord:
        record = SessionRecord(
            id=uuid4(),
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            revoked_at=None,
        )
        self.sessions[token_hash] = record
        return record

    def get_session_by_token_hash(self, token_hash: str) -> SessionRecord | None:
        return self.sessions.get(token_hash)

    def revoke_session(self, token_hash: str) -> None:
        record = self.sessions.get(token_hash)
        if record is None or record.revoked_at is not None:
            return
        self.sessions[token_hash] = SessionRecord(
            id=record.id,
            user_id=record.user_id,
            token_hash=record.token_hash,
            expires_at=record.expires_at,
            revoked_at=datetime.now(UTC),
        )
