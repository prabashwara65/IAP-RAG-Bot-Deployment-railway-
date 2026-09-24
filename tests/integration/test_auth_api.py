"""Auth and profile HTTP contracts using an in-memory account store."""

from pathlib import Path

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from app.api.dependencies import get_account_repository
from app.core.config import Settings
from app.main import create_app
from app.services.auth import hash_password
from tests.fakes.user_accounts import MemoryUserAccountRepository

PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx"
    b"\x9cc```\x00\x00\x00\x04\x00\x01\xdd\x8d\xb4\x1c"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _application(tmp_path: Path) -> tuple[FastAPI, MemoryUserAccountRepository]:
    store = MemoryUserAccountRepository()
    application = create_app(
        Settings(  # type: ignore[call-arg]
            _env_file=None,
            app_env="test",
            gemini_api_key=SecretStr("test-api-key-not-a-real-secret"),
            data_directory=tmp_path,
            rate_limit_requests=1000,
        )
    )
    application.dependency_overrides[get_account_repository] = lambda: store
    return application, store


async def _client(application: FastAPI) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=application),
        base_url="http://testserver",
    )


async def test_signup_returns_the_otp_code(tmp_path: Path) -> None:
    application, _store = _application(tmp_path)
    async with await _client(application) as client:
        response = await client.post(
            "/api/v1/auth/signup",
            json={
                "email": "ada@example.com",
                "display_name": "Ada",
                "password": "password12",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["otp_sent"] is True
    assert body["email"] == "ada@example.com"
    assert body["delivery"] == "on_screen"
    assert body["otp_code"] is not None
    assert len(body["otp_code"]) == 6


async def test_verify_otp_returns_a_session_and_unlocks_profile(tmp_path: Path) -> None:
    application, _store = _application(tmp_path)
    async with await _client(application) as client:
        issued = await client.post(
            "/api/v1/auth/signup",
            json={
                "email": "ada@example.com",
                "display_name": "Ada",
                "password": "password12",
            },
        )
        code = issued.json()["otp_code"]
        verified = await client.post(
            "/api/v1/auth/verify",
            json={"email": "ada@example.com", "code": code},
        )
        token = verified.json()["access_token"]
        me = await client.get(
            "/api/v1/me",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert verified.status_code == 200
    assert me.status_code == 200
    assert me.json()["display_name"] == "Ada"
    assert me.json()["has_avatar"] is False
    assert me.json()["two_factor_method"] == "email_otp"


async def test_profile_requires_a_session(tmp_path: Path) -> None:
    application, _store = _application(tmp_path)
    async with await _client(application) as client:
        response = await client.get("/api/v1/me")

    assert response.status_code == 401


async def test_hr_ask_requires_a_session(tmp_path: Path) -> None:
    application, _store = _application(tmp_path)
    async with await _client(application) as client:
        response = await client.post(
            "/api/v1/hr/ask",
            json={"question": "How much leave?", "tenant_id": "tenant-synthetic"},
        )

    assert response.status_code == 401


async def test_avatar_upload_and_fetch(tmp_path: Path) -> None:
    application, _store = _application(tmp_path)
    async with await _client(application) as client:
        issued = await client.post(
            "/api/v1/auth/signup",
            json={
                "email": "ada@example.com",
                "display_name": "Ada",
                "password": "password12",
            },
        )
        verified = await client.post(
            "/api/v1/auth/verify",
            json={"email": "ada@example.com", "code": issued.json()["otp_code"]},
        )
        token = verified.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        uploaded = await client.post(
            "/api/v1/me/avatar",
            headers=headers,
            files={"file": ("photo.png", PNG, "image/png")},
        )
        fetched = await client.get("/api/v1/me/avatar", headers=headers)
        patched = await client.patch(
            "/api/v1/me",
            headers=headers,
            json={"theme": "dark", "display_name": "Ada Lovelace"},
        )

    assert uploaded.status_code == 200
    assert uploaded.json()["has_avatar"] is True
    assert fetched.status_code == 200
    assert fetched.content.startswith(b"\x89PNG")
    assert patched.json()["theme"] == "dark"
    assert patched.json()["display_name"] == "Ada Lovelace"
    assert patched.json()["two_factor_method"] == "email_otp"


async def test_duplicate_signup_is_conflict(tmp_path: Path) -> None:
    application, store = _application(tmp_path)
    store.create_user(
        email="ada@example.com",
        display_name="Ada",
        theme="system",
        password_hash=hash_password("password12"),
    )
    async with await _client(application) as client:
        response = await client.post(
            "/api/v1/auth/signup",
            json={
                "email": "ada@example.com",
                "display_name": "Ada",
                "password": "password12",
            },
        )

    assert response.status_code == 409


async def test_login_requires_password_then_otp(tmp_path: Path) -> None:
    application, _store = _application(tmp_path)
    async with await _client(application) as client:
        issued = await client.post(
            "/api/v1/auth/signup",
            json={
                "email": "ada@example.com",
                "display_name": "Ada",
                "password": "password12",
            },
        )
        await client.post(
            "/api/v1/auth/verify",
            json={"email": "ada@example.com", "code": issued.json()["otp_code"]},
        )
        rejected = await client.post(
            "/api/v1/auth/login",
            json={"email": "ada@example.com", "password": "wrong-password"},
        )
        login = await client.post(
            "/api/v1/auth/login",
            json={"email": "ada@example.com", "password": "password12"},
        )

    assert rejected.status_code == 401
    assert login.status_code == 200
    assert login.json()["otp_code"] is not None
    assert login.json()["delivery"] == "on_screen"


async def test_reset_password_flow_via_api(tmp_path: Path) -> None:
    application, _store = _application(tmp_path)
    async with await _client(application) as client:
        # Sign up
        issued = await client.post(
            "/api/v1/auth/signup",
            json={
                "email": "ada@example.com",
                "display_name": "Ada",
                "password": "password12",
            },
        )
        await client.post(
            "/api/v1/auth/verify",
            json={"email": "ada@example.com", "code": issued.json()["otp_code"]},
        )

        # Reset password
        reset_req = await client.post(
            "/api/v1/auth/reset-password",
            json={
                "email": "ada@example.com",
                "new_password": "NewSecretPassword123!",
            },
        )
        assert reset_req.status_code == 200
        reset_otp = reset_req.json()["otp_code"]

        # Verify OTP
        verify_resp = await client.post(
            "/api/v1/auth/verify",
            json={"email": "ada@example.com", "code": reset_otp},
        )
        assert verify_resp.status_code == 200

        # Login with new password
        login = await client.post(
            "/api/v1/auth/login",
            json={"email": "ada@example.com", "password": "NewSecretPassword123!"},
        )
        assert login.status_code == 200
