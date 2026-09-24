"""Auth service: passwords, OTP issue/verify, sessions, and avatar rules."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.domain.accounts import OtpPurpose
from app.services.auth import AuthError, AuthErrorCode, AuthService
from app.services.mail import RecordingMailer, SmtpMailError
from tests.fakes.user_accounts import MemoryUserAccountRepository

PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx"
    b"\x9cc```\x00\x00\x00\x04\x00\x01\xdd\x8d\xb4\x1c"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)
PASSWORD = "password12"


def _settings(tmp_path: Path) -> Settings:
    return Settings(  # type: ignore[call-arg]
        _env_file=None,
        app_env="test",
        gemini_api_key=SecretStr("test-api-key-not-a-real-secret"),
        data_directory=tmp_path,
        otp_ttl_seconds=600,
    )


def _service(tmp_path: Path) -> tuple[AuthService, MemoryUserAccountRepository]:
    store = MemoryUserAccountRepository()
    return AuthService(store, _settings(tmp_path)), store


def test_signup_returns_a_six_digit_otp_in_test(tmp_path: Path) -> None:
    service, _store = _service(tmp_path)

    issued = service.request_signup(
        email="Ada@Example.com",
        display_name=" Ada ",
        password=PASSWORD,
    )

    assert issued.email == "ada@example.com"
    assert issued.delivery == "on_screen"
    assert issued.otp_code is not None
    assert issued.otp_code.isdigit()
    assert len(issued.otp_code) == 6


def test_signup_rejects_an_existing_account(tmp_path: Path) -> None:
    service, _store = _service(tmp_path)
    issued = service.request_signup(
        email="ada@example.com",
        display_name="Ada",
        password=PASSWORD,
    )
    assert issued.otp_code is not None
    service.verify_otp(email="ada@example.com", code=issued.otp_code)

    with pytest.raises(AuthError) as error:
        service.request_signup(
            email="ada@example.com",
            display_name="Ada",
            password=PASSWORD,
        )
    assert error.value.code is AuthErrorCode.ACCOUNT_EXISTS


def test_signup_rejects_a_short_password(tmp_path: Path) -> None:
    service, _store = _service(tmp_path)

    with pytest.raises(AuthError) as error:
        service.request_signup(
            email="ada@example.com",
            display_name="Ada",
            password="short",
        )
    assert error.value.code is AuthErrorCode.INVALID_PASSWORD


def test_verify_signup_otp_creates_a_session(tmp_path: Path) -> None:
    service, store = _service(tmp_path)
    issued = service.request_signup(
        email="ada@example.com",
        display_name="Ada Lovelace",
        password=PASSWORD,
    )
    assert issued.otp_code is not None

    session = service.verify_otp(email="ada@example.com", code=issued.otp_code)

    assert session.user.display_name == "Ada Lovelace"
    assert service.user_for_token(session.access_token).email == "ada@example.com"
    assert store.latest_open_otp("ada@example.com") is None


def test_wrong_otp_is_rejected(tmp_path: Path) -> None:
    service, _store = _service(tmp_path)
    service.request_signup(email="ada@example.com", display_name="Ada", password=PASSWORD)

    with pytest.raises(AuthError) as error:
        service.verify_otp(email="ada@example.com", code="000000")
    assert error.value.code is AuthErrorCode.INVALID_OTP


def test_login_requires_an_existing_account(tmp_path: Path) -> None:
    service, _store = _service(tmp_path)

    with pytest.raises(AuthError) as error:
        service.request_login(email="missing@example.com", password=PASSWORD)
    assert error.value.code is AuthErrorCode.INVALID_CREDENTIALS


def test_login_rejects_the_wrong_password(tmp_path: Path) -> None:
    service, _store = _service(tmp_path)
    issued = service.request_signup(
        email="ada@example.com",
        display_name="Ada",
        password=PASSWORD,
    )
    assert issued.otp_code is not None
    service.verify_otp(email="ada@example.com", code=issued.otp_code)

    with pytest.raises(AuthError) as error:
        service.request_login(email="ada@example.com", password="wrong-password")
    assert error.value.code is AuthErrorCode.INVALID_CREDENTIALS


def test_login_issues_email_otp_after_the_password(tmp_path: Path) -> None:
    service, _store = _service(tmp_path)
    issued = service.request_signup(
        email="ada@example.com",
        display_name="Ada",
        password=PASSWORD,
    )
    assert issued.otp_code is not None
    service.verify_otp(email="ada@example.com", code=issued.otp_code)

    login = service.request_login(email="ada@example.com", password=PASSWORD)

    assert login.delivery == "on_screen"
    assert login.otp_code is not None
    session = service.verify_otp(email="ada@example.com", code=login.otp_code)
    assert session.user.email == "ada@example.com"


def test_logout_revokes_the_session(tmp_path: Path) -> None:
    service, _store = _service(tmp_path)
    issued = service.request_signup(
        email="ada@example.com",
        display_name="Ada",
        password=PASSWORD,
    )
    assert issued.otp_code is not None
    session = service.verify_otp(email="ada@example.com", code=issued.otp_code)

    service.logout(session.access_token)

    with pytest.raises(AuthError) as error:
        service.user_for_token(session.access_token)
    assert error.value.code is AuthErrorCode.UNAUTHENTICATED


def test_expired_otp_is_rejected(tmp_path: Path) -> None:
    service, store = _service(tmp_path)
    issued = service.request_signup(
        email="ada@example.com",
        display_name="Ada",
        password=PASSWORD,
    )
    assert issued.otp_code is not None
    challenge = store.latest_open_otp("ada@example.com")
    assert challenge is not None
    store.otps[challenge.id] = type(challenge)(
        id=challenge.id,
        email=challenge.email,
        purpose=challenge.purpose,
        code_hash=challenge.code_hash,
        display_name=challenge.display_name,
        password_hash=challenge.password_hash,
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
        attempt_count=challenge.attempt_count,
        consumed_at=challenge.consumed_at,
    )

    with pytest.raises(AuthError) as error:
        service.verify_otp(email="ada@example.com", code=issued.otp_code)
    assert error.value.code is AuthErrorCode.OTP_EXPIRED


def test_configured_mailer_hides_the_otp_code(tmp_path: Path) -> None:
    store = MemoryUserAccountRepository()
    mailer = RecordingMailer()
    service = AuthService(store, _settings(tmp_path), mailer=mailer)

    issued = service.request_signup(
        email="ada@example.com",
        display_name="Ada",
        password=PASSWORD,
    )

    assert issued.otp_code is None
    assert issued.delivery == "email"
    assert len(mailer.sent) == 1
    assert mailer.sent[0][0] == "ada@example.com"
    assert mailer.sent[0][1].isdigit()
    assert len(mailer.sent[0][1]) == 6
    assert mailer.sent[0][2] == "signup"
    session = service.verify_otp(email="ada@example.com", code=mailer.sent[0][1])
    assert session.user.email == "ada@example.com"


def test_mail_delivery_failure_is_surfaced(tmp_path: Path) -> None:
    class FailingMailer:
        def send_otp(self, *, to_email: str, code: str, purpose: OtpPurpose) -> None:
            raise SmtpMailError("SMTP send failed: SMTPException.")

    service = AuthService(
        MemoryUserAccountRepository(),
        _settings(tmp_path),
        mailer=FailingMailer(),
    )

    with pytest.raises(AuthError) as error:
        service.request_signup(
            email="ada@example.com",
            display_name="Ada",
            password=PASSWORD,
        )
    assert error.value.code is AuthErrorCode.MAIL_DELIVERY_FAILED


def test_avatar_upload_accepts_png(tmp_path: Path) -> None:
    service, _store = _service(tmp_path)
    issued = service.request_signup(
        email="ada@example.com",
        display_name="Ada",
        password=PASSWORD,
    )
    assert issued.otp_code is not None
    session = service.verify_otp(email="ada@example.com", code=issued.otp_code)

    updated = service.save_avatar(session.user, PNG, "image/png")

    assert updated.avatar_path is not None
    path = service.avatar_file(updated)
    assert path is not None
    assert path.read_bytes().startswith(b"\x89PNG")


def test_avatar_upload_rejects_non_images(tmp_path: Path) -> None:
    service, _store = _service(tmp_path)
    issued = service.request_signup(
        email="ada@example.com",
        display_name="Ada",
        password=PASSWORD,
    )
    assert issued.otp_code is not None
    session = service.verify_otp(email="ada@example.com", code=issued.otp_code)

    with pytest.raises(AuthError) as error:
        service.save_avatar(session.user, b"not-an-image", "text/plain")
    assert error.value.code is AuthErrorCode.INVALID_AVATAR


def test_reset_password_updates_password(tmp_path: Path) -> None:
    service, _store = _service(tmp_path)
    signup_issued = service.request_signup(
        email="ada@example.com",
        display_name="Ada",
        password=PASSWORD,
    )
    assert signup_issued.otp_code is not None
    service.verify_otp(email="ada@example.com", code=signup_issued.otp_code)

    # Request password reset
    new_password = "BrandNewPassword123!"
    reset_issued = service.request_reset_password(
        email="ada@example.com",
        new_password=new_password,
    )
    assert reset_issued.otp_code is not None
    session = service.verify_otp(email="ada@example.com", code=reset_issued.otp_code)
    assert session.user.email == "ada@example.com"

    # Login with new password works
    login_issued = service.request_login(
        email="ada@example.com",
        password=new_password,
    )
    assert login_issued.otp_code is not None

    # Login with old password fails
    with pytest.raises(AuthError) as error:
        service.request_login(email="ada@example.com", password=PASSWORD)
    assert error.value.code is AuthErrorCode.INVALID_CREDENTIALS


def test_reset_password_unknown_email_rejected(tmp_path: Path) -> None:
    service, _store = _service(tmp_path)
    with pytest.raises(AuthError) as error:
        service.request_reset_password(
            email="nobody@example.com",
            new_password="BrandNewPassword123!",
        )
    assert error.value.code is AuthErrorCode.ACCOUNT_NOT_FOUND
