"""Integration tests for the authenticated document ingestion endpoint."""

from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
import pytest
from datetime import UTC, datetime
from app.domain.accounts import UserAccount
from app.domain.roles import Role
from httpx import ASGITransport, AsyncClient, Response

from app.api.dependencies import get_current_user, get_embedding_provider, get_session
from app.core.config import Settings
from app.main import create_app
from app.domain.documents import DocumentVersionStatus
from app.services.document_ingestion import PersistedIngestedDocument

UPLOAD_PATH = "/api/v1/documents/ingest"


def _application(*, max_bytes: int = 2048, role: Role = Role.ADMIN) -> FastAPI:
    application = create_app(
        Settings(app_env="test", document_max_bytes=max_bytes)
    )
    application.dependency_overrides[get_current_user] = lambda: UserAccount(
        id=uuid4(), email="account@example.com", display_name="Account",
        theme="light", avatar_path=None, created_at=datetime.now(UTC), role=role,
    )
    application.dependency_overrides[get_embedding_provider] = lambda: object()

    def session_dependency():
        yield object()

    application.dependency_overrides[get_session] = session_dependency
    return application


async def _upload(
    application: FastAPI,
    filename: str,
    content: bytes,
    document_type: str = "Other",
) -> Response:
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.post(
            UPLOAD_PATH,
            data={"document_type": document_type},
            files={"file": (filename, content, "application/octet-stream")},
        )


async def test_upload_returns_persisted_chunk_preview(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.routes.documents.persist_ingested_document",
        lambda *args, **kwargs: PersistedIngestedDocument(
            document_key="UPLOAD-TEST",
            document_type="CV",
            version_id=uuid4(),
            version_status=DocumentVersionStatus.CANDIDATE,
            chunk_count=2,
        ),
    )
    response = await _upload(
        _application(), "guide.txt", b"First part.\n\nSecond part.", "CV"
    )

    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    assert body["filename"] == "guide.txt"
    assert body["document_key"] == "UPLOAD-TEST"
    assert body["document_type"] == "CV"
    assert body["version_status"] == "candidate"
    assert body["chunk_count"] == 2
    assert [chunk["content_text"] for chunk in body["chunks"]] == [
        "First part.",
        "Second part.",
    ]
    assert all(len(chunk["content_hash"]) == 64 for chunk in body["chunks"])


async def test_upload_rejects_unsupported_extension() -> None:
    response = await _upload(_application(), "guide.rtf", b"Some text")

    assert response.status_code == 415


async def test_upload_rejects_files_over_configured_limit() -> None:
    response = await _upload(_application(max_bytes=1024), "guide.txt", b"x" * 1025)

    assert response.status_code == 413

@pytest.mark.parametrize("role", [Role.USER, Role.HR, Role.EMPLOYEE, Role.STUDENT])
async def test_upload_denies_every_non_admin_before_processing(role, monkeypatch) -> None:
    def unexpected_processing(*args, **kwargs):
        raise AssertionError("An unauthorized upload must not be processed")
    monkeypatch.setattr("app.api.routes.documents.ingest_document", unexpected_processing)
    monkeypatch.setattr("app.api.routes.documents.persist_ingested_document", unexpected_processing)
    application = _application(role=role)
    application.dependency_overrides[get_embedding_provider] = unexpected_processing
    response = await _upload(application, "guide.txt", b"Some text")
    assert response.status_code == 403
    assert "Only administrators" in str(response.json())


async def test_upload_requires_sign_in() -> None:
    application = _application()
    def unauthenticated():
        raise HTTPException(401, "Sign in required.")
    application.dependency_overrides[get_current_user] = unauthenticated
    response = await _upload(application, "guide.txt", b"Some text")
    assert response.status_code == 401
