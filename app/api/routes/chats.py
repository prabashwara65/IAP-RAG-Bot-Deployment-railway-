"""Routes for saving and retrieving user chat sessions."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_session
from app.domain.accounts import UserAccount
from app.repositories.saved_chats import SavedChatRepository
from app.schemas.chats import (
    SavedChatCreate,
    SavedChatDetail,
    SavedChatSummary,
)

router = APIRouter(prefix="/chats", tags=["chats"])


def _extract_title(payload: SavedChatCreate) -> str:
    if payload.title and payload.title.strip():
        return payload.title.strip()[:120]
    for msg in payload.messages:
        question = msg.get("question") or msg.get("content") or ""
        if isinstance(question, str) and question.strip():
            return question.strip()[:60]
    return "Saved Chat"


@router.post("", response_model=SavedChatSummary, status_code=status.HTTP_201_CREATED)
def save_chat(
    payload: SavedChatCreate,
    user: Annotated[UserAccount, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> SavedChatSummary:
    """Save an ongoing conversation to the user's account."""
    repository = SavedChatRepository(session)
    title = _extract_title(payload)
    model = repository.create(
        user_id=user.id,
        title=title,
        messages=payload.messages,
    )
    return SavedChatSummary(
        id=model.id,
        title=model.title,
        created_at=model.created_at,
        updated_at=model.updated_at,
        message_count=len(model.messages),
    )


@router.get("", response_model=list[SavedChatSummary])
def list_chats(
    user: Annotated[UserAccount, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> list[SavedChatSummary]:
    """List recent saved chats for the signed-in user."""
    repository = SavedChatRepository(session)
    models = repository.list_by_user(user.id)
    return [
        SavedChatSummary(
            id=m.id,
            title=m.title,
            created_at=m.created_at,
            updated_at=m.updated_at,
            message_count=len(m.messages),
        )
        for m in models
    ]


@router.get("/{chat_id}", response_model=SavedChatDetail)
def get_chat(
    chat_id: UUID,
    user: Annotated[UserAccount, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> SavedChatDetail:
    """Retrieve full conversation turns for a saved chat."""
    repository = SavedChatRepository(session)
    model = repository.get_by_id(user.id, chat_id)
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Saved chat not found.",
        )
    return SavedChatDetail(
        id=model.id,
        title=model.title,
        messages=model.messages,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chat(
    chat_id: UUID,
    user: Annotated[UserAccount, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> None:
    """Delete a saved chat from the user's account."""
    repository = SavedChatRepository(session)
    deleted = repository.delete(user.id, chat_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Saved chat not found.",
        )
