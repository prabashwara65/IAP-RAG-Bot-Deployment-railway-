"""Repository for saved chat persistence."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.saved_chats import SavedChatModel


class SavedChatRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        *,
        user_id: UUID,
        title: str,
        messages: list[dict[str, Any]],
    ) -> SavedChatModel:
        model = SavedChatModel(
            user_id=user_id,
            title=title,
            messages=messages,
        )
        self._session.add(model)
        self._session.flush()
        return model

    def list_by_user(self, user_id: UUID) -> list[SavedChatModel]:
        statement = (
            select(SavedChatModel)
            .where(SavedChatModel.user_id == user_id)
            .order_by(desc(SavedChatModel.updated_at))
        )
        return list(self._session.scalars(statement).all())

    def get_by_id(self, user_id: UUID, chat_id: UUID) -> SavedChatModel | None:
        statement = select(SavedChatModel).where(
            SavedChatModel.id == chat_id,
            SavedChatModel.user_id == user_id,
        )
        return self._session.scalar(statement)

    def delete(self, user_id: UUID, chat_id: UUID) -> bool:
        model = self.get_by_id(user_id, chat_id)
        if model is None:
            return False
        self._session.delete(model)
        self._session.flush()
        return True
