"""Portable SQLAlchemy implementation of the account repository."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.accounts import (
    OtpChallenge,
    OtpPurpose,
    SessionRecord,
    ThemePreference,
    TwoFactorMethod,
    UserAccount,
)
from app.domain.roles import Role
from app.models.users import OtpChallengeModel, SessionModel, UserModel


def user_account_from_model(model: UserModel) -> UserAccount:
    theme: ThemePreference = model.theme  # type: ignore[assignment]
    raw_method = model.two_factor_method
    if raw_method == "none":
        method: TwoFactorMethod = "none"
    elif raw_method == "totp":
        method = "totp"
    else:
        method = "email_otp"
    return UserAccount(
        id=model.id,
        role=Role(model.role),
        email=model.email,
        display_name=model.display_name,
        theme=theme,
        avatar_path=model.avatar_path,
        created_at=model.created_at,
        two_factor_method=method,
    )


def _otp_from_model(model: OtpChallengeModel) -> OtpChallenge:
    purpose: OtpPurpose = model.purpose  # type: ignore[assignment]
    return OtpChallenge(
        id=model.id,
        email=model.email,
        purpose=purpose,
        code_hash=model.code_hash,
        display_name=model.display_name,
        password_hash=model.password_hash,
        expires_at=model.expires_at,
        attempt_count=model.attempt_count,
        consumed_at=model.consumed_at,
    )


def _session_from_model(model: SessionModel) -> SessionRecord:
    return SessionRecord(
        id=model.id,
        user_id=model.user_id,
        token_hash=model.token_hash,
        expires_at=model.expires_at,
        revoked_at=model.revoked_at,
    )


class SQLAlchemyUserAccountRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_user_by_id(self, user_id: UUID) -> UserAccount | None:
        model = self._session.get(UserModel, user_id)
        return None if model is None else user_account_from_model(model)

    def get_user_by_email(self, email: str) -> UserAccount | None:
        model = self._session.scalar(select(UserModel).where(UserModel.email == email))
        return None if model is None else user_account_from_model(model)

    def get_password_hash_by_email(self, email: str) -> str | None:
        model = self._session.scalar(select(UserModel).where(UserModel.email == email))
        return None if model is None else model.password_hash

    def create_user(
        self,
        *,
        email: str,
        display_name: str,
        theme: ThemePreference,
        password_hash: str,
    ) -> UserAccount:
        model = UserModel(
            email=email,
            display_name=display_name,
            theme=theme,
            password_hash=password_hash,
            two_factor_method="email_otp",
            role=Role.USER.value,
        )
        self._session.add(model)
        self._session.flush()
        return user_account_from_model(model)

    def update_user(
        self,
        user_id: UUID,
        *,
        display_name: str | None = None,
        theme: ThemePreference | None = None,
        avatar_path: str | None = None,
        clear_avatar: bool = False,
    ) -> UserAccount:
        model = self._session.get(UserModel, user_id)
        if model is None:
            raise LookupError("user_not_found")
        if display_name is not None:
            model.display_name = display_name
        if theme is not None:
            model.theme = theme
        if clear_avatar:
            model.avatar_path = None
        elif avatar_path is not None:
            model.avatar_path = avatar_path
        model.updated_at = datetime.now(UTC)
        self._session.flush()
        return user_account_from_model(model)

    def get_totp_material(self, user_id: UUID) -> tuple[str | None, str | None]:
        model = self._session.get(UserModel, user_id)
        if model is None:
            raise LookupError("user_not_found")
        return model.totp_secret, model.totp_pending_secret

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
        model = self._session.get(UserModel, user_id)
        if model is None:
            raise LookupError("user_not_found")
        model.two_factor_method = method
        if clear_totp_secret:
            model.totp_secret = None
        elif totp_secret is not None:
            model.totp_secret = totp_secret
        if clear_pending_secret:
            model.totp_pending_secret = None
        elif totp_pending_secret is not None:
            model.totp_pending_secret = totp_pending_secret
        model.updated_at = datetime.now(UTC)
        self._session.flush()
        return user_account_from_model(model)

    def update_password(self, user_id: UUID, password_hash: str) -> None:
        model = self._session.get(UserModel, user_id)
        if model is None:
            raise LookupError("user_not_found")
        model.password_hash = password_hash
        model.updated_at = datetime.now(UTC)
        self._session.flush()

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
        open_rows = self._session.scalars(
            select(OtpChallengeModel).where(
                OtpChallengeModel.email == email,
                OtpChallengeModel.consumed_at.is_(None),
            )
        )
        for row in open_rows:
            row.consumed_at = now
        model = OtpChallengeModel(
            email=email,
            purpose=purpose,
            code_hash=code_hash,
            expires_at=expires_at,
            display_name=display_name,
            password_hash=password_hash,
        )
        self._session.add(model)
        self._session.flush()
        return _otp_from_model(model)

    def latest_open_otp(self, email: str) -> OtpChallenge | None:
        model = self._session.scalar(
            select(OtpChallengeModel)
            .where(
                OtpChallengeModel.email == email,
                OtpChallengeModel.consumed_at.is_(None),
            )
            .order_by(OtpChallengeModel.created_at.desc())
        )
        return None if model is None else _otp_from_model(model)

    def consume_otp(self, otp_id: UUID) -> None:
        model = self._session.get(OtpChallengeModel, otp_id)
        if model is not None:
            model.consumed_at = datetime.now(UTC)
            self._session.flush()

    def increment_otp_attempts(self, otp_id: UUID) -> int:
        model = self._session.get(OtpChallengeModel, otp_id)
        if model is None:
            raise LookupError("otp_not_found")
        model.attempt_count += 1
        self._session.flush()
        return model.attempt_count

    def create_session(
        self,
        *,
        user_id: UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> SessionRecord:
        model = SessionModel(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self._session.add(model)
        self._session.flush()
        return _session_from_model(model)

    def get_session_by_token_hash(self, token_hash: str) -> SessionRecord | None:
        model = self._session.scalar(
            select(SessionModel).where(SessionModel.token_hash == token_hash)
        )
        return None if model is None else _session_from_model(model)

    def revoke_session(self, token_hash: str) -> None:
        model = self._session.scalar(
            select(SessionModel).where(SessionModel.token_hash == token_hash)
        )
        if model is not None and model.revoked_at is None:
            model.revoked_at = datetime.now(UTC)
            self._session.flush()