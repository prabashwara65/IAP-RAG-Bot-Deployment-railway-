"""Authenticated events endpoints, isolated from chat and RAG."""

from __future__ import annotations

from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import SQLAlchemyError

from app.api.dependencies import get_current_user, get_event_service, get_request_settings
from app.core.config import Settings
from app.core.logging import get_logger
from app.domain.accounts import UserAccount
from app.schemas.events import (
    CalendarSettingsResponse,
    ConfirmEventResponse,
    CreateEventRequest,
    CreateEventResponse,
    EventResponse,
)
from app.services.events import (
    EventConflictError,
    EventNotFoundError,
    EventService,
    EventValidationError,
)

router = APIRouter(prefix="/events", tags=["events"])
logger = get_logger("api.events")


def _unavailable(error: SQLAlchemyError) -> NoReturn:
    logger.warning("Calendar persistence unavailable")
    raise HTTPException(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "The calendar service is unavailable.",
    ) from error


@router.get(
    "/settings",
    response_model=CalendarSettingsResponse,
    dependencies=[Depends(get_current_user)],
)
def calendar_settings(
    settings: Annotated[Settings, Depends(get_request_settings)],
) -> CalendarSettingsResponse:
    return CalendarSettingsResponse(timezone=settings.calendar_timezone)


@router.get("", response_model=list[EventResponse])
def list_events(
    user: Annotated[UserAccount, Depends(get_current_user)],
    service: Annotated[EventService, Depends(get_event_service)],
) -> list[EventResponse]:
    try:
        return [EventResponse.model_validate(event) for event in service.list_for_user(user.id)]
    except SQLAlchemyError as error:
        _unavailable(error)


@router.post("", response_model=CreateEventResponse, status_code=status.HTTP_201_CREATED)
def create_event(
    payload: CreateEventRequest,
    user: Annotated[UserAccount, Depends(get_current_user)],
    service: Annotated[EventService, Depends(get_event_service)],
) -> CreateEventResponse:
    try:
        event, email_sent = service.create(user, **payload.model_dump())
        return CreateEventResponse(
            **EventResponse.model_validate(event).model_dump(), email_sent=email_sent
        )
    except EventValidationError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    except SQLAlchemyError as error:
        _unavailable(error)


@router.patch("/{event_id}/confirm", response_model=ConfirmEventResponse)
def confirm_event(
    event_id: UUID,
    user: Annotated[UserAccount, Depends(get_current_user)],
    service: Annotated[EventService, Depends(get_event_service)],
) -> ConfirmEventResponse:
    try:
        event, email_sent = service.confirm(user, event_id)
        return ConfirmEventResponse(
            **EventResponse.model_validate(event).model_dump(),
            email_sent=email_sent,
        )
    except EventConflictError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    except EventNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found.") from error
    except SQLAlchemyError as error:
        _unavailable(error)


@router.patch("/{event_id}/cancel", response_model=EventResponse)
def cancel_event(
    event_id: UUID,
    user: Annotated[UserAccount, Depends(get_current_user)],
    service: Annotated[EventService, Depends(get_event_service)],
) -> EventResponse:
    try:
        return EventResponse.model_validate(service.cancel(user, event_id))
    except EventNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found.") from error
    except SQLAlchemyError as error:
        _unavailable(error)


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(
    event_id: UUID,
    user: Annotated[UserAccount, Depends(get_current_user)],
    service: Annotated[EventService, Depends(get_event_service)],
) -> Response:
    try:
        service.delete(user, event_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except EventNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found.") from error
    except SQLAlchemyError as error:
        _unavailable(error)
