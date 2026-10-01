"""Permission rules that also run with Python's standard-library test runner."""

import unittest
from uuid import uuid4

from app.domain.roles import Role, RolePermissionError, require_admin, validate_assignment


class RoleRuleTests(unittest.TestCase):
    def test_admin_can_manage_roles(self) -> None:
        require_admin(Role.ADMIN)

    def test_every_other_role_is_denied(self) -> None:
        for role in (Role.USER, Role.HR, Role.EMPLOYEE, Role.STUDENT):
            with self.subTest(role=role), self.assertRaises(RolePermissionError):
                require_admin(role)

    def test_all_four_assignment_choices_are_accepted(self) -> None:
        actor, target = uuid4(), uuid4()
        for role in (Role.ADMIN, Role.HR, Role.EMPLOYEE, Role.STUDENT):
            validate_assignment(actor, target, role)

    def test_regular_user_is_only_the_signup_default(self) -> None:
        with self.assertRaises(ValueError):
            validate_assignment(uuid4(), uuid4(), Role.USER)

    def test_self_demotion_is_denied(self) -> None:
        admin = uuid4()
        for role in (Role.HR, Role.EMPLOYEE, Role.STUDENT):
            with self.subTest(role=role), self.assertRaises(ValueError):
                validate_assignment(admin, admin, role)

    def test_saving_own_existing_admin_role_is_allowed(self) -> None:
        admin = uuid4()
        validate_assignment(admin, admin, Role.ADMIN)