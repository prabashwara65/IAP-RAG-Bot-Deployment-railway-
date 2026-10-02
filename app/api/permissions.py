"""Reusable authorization checks for authenticated administrators."""
from typing import Annotated
from fastapi import Depends, HTTPException, status
from app.api.dependencies import get_current_user
from app.domain.accounts import UserAccount
from app.domain.roles import Role


def get_current_admin(
    user: Annotated[UserAccount, Depends(get_current_user)],
) -> UserAccount:
    """Use the authenticated account's server-side role, never a request role."""
    if user.role != Role.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can upload documents.",
        )
    return user
