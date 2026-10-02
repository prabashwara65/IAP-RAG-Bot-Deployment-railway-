"""Pydantic schemas for saved chat sessions."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class SavedChatCreate(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    messages: list[dict[str, Any]] = Field(min_length=1)


class SavedChatSummary(BaseModel):
    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int


class SavedChatDetail(BaseModel):
    id: UUID
    title: str
    messages: list[dict[str, Any]]
    created_at: datetime
    updated_at: datetime
