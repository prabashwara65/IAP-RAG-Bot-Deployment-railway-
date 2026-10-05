"""Calendar API contracts; clients cannot supply ownership or recipients."""

from __future__ import annotations

from datetime import date, datetime, time
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CreateEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    event_date: date
    event_time: time | None = None
    send_email: bool = Field(default=False, strict=True)

    @field_validator("title")
    @classmethod
    def single_line_title(cls, value: str) -> str:
        if any(ord(character) < 32 or ord(character) == 127 for character in value):
            raise ValueError("Use a single-line event title.")
        return value

    @field_validator("description")
    @classmethod
    def optional_description(cls, value: str | None) -> str | None:
        return value or None

    @field_validator("event_time")
    @classmethod
    def local_minute_time(cls, value: time | None) -> time | None:
        if value is not None and (value.tzinfo is not None or value.second or value.microsecond):
            raise ValueError("Use local hours and minutes without a timezone suffix.")
        return value


class EventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    description: str | None
    event_date: date
    event_time: time | None
    completed: bool
    cancelled: bool
    confirmation_email_sent: bool
    created_at: datetime
    updated_at: datetime


class CreateEventResponse(EventResponse):
    email_sent: bool


class ConfirmEventResponse(EventResponse):
    email_sent: bool


class CalendarSettingsResponse(BaseModel):
    timezone: str
