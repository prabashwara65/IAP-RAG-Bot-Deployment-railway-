"""Focused service/config/input checks; no database or real mail."""

from datetime import UTC, date, datetime, time
from unittest.mock import Mock
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings
from app.domain.accounts import UserAccount
from app.models.events import CalendarEventModel
from app.schemas.events import CreateEventRequest
from app.services.event_mail import EventMailError
from app.services.events import EventNotFoundError, EventService, EventValidationError


def user() -> UserAccount:
    return UserAccount(
        id=uuid4(),
        email="synthetic@example.com",
        display_name="Synthetic User",
        theme="system",
        avatar_path=None,
        created_at=datetime.now(UTC),
    )


def record(owner: UserAccount) -> CalendarEventModel:
    return CalendarEventModel(
        id=uuid4(),
        user_id=owner.id,
        title="Synthetic meeting",
        description=None,
        event_date=date(2099, 10, 12),
        event_time=None,
        completed=False,
        cancelled=False,
        confirmation_email_sent=False,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def setup_service():
    owner = user()
    event = record(owner)
    repository, mailer, commit = Mock(), Mock(), Mock()
    repository.create.return_value = event
    repository.get_owned.side_effect = lambda user_id, event_id: (
        event if user_id == owner.id and event_id == event.id else None
    )

    def complete(user_id, event_id):
        if user_id != owner.id or event_id != event.id or event.completed:
            return None
        event.completed = True
        return event

    repository.complete_if_pending.side_effect = complete
    repository.mark_email_sent.side_effect = lambda item: setattr(
        item, "confirmation_email_sent", True
    )
    service = EventService(
        repository,
        Settings(_env_file=None),
        mailer,
        commit,
    )
    return service, owner, event, repository, mailer, commit


def test_creation_saves_but_never_sends_email():
    service, owner, event, repository, mailer, commit = setup_service()
    assert service.create(
        owner,
        title=event.title,
        description=None,
        event_date=event.event_date,
        event_time=None,
    ) == (event, False)
    repository.create.assert_called_once()
    assert repository.create.call_args.kwargs["user_id"] == owner.id
    commit.assert_called_once()
    mailer.send_confirmation.assert_not_called()


def test_confirmation_commits_before_mail_and_duplicate_does_not_send():
    service, owner, event, _, mailer, commit = setup_service()

    def send(**kwargs):
        commit.assert_called_once()
        assert event.completed
        assert kwargs["to_email"] == owner.email

    mailer.send_confirmation.side_effect = send
    assert service.confirm(owner, event.id) == (event, True)
    assert event.confirmation_email_sent
    assert service.confirm(owner, event.id) == (event, True)
    mailer.send_confirmation.assert_called_once()
    assert commit.call_count == 2


def test_mail_failure_keeps_completion_without_retry():
    service, owner, event, _, mailer, commit = setup_service()
    mailer.send_confirmation.side_effect = EventMailError("safe failure")
    assert service.confirm(owner, event.id) == (event, False)
    assert event.completed and not event.confirmation_email_sent
    assert service.confirm(owner, event.id) == (event, False)
    mailer.send_confirmation.assert_called_once()
    commit.assert_called_once()


def test_missing_event_mail_configuration_still_completes_without_mail():
    service, owner, event, repository, _, commit = setup_service()
    service = EventService(repository, Settings(_env_file=None), None, commit)
    assert service.confirm(owner, event.id) == (event, False)
    assert event.completed and not event.confirmation_email_sent
    commit.assert_called_once()


def test_commit_failure_prevents_mail():
    service, owner, event, _, mailer, commit = setup_service()
    commit.side_effect = SQLAlchemyError("synthetic private database detail")
    with pytest.raises(SQLAlchemyError):
        service.confirm(owner, event.id)
    mailer.send_confirmation.assert_not_called()


def test_other_owner_cannot_confirm_or_get_email():
    service, _, event, _, mailer, commit = setup_service()
    with pytest.raises(EventNotFoundError):
        service.confirm(user(), event.id)
    assert not event.completed
    commit.assert_not_called()
    mailer.send_confirmation.assert_not_called()


def test_past_date_rejected_before_any_write():
    service, owner, _, repository, mailer, commit = setup_service()
    with pytest.raises(EventValidationError):
        service.create(
            owner, title="Past", description=None, event_date=date(2000, 1, 1), event_time=None
        )
    repository.create.assert_not_called()
    commit.assert_not_called()
    mailer.send_confirmation.assert_not_called()


@pytest.mark.parametrize(
    "change",
    [
        {"title": "   "},
        {"title": "bad\nsubject"},
        {"description": "x" * 2001},
        {"event_time": "08:20:01"},
        {"event_time": "08:20+05:30"},
        {"user_id": str(uuid4())},
        {"email": "someone@example.com"},
        {"completed": True},
    ],
)
def test_schema_rejects_invalid_or_client_owned_values(change):
    with pytest.raises(ValidationError):
        CreateEventRequest.model_validate(
            {"title": "Meeting", "event_date": "2099-10-12", **change}
        )


def test_optional_description_and_time():
    payload = CreateEventRequest(
        title=" Meeting ", description="   ", event_date=date(2099, 10, 12)
    )
    assert payload.title == "Meeting" and payload.description is None and payload.event_time is None
    assert CreateEventRequest(
        title="Timed", event_date=date(2099, 10, 12), event_time=time(8, 20)
    ).event_time == time(8, 20)


def test_calendar_timezone_only_changes_calendar_zone():
    settings = Settings(_env_file=None, calendar_timezone="Asia/Colombo")
    instant = datetime(2026, 10, 2, 20, 0, tzinfo=UTC)
    assert instant.astimezone(settings.calendar_zone).date() == date(2026, 10, 3)
    assert instant.date() == date(2026, 10, 2)
    assert Settings(_env_file=None).calendar_timezone == "UTC"


@pytest.mark.parametrize(
    "overrides",
    [
        {"calendar_timezone": "invalid/zone"},
        {"event_smtp_port": 0},
        {"event_smtp_port": 65536},
        {"event_smtp_host": "   "},
    ],
)
def test_invalid_event_configuration_fails_validation(overrides):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **overrides)


