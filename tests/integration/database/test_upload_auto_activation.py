"""PostgreSQL integration for automatic upload activation and grounded retrieval."""

from datetime import UTC, datetime
from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from sqlalchemy import Engine, select

from app.api.dependencies import get_current_user, get_embedding_provider, get_llm_provider
from app.core.config import get_settings
from app.core.database import create_session_factory, session_scope
from app.domain.accounts import UserAccount
from app.domain.documents import DocumentVersionStatus, EmbeddingSetStatus
from app.main import create_app
from app.models.documents import DocumentModel, DocumentVersionModel, EmbeddingSetModel
from app.providers.deterministic_embeddings import DeterministicEmbeddingProvider
from app.providers.deterministic_llm import DeterministicLLMProvider

CONTENT = "The annual leave entitlement is twenty-one working days."


async def test_uploaded_document_is_active_and_retrievable(
    migrated_engine: Engine,
) -> None:
    embedding_provider = DeterministicEmbeddingProvider(dimension=8)
    application = create_app(
        get_settings().model_copy(
            update={"app_env": "test", "auto_activate_uploads": True}
        )
    )
    application.dependency_overrides[get_current_user] = lambda: UserAccount(
        id=uuid4(),
        email="upload-test@example.com",
        display_name="Upload Test",
        theme="system",
        avatar_path=None,
        created_at=datetime.now(UTC),
    )
    application.dependency_overrides[get_embedding_provider] = lambda: embedding_provider
    application.dependency_overrides[get_llm_provider] = DeterministicLLMProvider

    try:
        transport = ASGITransport(app=application)
        async with AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            upload_response = await client.post(
                "/api/v1/documents/ingest",
                data={"document_type": "CV"},
                files={"file": ("leave-policy.txt", CONTENT, "text/plain")},
            )
            assert upload_response.status_code == 200
            upload_body = upload_response.json()
            assert upload_body["version_status"] == DocumentVersionStatus.ACTIVE.value

            document_key = upload_body["document_key"]
            with session_scope(create_session_factory(migrated_engine)) as session:
                document = session.scalar(
                    select(DocumentModel).where(
                        DocumentModel.document_key == document_key
                    )
                )
                assert document is not None
                version = session.scalar(
                    select(DocumentVersionModel).where(
                        DocumentVersionModel.document_id == document.id
                    )
                )
                assert version is not None
                assert version.status == DocumentVersionStatus.ACTIVE.value
                assert version.approved_at is not None
                assert version.activated_at is not None
                embedding_set = session.scalar(
                    select(EmbeddingSetModel).where(
                        EmbeddingSetModel.document_version_id == version.id
                    )
                )
                assert embedding_set is not None
                assert embedding_set.status == EmbeddingSetStatus.ACTIVE.value

            ask_response = await client.post(
                "/api/v1/hr/ask",
                json={"question": CONTENT, "tenant_id": "tenant-synthetic"},
            )

        assert ask_response.status_code == 200
        ask_body = ask_response.json()
        assert ask_body["insufficient_evidence"] is False
        assert any(
            citation["document_key"] == document_key
            for citation in ask_body["citations"]
        )
    finally:
        application.state.database_engine.dispose()