"""Signup, login, OTP verification, and logout."""

from __future__ import annotations

from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.dependencies import get_auth_service, get_bearer_token
from app.core.rate_limit import enforce_rate_limit
from app.schemas.auth import (
    LoginRequest,
    OtpIssuedResponse,
    SessionResponse,
    SignupRequest,
    VerifyOtpRequest,
)
from app.services.auth import AuthError, AuthErrorCode, AuthService, IssuedOtp, IssuedSession

router = APIRouter(prefix="/auth", tags=["auth"])
_bearer = HTTPBearer(auto_error=False)

_CLIENT_CODES = {
    AuthErrorCode.INVALID_EMAIL,
    AuthErrorCode.INVALID_DISPLAY_NAME,
    AuthErrorCode.INVALID_OTP,
    AuthErrorCode.INVALID_PASSWORD,
    AuthErrorCode.ACCOUNT_EXISTS,
    AuthErrorCode.ACCOUNT_NOT_FOUND,
    AuthErrorCode.OTP_EXPIRED,
    AuthErrorCode.OTP_NOT_FOUND,
    AuthErrorCode.OTP_LOCKED,
}


def _fail(error: AuthError) -> NoReturn:
    status_code = (
        status.HTTP_422_UNPROCESSABLE_ENTITY
        if error.code in _CLIENT_CODES
        else status.HTTP_401_UNAUTHORIZED
    )
    if error.code is AuthErrorCode.ACCOUNT_EXISTS:
        status_code = status.HTTP_409_CONFLICT
    if error.code is AuthErrorCode.ACCOUNT_NOT_FOUND:
        status_code = status.HTTP_404_NOT_FOUND
    if error.code is AuthErrorCode.UNAUTHENTICATED:
        status_code = status.HTTP_401_UNAUTHORIZED
    if error.code is AuthErrorCode.INVALID_CREDENTIALS:
        status_code = status.HTTP_401_UNAUTHORIZED
    if error.code is AuthErrorCode.MAIL_DELIVERY_FAILED:
        status_code = status.HTTP_502_BAD_GATEWAY
    raise HTTPException(status_code=status_code, detail=str(error)) from error


def _otp_response(issued: IssuedOtp) -> OtpIssuedResponse:
    return OtpIssuedResponse(
        email=issued.email,
        expires_in_seconds=issued.expires_in_seconds,
        otp_code=issued.otp_code,
        delivery=issued.delivery,
    )


def _session_response(issued: IssuedSession) -> SessionResponse:
    from app.schemas.auth import ProfileResponse

    return SessionResponse(
        access_token=issued.access_token,
        user=ProfileResponse.from_account(issued.user),
    )


@router.post(
    "/signup",
    response_model=OtpIssuedResponse,
    dependencies=[Depends(enforce_rate_limit)],
)
def signup(
    payload: SignupRequest,
    auth: Annotated[AuthService, Depends(get_auth_service)],
) -> OtpIssuedResponse:
    try:
        issued = auth.request_signup(
            email=payload.email,
            display_name=payload.display_name,
            password=payload.password,
        )
    except AuthError as error:
        _fail(error)
    return _otp_response(issued)


@router.post(
    "/login",
    response_model=OtpIssuedResponse,
    dependencies=[Depends(enforce_rate_limit)],
)
def login(
    payload: LoginRequest,
    auth: Annotated[AuthService, Depends(get_auth_service)],
) -> OtpIssuedResponse:
    try:
        issued = auth.request_login(email=payload.email, password=payload.password)
    except AuthError as error:
        _fail(error)
    return _otp_response(issued)


@router.post(
    "/verify",
    response_model=SessionResponse,
    dependencies=[Depends(enforce_rate_limit)],
)
def verify(
    payload: VerifyOtpRequest,
    auth: Annotated[AuthService, Depends(get_auth_service)],
) -> SessionResponse:
    try:
        issued = auth.verify_otp(email=payload.email, code=payload.code)
    except AuthError as error:
        _fail(error)
    return _session_response(issued)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    auth: Annotated[AuthService, Depends(get_auth_service)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> None:
    token = get_bearer_token(request, credentials)
    auth.logout(token or "")
