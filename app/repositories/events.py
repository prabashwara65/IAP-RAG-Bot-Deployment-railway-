"""Owner-filtered calendar persistence and an atomic completion transition."""

from __future__ import annotations

from datetime import date, time
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.models.events import CalendarEventModel


class EventRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        *,
        user_id: UUID,
        title: str,
        description: str | None,
        event_date: date,
        event_time: time | None,
    ) -> CalendarEventModel:
        event = CalendarEventModel(
            user_id=user_id,
            title=title,
            description=description,
            event_date=event_date,
            event_time=event_time,
            completed=False,
            cancelled=False,
            confirmation_email_sent=False,
        )
        self._session.add(event)
        self._session.flush()
        return event

    def list_for_user(self, user_id: UUID) -> list[CalendarEventModel]:
        return list(
            self._session.scalars(
                select(CalendarEventModel)
                .where(CalendarEventModel.user_id == user_id)
                .order_by(
                    CalendarEventModel.event_date,
                    CalendarEventModel.event_time.asc().nullsfirst(),
                    CalendarEventModel.created_at,
                    CalendarEventModel.id,
                ),
            )
        )

    def get_owned(self, user_id: UUID, event_id: UUID) -> CalendarEventModel | None:
        return self._session.scalar(
            select(CalendarEventModel)
            .where(
                CalendarEventModel.id == event_id,
                CalendarEventModel.user_id == user_id,
            )
            .execution_options(populate_existing=True),
        )

    def complete_if_pending(self, user_id: UUID, event_id: UUID) -> CalendarEventModel | None:
        # PostgreSQL rechecks this predicate after a concurrent row update commits.
        # Only the request that changes false -> true may attempt SMTP.
        return self._session.scalar(
            update(CalendarEventModel)
            .where(
                CalendarEventModel.id == event_id,
                CalendarEventModel.user_id == user_id,
                CalendarEventModel.completed.is_(False),
                CalendarEventModel.cancelled.is_(False),
            )
            .values(completed=True)
            .returning(CalendarEventModel),
        )

    def mark_email_sent(self, event: CalendarEventModel) -> None:
        event.confirmation_email_sent = True
        self._session.flush()

    def cancel_owned(self, user_id: UUID, event_id: UUID) -> CalendarEventModel | None:
        return self._session.scalar(
            update(CalendarEventModel)
            .where(
                CalendarEventModel.id == event_id,
                CalendarEventModel.user_id == user_id,
                CalendarEventModel.cancelled.is_(False),
            )
            .values(cancelled=True)
            .returning(CalendarEventModel),
        )

    def delete_owned(self, user_id: UUID, event_id: UUID) -> bool:
        deleted = self._session.scalar(
            delete(CalendarEventModel)
            .where(
                CalendarEventModel.id == event_id,
                CalendarEventModel.user_id == user_id,
            )
            .returning(CalendarEventModel.id),
        )
        return deleted is not None
