"""Admin-only user listing and role assignment."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_session
from app.domain.accounts import UserAccount
from app.domain.roles import Role, RolePermissionError, require_admin
from app.schemas.admin_users import RoleUpdateRequest, RoleUpdateResponse, UserListResponse
from app.schemas.auth import ProfileResponse
from app.services.user_roles import UserRoleService

router = APIRouter(prefix="/admin/users", tags=["admin-users"])


def get_current_admin(
    user: Annotated[UserAccount, Depends(get_current_user)],
) -> UserAccount:
    try:
        require_admin(user.role)
    except RolePermissionError as error:
        raise HTTPException(403, str(error)) from error
    return user


@router.get("", response_model=UserListResponse)
def list_users(
    admin: Annotated[UserAccount, Depends(get_current_admin)],
    session: Annotated[Session, Depends(get_session)],
    search: Annotated[str, Query(max_length=254)] = "",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> UserListResponse:
    users, total = UserRoleService(session).list_users(
        admin, search=search, page=page, page_size=page_size
    )
    return UserListResponse(
        users=[ProfileResponse.from_account(user) for user in users],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.patch("/{user_id}/role", response_model=RoleUpdateResponse)
def update_role(
    user_id: UUID,
    payload: RoleUpdateRequest,
    admin: Annotated[UserAccount, Depends(get_current_admin)],
    session: Annotated[Session, Depends(get_session)],
) -> RoleUpdateResponse:
    try:
        updated = UserRoleService(session).assign_role(admin, user_id, Role(payload.role))
    except RolePermissionError as error:
        raise HTTPException(403, str(error)) from error
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    result = RoleUpdateResponse(user=ProfileResponse.from_account(updated))
    session.commit()
    return result