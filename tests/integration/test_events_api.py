"""Authenticated API checks with in-memory accounts/events and fake SMTP."""

from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import SQLAlchemyError

from app.api.dependencies import get_account_repository, get_event_service, get_session
from app.core.config import Settings
from app.main import create_app
from app.models.events import CalendarEventModel
from app.services.auth import hash_secret
from app.services.event_mail import EventMailError
from app.services.events import EventService
from tests.fakes.user_accounts import MemoryUserAccountRepository


def setup_api():
    settings = Settings(_env_file=None, app_env="test")
    app = create_app(settings)
    accounts = MemoryUserAccountRepository()
    users = {}
    for name in ("ada", "grace"):
        owner = accounts.create_user(
            email=f"{name}@example.com",
            display_name=name,
            theme="system",
            password_hash="synthetic",
        )
        accounts.create_session(
            user_id=owner.id,
            token_hash=hash_secret(name),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        users[name] = owner
    stored = {}
    repository, mailer, session = Mock(), Mock(), Mock()

    def create(**fields):
        event = CalendarEventModel(
            id=uuid4(),
            **fields,
            completed=False,
            cancelled=False,
            confirmation_email_sent=False,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        stored[event.id] = event
        return event

    def get_owned(user_id, event_id):
        event = stored.get(event_id)
        return event if event is not None and event.user_id == user_id else None

    def complete(user_id, event_id):
        event = get_owned(user_id, event_id)
        if event is None or event.completed or event.cancelled:
            return None
        event.completed = True
        return event

    repository.create.side_effect = create
    repository.get_owned.side_effect = get_owned

    def cancel(user_id, event_id):
        event = get_owned(user_id, event_id)
        if event is None or event.cancelled:
            return None
        event.cancelled = True
        return event

    def delete(user_id, event_id):
        event = get_owned(user_id, event_id)
        if event is None:
            return False
        del stored[event_id]
        return True

    repository.cancel_owned.side_effect = cancel
    repository.delete_owned.side_effect = delete
    repository.complete_if_pending.side_effect = complete
    repository.list_for_user.side_effect = lambda user_id: [
        event for event in stored.values() if event.user_id == user_id
    ]
    repository.mark_email_sent.side_effect = lambda event: setattr(
        event, "confirmation_email_sent", True
    )
    service = EventService(repository, settings, mailer, session.commit)
    app.dependency_overrides[get_account_repository] = lambda: accounts
    app.dependency_overrides[get_event_service] = lambda: service
    app.dependency_overrides[get_session] = lambda: session
    return app, repository, mailer, session, users


async def test_create_list_confirm_ownership_and_no_duplicate_mail():
    app, _, mailer, session, users = setup_api()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        ada = {"Authorization": "Bearer ada"}
        grace = {"Authorization": "Bearer grace"}
        response = await client.post(
            "/api/v1/events",
            headers=ada,
            json={
                "title": " Team Meeting ",
                "description": "Discussion",
                "event_date": "2099-10-12",
                "event_time": "10:00",
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert body["title"] == "Team Meeting" and not body["completed"]
        assert not body["confirmation_email_sent"] and "user_id" not in body
        mailer.send_confirmation.assert_not_called()
        assert len((await client.get("/api/v1/events", headers=ada)).json()) == 1
        assert (await client.get("/api/v1/events", headers=grace)).json() == []
        path = f"/api/v1/events/{body['id']}/confirm"
        assert (await client.patch(path, headers=grace)).status_code == 404
        assert (
            await client.patch(f"/api/v1/events/{uuid4()}/confirm", headers=ada)
        ).status_code == 404

        def deliver(**kwargs):
            assert session.commit.call_count == 2  # create, then completion
            assert kwargs["to_email"] == users["ada"].email

        mailer.send_confirmation.side_effect = deliver
        confirmed = await client.patch(path, headers=ada)
        assert confirmed.status_code == 200
        assert confirmed.json()["completed"] and confirmed.json()["email_sent"]
        duplicate = await client.patch(path, headers=ada)
        assert duplicate.json()["completed"]
        mailer.send_confirmation.assert_called_once()
        assert session.commit.call_count == 3
        assert (await client.get("/api/v1/events/settings", headers=ada)).json() == {
            "timezone": "UTC"
        }


async def test_authentication_and_client_identity_fields_rejected():
    app, _, mailer, _, _ = setup_api()
    payload = {"title": "Event", "event_date": "2099-10-12"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/api/v1/events")).status_code == 401
        assert (await client.post("/api/v1/events", json=payload)).status_code == 401
        assert (await client.patch(f"/api/v1/events/{uuid4()}/confirm")).status_code == 401
        for change in [
            {"email": "grace@example.com"},
            {"user_id": str(uuid4())},
            {"completed": True},
            {"title": "   "},
            {"event_date": "2000-01-01"},
        ]:
            response = await client.post(
                "/api/v1/events",
                headers={"Authorization": "Bearer ada"},
                json={**payload, **change},
            )
            assert response.status_code == 422
    mailer.send_confirmation.assert_not_called()


async def test_failed_email_keeps_checked_state_and_duplicate_does_not_retry():
    app, _, mailer, _, _ = setup_api()
    mailer.send_confirmation.side_effect = EventMailError("synthetic failure")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = {"Authorization": "Bearer ada"}
        created = await client.post(
            "/api/v1/events", headers=headers, json={"title": "Event", "event_date": "2099-10-12"}
        )
        path = f"/api/v1/events/{created.json()['id']}/confirm"
        result = await client.patch(path, headers=headers)
        assert result.status_code == 200
        assert result.json()["completed"] and not result.json()["email_sent"]
        listed = (await client.get("/api/v1/events", headers=headers)).json()
        assert listed[0]["completed"] and not listed[0]["confirmation_email_sent"]
        await client.patch(path, headers=headers)
    mailer.send_confirmation.assert_called_once()


async def test_database_errors_are_curated_and_commit_failure_sends_nothing():
    app, repository, mailer, session, _ = setup_api()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = {"Authorization": "Bearer ada"}
        repository.list_for_user.side_effect = SQLAlchemyError("synthetic private schema")
        response = await client.get("/api/v1/events", headers=headers)
        assert response.status_code == 503 and "private" not in response.text
        repository.list_for_user.side_effect = lambda _: []
        created = await client.post(
            "/api/v1/events", headers=headers, json={"title": "Event", "event_date": "2099-10-12"}
        )
        session.commit.side_effect = SQLAlchemyError("synthetic private commit")
        response = await client.patch(
            f"/api/v1/events/{created.json()['id']}/confirm", headers=headers
        )
        assert response.status_code == 503 and "private" not in response.text
    mailer.send_confirmation.assert_not_called()


async def test_cancel_and_delete_are_owner_scoped_and_send_no_mail():
    app, _, mailer, _, _ = setup_api()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        ada = {"Authorization": "Bearer ada"}
        grace = {"Authorization": "Bearer grace"}
        result = await client.post(
            "/api/v1/events",
            headers=ada,
            json={"title": "Cancel me", "event_date": "2099-10-12"},
        )
        path = f"/api/v1/events/{result.json()['id']}"
        assert (await client.patch(path + "/cancel")).status_code == 401
        assert (await client.delete(path)).status_code == 401
        assert (await client.patch(path + "/cancel", headers=grace)).status_code == 404
        assert (await client.delete(path, headers=grace)).status_code == 404
        assert len((await client.get("/api/v1/events", headers=ada)).json()) == 1
        cancelled = await client.patch(path + "/cancel", headers=ada)
        assert cancelled.status_code == 200 and cancelled.json()["cancelled"]
        assert (await client.patch(path + "/cancel", headers=ada)).json()["cancelled"]
        assert (await client.patch(path + "/confirm", headers=ada)).status_code == 409
        assert (await client.get("/api/v1/events", headers=ada)).json()[0]["cancelled"]
        deleted = await client.delete(path, headers=ada)
        assert deleted.status_code == 204 and not deleted.content
        assert (await client.get("/api/v1/events", headers=ada)).json() == []
        assert (await client.delete(path, headers=ada)).status_code == 404
    mailer.send_confirmation.assert_not_called()


async def test_cancel_delete_errors_are_curated():
    app, repository, mailer, _, _ = setup_api()
    repository.cancel_owned.side_effect = SQLAlchemyError("private schema")
    repository.delete_owned.side_effect = SQLAlchemyError("private schema")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        path = f"/api/v1/events/{uuid4()}"
        for response in [
            await client.patch(path + "/cancel", headers={"Authorization": "Bearer ada"}),
            await client.delete(path, headers={"Authorization": "Bearer ada"}),
        ]:
            assert response.status_code == 503 and "private" not in response.text
    mailer.send_confirmation.assert_not_called()


async def test_creation_email_opt_in_uses_authenticated_recipient_after_commit():
    app, _, mailer, session, users = setup_api()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = {"Authorization": "Bearer ada"}
        payload = {
            "title": "Scheduled meeting",
            "description": "Full details",
            "event_date": "2099-10-12",
        }
        unchecked = await client.post(
            "/api/v1/events", headers=headers, json={**payload, "send_email": False}
        )
        assert unchecked.status_code == 201 and not unchecked.json()["email_sent"]
        mailer.send_confirmation.assert_not_called()

        def deliver(**kwargs):
            assert session.commit.call_count == 2
            assert kwargs["to_email"] == users["ada"].email
            assert kwargs["event"].description == "Full details"

        mailer.send_confirmation.side_effect = deliver
        checked = await client.post(
            "/api/v1/events", headers=headers, json={**payload, "send_email": True}
        )
        assert checked.status_code == 201 and checked.json()["email_sent"]
        assert not checked.json()["completed"]
        mailer.send_confirmation.assert_called_once()
        assert len((await client.get("/api/v1/events", headers=headers)).json()) == 2

        mailer.send_confirmation.side_effect = EventMailError("synthetic delivery failure")
        failed = await client.post(
            "/api/v1/events", headers=headers, json={**payload, "send_email": True}
        )
        assert failed.status_code == 201 and not failed.json()["email_sent"]
        assert len((await client.get("/api/v1/events", headers=headers)).json()) == 3
        for value in ["false", 1, None]:
            result = await client.post(
                "/api/v1/events", headers=headers, json={**payload, "send_email": value}
            )
            assert result.status_code == 422
