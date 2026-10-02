"""Validated admin user-management requests and responses."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.schemas.auth import ProfileResponse


class RoleUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["admin", "hr", "employee", "student"]


class UserListResponse(BaseModel):
    users: list[ProfileResponse]
    total: int
    page: int
    page_size: int


class RoleUpdateResponse(BaseModel):
    user: ProfileResponse
    message: str = "Role updated successfully."