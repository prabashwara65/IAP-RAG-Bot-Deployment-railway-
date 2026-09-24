"""Email-and-password signup/login with Gmail OTP two-factor verification."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path

from app.core.config import Settings
from app.domain.accounts import THEME_VALUES, OtpPurpose, ThemePreference, UserAccount
from app.repositories.users import UserAccountRepository
from app.services.mail import Mailer, SmtpMailError, mailer_from_settings

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
OTP_LENGTH = 6
MAX_OTP_ATTEMPTS = 5
MIN_PASSWORD_LENGTH = 8
PBKDF2_ITERATIONS = 200_000
ALLOWED_AVATAR_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
JPEG_MAGIC = b"\xff\xd8\xff"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
WEBP_MAGIC = b"RIFF"


class AuthErrorCode(StrEnum):
    INVALID_EMAIL = "invalid_email"
    INVALID_DISPLAY_NAME = "invalid_display_name"
    INVALID_OTP = "invalid_otp"
    INVALID_PASSWORD = "invalid_password"
    INVALID_CREDENTIALS = "invalid_credentials"
    INVALID_THEME = "invalid_theme"
    ACCOUNT_EXISTS = "account_exists"
    ACCOUNT_NOT_FOUND = "account_not_found"
    OTP_EXPIRED = "otp_expired"
    OTP_NOT_FOUND = "otp_not_found"
    OTP_LOCKED = "otp_locked"
    UNAUTHENTICATED = "unauthenticated"
    INVALID_AVATAR = "invalid_avatar"
    AVATAR_TOO_LARGE = "avatar_too_large"
    MAIL_DELIVERY_FAILED = "mail_delivery_failed"


class AuthError(RuntimeError):
    def __init__(self, code: AuthErrorCode, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class IssuedOtp:
    email: str
    expires_in_seconds: int
    otp_code: str | None
    delivery: str


@dataclass(frozen=True)
class IssuedSession:
    access_token: str
    user: UserAccount


def normalize_email(value: str) -> str:
    return value.strip().lower()


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    return f"pbkdf2$sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    parts = stored.split("$")
    if len(parts) != 5 or parts[0] != "pbkdf2" or parts[1] != "sha256":
        return False
    try:
        iterations = int(parts[2])
        salt = bytes.fromhex(parts[3])
        expected = bytes.fromhex(parts[4])
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(digest, expected)


def _otp_digest(*, pepper: str, email: str, code: str) -> str:
    material = f"{pepper}:{email}:{code}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _validate_email(email: str) -> str:
    normalized = normalize_email(email)
    if not normalized or len(normalized) > 254 or EMAIL_PATTERN.match(normalized) is None:
        raise AuthError(AuthErrorCode.INVALID_EMAIL, "Enter a valid email address.")
    return normalized


def _validate_display_name(name: str) -> str:
    trimmed = name.strip()
    if not trimmed or len(trimmed) > 80:
        raise AuthError(
            AuthErrorCode.INVALID_DISPLAY_NAME,
            "Enter a display name between 1 and 80 characters.",
        )
    return trimmed


def _validate_password(password: str) -> str:
    if len(password) < MIN_PASSWORD_LENGTH or len(password) > 128:
        raise AuthError(
            AuthErrorCode.INVALID_PASSWORD,
            "Choose a password of at least 8 characters.",
        )
    if password.strip() != password or not password.strip():
        raise AuthError(
            AuthErrorCode.INVALID_PASSWORD,
            "Choose a password of at least 8 characters.",
        )
    return password


def _detect_image_type(content: bytes) -> str | None:
    if content.startswith(JPEG_MAGIC):
        return "image/jpeg"
    if content.startswith(PNG_MAGIC):
        return "image/png"
    if content.startswith(WEBP_MAGIC) and b"WEBP" in content[:16]:
        return "image/webp"
    return None


class AuthService:
    def __init__(
        self,
        repository: UserAccountRepository,
        settings: Settings,
        mailer: Mailer | None = None,
    ) -> None:
        self._repository = repository
        self._settings = settings
        self._mailer = mailer if mailer is not None else mailer_from_settings(settings)

    def request_signup(self, *, email: str, display_name: str, password: str) -> IssuedOtp:
        normalized_email = _validate_email(email)
        name = _validate_display_name(display_name)
        hashed = hash_password(_validate_password(password))
        if self._repository.get_user_by_email(normalized_email) is not None:
            raise AuthError(
                AuthErrorCode.ACCOUNT_EXISTS,
                "An account with this email already exists. Log in instead.",
            )
        return self._issue_otp(
            email=normalized_email,
            purpose="signup",
            display_name=name,
            password_hash=hashed,
        )

    def request_login(self, *, email: str, password: str) -> IssuedOtp:
        normalized_email = _validate_email(email)
        _validate_password(password)
        stored = self._repository.get_password_hash_by_email(normalized_email)
        if stored is None or not verify_password(password, stored):
            raise AuthError(
                AuthErrorCode.INVALID_CREDENTIALS,
                "That email or password is not correct.",
            )
        return self._issue_otp(
            email=normalized_email,
            purpose="login",
            display_name=None,
            password_hash=None,
        )

    def request_reset_password(self, *, email: str, new_password: str) -> IssuedOtp:
        normalized_email = _validate_email(email)
        _validate_password(new_password)
        existing = self._repository.get_user_by_email(normalized_email)
        if existing is None:
            raise AuthError(
                AuthErrorCode.ACCOUNT_NOT_FOUND,
                "No account was found for that email. Sign up first.",
            )
        hashed = hash_password(new_password)
        return self._issue_otp(
            email=normalized_email,
            purpose="login",
            display_name=None,
            password_hash=hashed,
        )

    def verify_otp(self, *, email: str, code: str) -> IssuedSession:
        normalized_email = _validate_email(email)
        challenge = self._repository.latest_open_otp(normalized_email)
        if challenge is None:
            raise AuthError(
                AuthErrorCode.OTP_NOT_FOUND,
                "No verification code is waiting for that email.",
            )
        if challenge.expires_at <= datetime.now(UTC):
            self._repository.consume_otp(challenge.id)
            raise AuthError(
                AuthErrorCode.OTP_EXPIRED,
                "That verification code has expired. Request a new one.",
            )
        if challenge.attempt_count >= MAX_OTP_ATTEMPTS:
            self._repository.consume_otp(challenge.id)
            raise AuthError(
                AuthErrorCode.OTP_LOCKED,
                "Too many incorrect codes. Request a new one.",
            )

        expected = _otp_digest(
            pepper=self._settings.otp_pepper.get_secret_value(),
            email=normalized_email,
            code=code.strip(),
        )
        if not hmac.compare_digest(expected, challenge.code_hash):
            attempts = self._repository.increment_otp_attempts(challenge.id)
            if attempts >= MAX_OTP_ATTEMPTS:
                self._repository.consume_otp(challenge.id)
                raise AuthError(
                    AuthErrorCode.OTP_LOCKED,
                    "Too many incorrect codes. Request a new one.",
                )
            raise AuthError(
                AuthErrorCode.INVALID_OTP,
                "That verification code is not correct.",
            )

        self._repository.consume_otp(challenge.id)
        if challenge.purpose == "signup":
            pending_hash = challenge.password_hash
            if not pending_hash:
                raise AuthError(
                    AuthErrorCode.INVALID_OTP,
                    "That verification code is not correct.",
                )
            user = self._repository.create_user(
                email=normalized_email,
                display_name=challenge.display_name or normalized_email.split("@", 1)[0],
                theme="system",
                password_hash=pending_hash,
            )
        else:
            existing = self._repository.get_user_by_email(normalized_email)
            if existing is None:
                raise AuthError(
                    AuthErrorCode.ACCOUNT_NOT_FOUND,
                    "No account was found for that email. Sign up first.",
                )
            if challenge.password_hash:
                self._repository.update_password(existing.id, challenge.password_hash)
            user = existing
        return self._open_session(user)

    def user_for_token(self, token: str) -> UserAccount:
        if not token.strip():
            raise AuthError(AuthErrorCode.UNAUTHENTICATED, "Sign in is required.")
        record = self._repository.get_session_by_token_hash(hash_secret(token.strip()))
        now = datetime.now(UTC)
        if (
            record is None
            or record.revoked_at is not None
            or record.expires_at <= now
        ):
            raise AuthError(AuthErrorCode.UNAUTHENTICATED, "Sign in is required.")
        user = self._repository.get_user_by_id(record.user_id)
        if user is None:
            raise AuthError(AuthErrorCode.UNAUTHENTICATED, "Sign in is required.")
        return user

    def logout(self, token: str) -> None:
        if token.strip():
            self._repository.revoke_session(hash_secret(token.strip()))

    def update_profile(
        self,
        user: UserAccount,
        *,
        display_name: str | None,
        theme: str | None,
    ) -> UserAccount:
        name = None if display_name is None else _validate_display_name(display_name)
        preference: ThemePreference | None = None
        if theme is not None:
            if theme not in THEME_VALUES:
                raise AuthError(AuthErrorCode.INVALID_THEME, "Choose light, dark, or system.")
            preference = theme
        return self._repository.update_user(
            user.id,
            display_name=name,
            theme=preference,
        )

    def save_avatar(self, user: UserAccount, content: bytes, declared_type: str) -> UserAccount:
        if len(content) == 0:
            raise AuthError(AuthErrorCode.INVALID_AVATAR, "Choose an image to upload.")
        if len(content) > self._settings.avatar_max_bytes:
            raise AuthError(
                AuthErrorCode.AVATAR_TOO_LARGE,
                "Choose an image smaller than 2 MB.",
            )
        detected = _detect_image_type(content)
        if detected is None or detected not in ALLOWED_AVATAR_TYPES:
            raise AuthError(
                AuthErrorCode.INVALID_AVATAR,
                "Upload a JPEG, PNG, or WebP image.",
            )
        if declared_type and declared_type not in ALLOWED_AVATAR_TYPES:
            raise AuthError(
                AuthErrorCode.INVALID_AVATAR,
                "Upload a JPEG, PNG, or WebP image.",
            )
        extension = ALLOWED_AVATAR_TYPES[detected]
        directory = Path(self._settings.data_directory) / "avatars"
        directory.mkdir(parents=True, exist_ok=True)
        filename = f"{user.id}{extension}"
        destination = directory / filename
        if user.avatar_path:
            previous = directory / Path(user.avatar_path).name
            if previous != destination and previous.is_file():
                previous.unlink()
        destination.write_bytes(content)
        return self._repository.update_user(user.id, avatar_path=filename)

    def clear_avatar(self, user: UserAccount) -> UserAccount:
        if user.avatar_path:
            previous = Path(self._settings.data_directory) / "avatars" / Path(user.avatar_path).name
            if previous.is_file():
                previous.unlink()
        return self._repository.update_user(user.id, clear_avatar=True)

    def avatar_file(self, user: UserAccount) -> Path | None:
        if not user.avatar_path:
            return None
        directory = Path(self._settings.data_directory) / "avatars"
        candidate = (directory / Path(user.avatar_path).name).resolve()
        root = directory.resolve()
        if not str(candidate).startswith(str(root)) or not candidate.is_file():
            return None
        return candidate

    def _issue_otp(
        self,
        *,
        email: str,
        purpose: OtpPurpose,
        display_name: str | None,
        password_hash: str | None,
    ) -> IssuedOtp:
        code = f"{secrets.randbelow(10**OTP_LENGTH):0{OTP_LENGTH}d}"
        expires_at = datetime.now(UTC) + timedelta(seconds=self._settings.otp_ttl_seconds)
        self._repository.create_otp(
            email=email,
            purpose=purpose,
            code_hash=_otp_digest(
                pepper=self._settings.otp_pepper.get_secret_value(),
                email=email,
                code=code,
            ),
            expires_at=expires_at,
            display_name=display_name,
            password_hash=password_hash,
        )
        if self._mailer is not None:
            try:
                self._mailer.send_otp(to_email=email, code=code, purpose=purpose)
            except SmtpMailError as error:
                raise AuthError(
                    AuthErrorCode.MAIL_DELIVERY_FAILED,
                    "The verification email could not be sent. Try again shortly.",
                ) from error
            return IssuedOtp(
                email=email,
                expires_in_seconds=self._settings.otp_ttl_seconds,
                otp_code=None,
                delivery="email",
            )
        reveal = self._settings.app_env in {"development", "test"}
        return IssuedOtp(
            email=email,
            expires_in_seconds=self._settings.otp_ttl_seconds,
            otp_code=code if reveal else None,
            delivery="on_screen" if reveal else "email",
        )

    def _open_session(self, user: UserAccount) -> IssuedSession:
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(seconds=self._settings.session_ttl_seconds)
        self._repository.create_session(
            user_id=user.id,
            token_hash=hash_secret(token),
            expires_at=expires_at,
        )
        return IssuedSession(access_token=token, user=user)
