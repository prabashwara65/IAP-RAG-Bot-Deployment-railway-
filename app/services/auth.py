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
from app.core.logging import get_logger
from app.domain.accounts import (
    THEME_VALUES,
    OtpPurpose,
    ThemePreference,
    TwoFactorMethod,
    UserAccount,
)
from app.repositories.users import UserAccountRepository
from app.services.mail import Mailer, SmtpMailError, mailer_from_settings
from app.services.totp import new_totp_secret, provisioning_uri, qr_svg, totp_matches

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
OTP_LENGTH = 6
MAX_OTP_ATTEMPTS = 5
logger = get_logger("auth")
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
    INVALID_TWO_FACTOR = "invalid_two_factor"
    TOTP_NOT_PENDING = "totp_not_pending"


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
    password_changed: bool = False


@dataclass(frozen=True)
class LoginOutcome:
    """Password check result: email code, authenticator code, or a session."""

    kind: str
    email: str
    otp: IssuedOtp | None = None
    session: IssuedSession | None = None


@dataclass(frozen=True)
class TotpSetup:
    secret: str
    otpauth_uri: str
    qr_svg: str


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


def _validate_password(password: str, *, require_strong: bool = False) -> str:
    message = (
        "Password must be at least 8 characters and include a capital letter, "
        "a number, and a symbol."
        if require_strong
        else "Choose a password of at least 8 characters."
    )
    if len(password) < MIN_PASSWORD_LENGTH or len(password) > 128:
        raise AuthError(AuthErrorCode.INVALID_PASSWORD, message)
    if password.strip() != password or not password.strip():
        raise AuthError(AuthErrorCode.INVALID_PASSWORD, message)
    if require_strong and not (
        re.search(r"[A-Z]", password)
        and re.search(r"[0-9]", password)
        and re.search(r"[^A-Za-z0-9]", password)
    ):
        raise AuthError(AuthErrorCode.INVALID_PASSWORD, message)
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
        hashed = hash_password(_validate_password(password, require_strong=True))
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

    def request_login(self, *, email: str, password: str) -> LoginOutcome:
        normalized_email = _validate_email(email)
        _validate_password(password)
        stored = self._repository.get_password_hash_by_email(normalized_email)
        if stored is None or not verify_password(password, stored):
            raise AuthError(
                AuthErrorCode.INVALID_CREDENTIALS,
                "That email or password is not correct.",
            )
        account = self._repository.get_user_by_email(normalized_email)
        if account is None:
            raise AuthError(
                AuthErrorCode.INVALID_CREDENTIALS,
                "That email or password is not correct.",
            )
        if account.two_factor_method == "none":
            return LoginOutcome(
                kind="session",
                email=normalized_email,
                session=self._open_session(account),
            )
        if account.two_factor_method == "totp":
            self._issue_totp_login_gate(normalized_email)
            return LoginOutcome(kind="totp", email=normalized_email)
        issued = self._issue_otp(
            email=normalized_email,
            purpose="login",
            display_name=None,
            password_hash=None,
        )
        return LoginOutcome(kind="email_otp", email=normalized_email, otp=issued)

    def request_reset_password(self, *, email: str, new_password: str) -> IssuedOtp:
        normalized_email = _validate_email(email)
        _validate_password(new_password, require_strong=True)
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

    def change_password(
        self, user: UserAccount, *, current_password: str, new_password: str,
    ) -> None:
        """Change only the signed-in user's password after verifying the old one."""
        stored = self._repository.get_password_hash_by_email(user.email)
        if stored is None or not verify_password(current_password, stored):
            raise AuthError(
                AuthErrorCode.INVALID_CREDENTIALS,
                "Your current password is not correct.",
            )
        _validate_password(new_password, require_strong=True)
        if verify_password(new_password, stored):
            raise AuthError(
                AuthErrorCode.INVALID_PASSWORD,
                "Choose a new password different from your current password.",
            )
        self._repository.update_password(user.id, hash_password(new_password))

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
        if challenge.purpose == "totp_login":
            raise AuthError(
                AuthErrorCode.INVALID_OTP,
                "Enter the code from your authenticator app.",
            )
        if challenge.attempt_count >= MAX_OTP_ATTEMPTS:
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
                self._repository.revoke_user_sessions(existing.id)
            user = existing

        changed = bool(challenge.password_hash) and challenge.purpose != "signup"
        issued = self._open_session(user, password_changed=changed)
        if changed:
            self._repository.commit_password_reset()
        return issued

    def verify_totp(self, *, email: str, code: str) -> IssuedSession:
        normalized_email = _validate_email(email)
        challenge = self._repository.latest_open_otp(normalized_email)
        if challenge is None or challenge.purpose != "totp_login":
            raise AuthError(
                AuthErrorCode.OTP_NOT_FOUND,
                "Sign in with your password before entering an authenticator code.",
            )
        if challenge.expires_at <= datetime.now(UTC):
            self._repository.consume_otp(challenge.id)
            raise AuthError(
                AuthErrorCode.OTP_EXPIRED,
                "That sign-in has expired. Enter your password again.",
            )
        if challenge.attempt_count >= MAX_OTP_ATTEMPTS:
            self._repository.consume_otp(challenge.id)
            raise AuthError(
                AuthErrorCode.OTP_LOCKED,
                "Too many incorrect codes. Sign in again.",
            )
        account = self._repository.get_user_by_email(normalized_email)
        secret = None if account is None else self._repository.get_totp_material(account.id)[0]
        if account is None or account.two_factor_method != "totp" or not secret:
            raise AuthError(
                AuthErrorCode.INVALID_OTP,
                "That authenticator code is not correct.",
            )
        if not totp_matches(secret, code):
            attempts = self._repository.increment_otp_attempts(challenge.id)
            if attempts >= MAX_OTP_ATTEMPTS:
                self._repository.consume_otp(challenge.id)
                raise AuthError(
                    AuthErrorCode.OTP_LOCKED,
                    "Too many incorrect codes. Sign in again.",
                )
            raise AuthError(
                AuthErrorCode.INVALID_OTP,
                "That authenticator code is not correct.",
            )
        self._repository.consume_otp(challenge.id)
        return self._open_session(account)

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

    def set_two_factor_method(self, user: UserAccount, method: str) -> UserAccount:
        if method not in {"none", "email_otp"}:
            raise AuthError(
                AuthErrorCode.INVALID_TWO_FACTOR,
                "Choose email codes, or turn two-factor authentication off.",
            )
        chosen: TwoFactorMethod = "none" if method == "none" else "email_otp"
        return self._repository.set_two_factor(
            user.id,
            method=chosen,
            clear_totp_secret=True,
            clear_pending_secret=True,
        )

    def begin_totp_setup(self, user: UserAccount) -> TotpSetup:
        secret = new_totp_secret()
        self._repository.set_two_factor(
            user.id,
            method=user.two_factor_method,
            totp_pending_secret=secret,
        )
        uri = provisioning_uri(secret=secret, email=user.email)
        return TotpSetup(secret=secret, otpauth_uri=uri, qr_svg=qr_svg(uri))

    def confirm_totp_setup(self, user: UserAccount, code: str) -> UserAccount:
        _active, pending = self._repository.get_totp_material(user.id)
        if not pending or not totp_matches(pending, code):
            if not pending:
                raise AuthError(
                    AuthErrorCode.TOTP_NOT_PENDING,
                    "Start authenticator setup before confirming a code.",
                )
            raise AuthError(
                AuthErrorCode.INVALID_OTP,
                "That authenticator code is not correct.",
            )
        return self._repository.set_two_factor(
            user.id,
            method="totp",
            totp_secret=pending,
            clear_pending_secret=True,
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

    def _issue_totp_login_gate(self, email: str) -> None:
        expires_at = datetime.now(UTC) + timedelta(seconds=self._settings.otp_ttl_seconds)
        self._repository.create_otp(
            email=email,
            purpose="totp_login",
            code_hash=hash_secret(secrets.token_urlsafe(16)),
            expires_at=expires_at,
            display_name=None,
            password_hash=None,
        )

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
                logger.warning(
                    "OTP email delivery failed",
                    extra={
                        "failure_code": AuthErrorCode.MAIL_DELIVERY_FAILED.value,
                        "smtp_error_type": type(error.__cause__).__name__
                        if error.__cause__ is not None
                        else type(error).__name__,
                    },
                )
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

    def send_password_changed_notice(self, email: str) -> None:
        """Send a security notice after the reset request has committed."""
        if self._mailer is not None:
            try:
                self._mailer.send_password_changed(to_email=email)
            except SmtpMailError:
                logger.warning("Password change notice could not be delivered")

    def _open_session(
        self,
        user: UserAccount,
        *,
        password_changed: bool = False,
    ) -> IssuedSession:
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(seconds=self._settings.session_ttl_seconds)
        self._repository.create_session(
            user_id=user.id,
            token_hash=hash_secret(token),
            expires_at=expires_at,
        )
        return IssuedSession(
            access_token=token,
            user=user,
            password_changed=password_changed,
        )