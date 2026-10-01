"""Admin role management using portable SQLAlchemy queries."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domain.accounts import UserAccount
from app.domain.roles import Role, require_admin, validate_assignment
from app.models.users import UserModel
from app.repositories.sqlalchemy_users import user_account_from_model

logger = get_logger("services.user_roles")


class UserRoleService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_users(
        self, actor: UserAccount, *, search: str, page: int, page_size: int
    ) -> tuple[list[UserAccount], int]:
        require_admin(actor.role)
        query = select(UserModel)
        count_query = select(func.count()).select_from(UserModel)
        if search.strip():
            # Escape LIKE wildcard characters so search text remains literal.
            term = search.strip().lower().replace("/", "//").replace("%", "/%")
            term = term.replace("_", "/_")
            condition = or_(
                func.lower(UserModel.email).like(f"%{term}%", escape="/"),
                func.lower(UserModel.display_name).like(f"%{term}%", escape="/"),
            )
            query = query.where(condition)
            count_query = count_query.where(condition)
        total = int(self._session.scalar(count_query) or 0)
        models = self._session.scalars(
            query.order_by(UserModel.display_name, UserModel.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return [user_account_from_model(model) for model in models], total

    def assign_role(self, actor: UserAccount, target_id: UUID, role: Role) -> UserAccount:
        validate_assignment(actor.id, target_id, role)
        # Lock both accounts in a stable order and refresh cached ORM values.
        # A concurrent demotion must take effect before this authorization check.
        models = self._session.scalars(
            select(UserModel)
            .where(UserModel.id.in_({actor.id, target_id}))
            .order_by(UserModel.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).all()
        accounts = {model.id: model for model in models}
        acting_model = accounts.get(actor.id)
        if acting_model is None:
            raise LookupError("Administrator account was not found.")
        require_admin(Role(acting_model.role))
        target = accounts.get(target_id)
        if target is None:
            raise LookupError("User was not found.")
        previous_role = target.role
        target.role = role.value
        target.updated_at = datetime.now(UTC)
        self._session.flush()
        logger.info(
            "User role updated",
            extra={
                "actor_id": str(actor.id),
                "target_user_id": str(target.id),
                "previous_role": previous_role,
                "new_role": role.value,
            },
        )
        return user_account_from_model(target)