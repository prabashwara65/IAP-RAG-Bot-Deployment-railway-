"""Signup, login, OTP verification, and logout."""

from __future__ import annotations

from typing import Annotated, NoReturn

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.dependencies import get_auth_service, get_bearer_token
from app.core.rate_limit import enforce_rate_limit
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    OtpIssuedResponse,
    ProfileResponse,
    ResetPasswordRequest,
    SessionResponse,
    SignupRequest,
    VerifyOtpRequest,
)
from app.schemas.common import ErrorDetail, ErrorResponse
from app.services.auth import (
    AuthError,
    AuthErrorCode,
    AuthService,
    IssuedOtp,
    IssuedSession,
    LoginOutcome,
)

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
    return SessionResponse(
        access_token=issued.access_token,
        user=ProfileResponse.from_account(issued.user),
    )


def _login_response(outcome: LoginOutcome) -> LoginResponse:
    if outcome.kind == "session" and outcome.session is not None:
        return LoginResponse(
            next_step="session",
            email=outcome.email,
            access_token=outcome.session.access_token,
            token_type="bearer",
            user=ProfileResponse.from_account(outcome.session.user),
        )
    if outcome.kind == "totp":
        return LoginResponse(next_step="totp", email=outcome.email)
    issued = outcome.otp
    if issued is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Sign-in could not be completed.",
        )
    return LoginResponse(
        next_step="email_otp",
        email=issued.email,
        otp_sent=True,
        expires_in_seconds=issued.expires_in_seconds,
        otp_code=issued.otp_code,
        delivery=issued.delivery,
    )


def _otp_failure_response(request: Request, error: AuthError) -> JSONResponse:
    """Return a normal response so the request session commits OTP state."""
    status_code = 404 if error.code is AuthErrorCode.ACCOUNT_NOT_FOUND else 422
    response = ErrorResponse(
        error=ErrorDetail(
            code=(
                error.code.value.upper()
                if error.code in {AuthErrorCode.OTP_LOCKED, AuthErrorCode.INVALID_OTP}
                else f"HTTP_{status_code}"
            ),
            message=str(error),
            correlation_id=getattr(request.state, "correlation_id", "unavailable"),
        )
    )
    return JSONResponse(status_code=status_code, content=response.model_dump(exclude_none=True))


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
    response_model=LoginResponse,
    dependencies=[Depends(enforce_rate_limit)],
)
def login(
    payload: LoginRequest,
    auth: Annotated[AuthService, Depends(get_auth_service)],
) -> LoginResponse:
    try:
        outcome = auth.request_login(email=payload.email, password=payload.password)
    except AuthError as error:
        _fail(error)
    return _login_response(outcome)


@router.post(
    "/reset-password",
    response_model=OtpIssuedResponse,
    dependencies=[Depends(enforce_rate_limit)],
)
def reset_password(
    payload: ResetPasswordRequest,
    auth: Annotated[AuthService, Depends(get_auth_service)],
) -> OtpIssuedResponse:
    try:
        issued = auth.request_reset_password(
            email=payload.email,
            new_password=payload.new_password,
        )
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
    request: Request,
    background_tasks: BackgroundTasks,
) -> SessionResponse | JSONResponse:
    try:
        issued = auth.verify_otp(email=payload.email, code=payload.code)
    except AuthError as error:
        if error.code in {
            AuthErrorCode.INVALID_OTP,
            AuthErrorCode.OTP_LOCKED,
            AuthErrorCode.OTP_EXPIRED,
            AuthErrorCode.ACCOUNT_NOT_FOUND,
        }:
            return _otp_failure_response(request, error)
        _fail(error)
    if issued.password_changed:
        background_tasks.add_task(auth.send_password_changed_notice, issued.user.email)
    return _session_response(issued)


@router.post(
    "/verify-totp",
    response_model=SessionResponse,
    dependencies=[Depends(enforce_rate_limit)],
)
def verify_totp(
    payload: VerifyOtpRequest,
    auth: Annotated[AuthService, Depends(get_auth_service)],
    request: Request,
) -> SessionResponse | JSONResponse:
    try:
        issued = auth.verify_totp(email=payload.email, code=payload.code)
    except AuthError as error:
        if error.code in {
            AuthErrorCode.INVALID_OTP,
            AuthErrorCode.OTP_LOCKED,
            AuthErrorCode.OTP_EXPIRED,
            AuthErrorCode.OTP_NOT_FOUND,
        }:
            return _otp_failure_response(request, error)
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