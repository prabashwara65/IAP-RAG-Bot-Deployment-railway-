"""Roles for this assistant. Public signup always creates a regular user."""

from enum import StrEnum


class Role(StrEnum):
    USER = "user"
    ADMIN = "admin"
    HR = "hr"
    EMPLOYEE = "employee"
    STUDENT = "student"


ASSIGNABLE_ROLES = frozenset({Role.ADMIN, Role.HR, Role.EMPLOYEE, Role.STUDENT})


class RolePermissionError(PermissionError):
    """An account is not allowed to manage roles."""


def require_admin(role: Role) -> None:
    if role is not Role.ADMIN:
        raise RolePermissionError("Only administrators can manage user roles.")


def validate_assignment(actor_id: object, target_id: object, role: Role) -> None:
    if role not in ASSIGNABLE_ROLES:
        raise ValueError("Choose Admin, HR, Employee, or Student.")
    if actor_id == target_id and role is not Role.ADMIN:
        raise ValueError("You cannot remove your own administrator access.")