def test_cancel_is_durable_without_email_and_blocks_confirmation():
    service, owner, event, repository, mailer, commit = setup_service()
    event.cancelled = True
    repository.cancel_owned.return_value = event
    assert service.cancel(owner, event.id) is event
    commit.assert_called_once()
    repository.complete_if_pending.return_value = None
    repository.complete_if_pending.side_effect = None
    from app.services.events import EventConflictError

    with pytest.raises(EventConflictError):
        service.confirm(owner, event.id)
    mailer.send_confirmation.assert_not_called()


def test_delete_requires_ownership_and_commit_without_email():
    service, owner, event, repository, mailer, commit = setup_service()
    repository.delete_owned.return_value = False
    with pytest.raises(EventNotFoundError):
        service.delete(owner, event.id)
    commit.assert_not_called()
    repository.delete_owned.return_value = True
    service.delete(owner, event.id)
    repository.delete_owned.assert_called_with(owner.id, event.id)
    commit.assert_called_once()
    mailer.send_confirmation.assert_not_called()


@pytest.mark.parametrize("send_email", [False, True])
def test_creation_email_opt_in_commits_before_smtp(send_email):
    service, owner, event, repository, mailer, commit = setup_service()

    def deliver(**kwargs):
        commit.assert_called_once()
        assert kwargs["to_email"] == owner.email
        assert kwargs["event"] is event

    mailer.send_confirmation.side_effect = deliver
    assert service.create(
        owner,
        title=event.title,
        description=event.description,
        event_date=event.event_date,
        event_time=None,
        send_email=send_email,
    ) == (event, send_email)
    assert "send_email" not in repository.create.call_args.kwargs
    assert mailer.send_confirmation.call_count == int(send_email)
    assert not event.completed and not event.confirmation_email_sent


def test_failed_creation_email_preserves_saved_event():
    service, owner, event, _, mailer, commit = setup_service()
    mailer.send_confirmation.side_effect = EventMailError("safe failure")
    assert service.create(
        owner,
        title=event.title,
        description=None,
        event_date=event.event_date,
        event_time=None,
        send_email=True,
    ) == (event, False)
    commit.assert_called_once()
    assert not event.completed


def test_creation_commit_failure_prevents_email():
    service, owner, event, _, mailer, commit = setup_service()
    commit.side_effect = SQLAlchemyError("synthetic failure")
    with pytest.raises(SQLAlchemyError):
        service.create(
            owner,
            title=event.title,
            description=None,
            event_date=event.event_date,
            event_time=None,
            send_email=True,
        )
    mailer.send_confirmation.assert_not_called()
