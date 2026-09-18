"""Current-user profile and avatar endpoints."""

from __future__ import annotations

from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from app.api.dependencies import get_auth_service, get_current_user
from app.domain.accounts import UserAccount
from app.schemas.auth import ProfileResponse, ProfileUpdateRequest
from app.services.auth import AuthError, AuthErrorCode, AuthService

router = APIRouter(prefix="/me", tags=["profile"])

_AVATAR_MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def _fail(error: AuthError) -> NoReturn:
    mapping = {
        AuthErrorCode.UNAUTHENTICATED: status.HTTP_401_UNAUTHORIZED,
        AuthErrorCode.INVALID_DISPLAY_NAME: status.HTTP_422_UNPROCESSABLE_ENTITY,
        AuthErrorCode.INVALID_THEME: status.HTTP_422_UNPROCESSABLE_ENTITY,
        AuthErrorCode.INVALID_AVATAR: status.HTTP_422_UNPROCESSABLE_ENTITY,
        AuthErrorCode.AVATAR_TOO_LARGE: 413,
    }
    raise HTTPException(
        status_code=mapping.get(error.code, status.HTTP_400_BAD_REQUEST),
        detail=str(error),
    ) from error


@router.get("", response_model=ProfileResponse)
def read_profile(
    user: Annotated[UserAccount, Depends(get_current_user)],
) -> ProfileResponse:
    return ProfileResponse.from_account(user)


@router.patch("", response_model=ProfileResponse)
def update_profile(
    payload: ProfileUpdateRequest,
    user: Annotated[UserAccount, Depends(get_current_user)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
) -> ProfileResponse:
    try:
        updated = auth.update_profile(
            user,
            display_name=payload.display_name,
            theme=payload.theme,
        )
    except AuthError as error:
        _fail(error)
    return ProfileResponse.from_account(updated)


@router.get("/avatar")
def read_avatar(
    user: Annotated[UserAccount, Depends(get_current_user)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
) -> FileResponse:
    path = auth.avatar_file(user)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No profile image is set.")
    media_type = _AVATAR_MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path, media_type=media_type)


@router.post("/avatar", response_model=ProfileResponse)
async def upload_avatar(
    user: Annotated[UserAccount, Depends(get_current_user)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    file: Annotated[UploadFile, File()],
) -> ProfileResponse:
    content = await file.read()
    try:
        updated = auth.save_avatar(user, content, file.content_type or "")
    except AuthError as error:
        _fail(error)
    return ProfileResponse.from_account(updated)


@router.delete("/avatar", response_model=ProfileResponse)
def delete_avatar(
    user: Annotated[UserAccount, Depends(get_current_user)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
) -> ProfileResponse:
    try:
        updated = auth.clear_avatar(user)
    except AuthError as error:
        _fail(error)
    return ProfileResponse.from_account(updated)
