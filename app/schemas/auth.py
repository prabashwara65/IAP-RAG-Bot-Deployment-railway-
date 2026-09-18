"""HTTP contracts for signup, OTP verification, sessions, and profile."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.accounts import ThemePreference, UserAccount


class SignupRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    display_name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=128)


class VerifyOtpRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    code: str = Field(min_length=4, max_length=12)


class OtpIssuedResponse(BaseModel):
    otp_sent: bool = True
    email: str
    expires_in_seconds: int
    otp_code: str | None = None
    delivery: str = "email"


class ProfileResponse(BaseModel):
    id: UUID
    email: str
    display_name: str
    theme: ThemePreference
    has_avatar: bool
    two_factor_method: str = "email_otp"

    @classmethod
    def from_account(cls, account: UserAccount) -> ProfileResponse:
        return cls(
            id=account.id,
            email=account.email,
            display_name=account.display_name,
            theme=account.theme,
            has_avatar=account.avatar_path is not None,
            two_factor_method="email_otp",
        )


class SessionResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: ProfileResponse


class ProfileUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    theme: ThemePreference | None = None
