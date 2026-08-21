"""Repository, constraint, transaction, and pgvector integration tests."""

from uuid import uuid4

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import create_session_factory, session_scope
from app.domain.documents import ApprovalDecisionType, DocumentVersionStatus
from app.models.documents import (
    ChunkModel,
    DocumentModel,
    DocumentVersionModel,
    EmbeddingModel,
    EmbeddingSetModel,
)
from app.repositories.postgres.documents import (
    InvalidLifecycleTransitionError,
    PostgresDocumentRepository,
)
from app.repositories.postgres.embeddings import (
    EmbeddingCompatibilityError,
    PostgresEmbeddingRepository,
)


def test_repository_create_read_and_candidate_isolation(
    migrated_engine: Engine,
) -> None:
    factory = create_session_factory(migrated_engine)
    with session_scope(factory) as session:
        repository = PostgresDocumentRepository(session)
        document = repository.create_document(
            tenant_id="tenant-test",
            document_key="DOC-001",
            title="Foundation test document",
        )
        candidate = repository.create_candidate_version(
            document_id=document.id,
            version_label="1.0",
            content_hash="hash-version-1",
        )
        assert repository.get_document(document.id) == document
        assert repository.get_version(candidate.id) == candidate
        assert repository.list_active_versions(document.id) == []
        with pytest.raises(InvalidLifecycleTransitionError):
            repository.activate_approved_version(candidate.id)

        approved = repository.record_approval(
            version_id=candidate.id,
            reviewer_actor_ref="reviewer-test",
            decision=ApprovalDecisionType.APPROVED,
            correlation_id="correlation-test-1",
        )
        assert approved.status is DocumentVersionStatus.APPROVED
        active = repository.activate_approved_version(candidate.id)
        assert active.status is DocumentVersionStatus.ACTIVE
        assert repository.list_active_versions(document.id) == [active]


def test_activating_new_version_supersedes_previous_version(
    migrated_engine: Engine,
) -> None:
    factory = create_session_factory(migrated_engine)
    with session_scope(factory) as session:
        repository = PostgresDocumentRepository(session)
        document = repository.create_document(
            tenant_id="tenant-test", document_key="DOC-002", title="Version test"
        )
        first = repository.create_candidate_version(
            document_id=document.id, version_label="1.0", content_hash="hash-a"
        )
        repository.record_approval(
            version_id=first.id,
            reviewer_actor_ref="reviewer-test",
            decision=ApprovalDecisionType.APPROVED,
            correlation_id="correlation-test-2",
        )
        repository.activate_approved_version(first.id)

        second = repository.create_candidate_version(
            document_id=document.id, version_label="2.0", content_hash="hash-b"
        )
        repository.record_approval(
            version_id=second.id,
            reviewer_actor_ref="reviewer-test",
            decision=ApprovalDecisionType.APPROVED,
            correlation_id="correlation-test-3",
        )
        repository.activate_approved_version(second.id)

        refreshed_first = repository.get_version(first.id)
        assert refreshed_first is not None
        assert refreshed_first.status is DocumentVersionStatus.SUPERSEDED
        assert repository.list_active_versions(document.id) == [
            repository.get_version(second.id)
        ]


def test_foreign_key_and_uniqueness_constraints(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        first = DocumentModel(
            tenant_id="tenant-test", document_key="DOC-003", title="First"
        )
        duplicate = DocumentModel(
            tenant_id="tenant-test", document_key="DOC-003", title="Duplicate"
        )
        session.add_all([first, duplicate])
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        session.add(
            DocumentVersionModel(
                document_id=uuid4(),
                version_label="1.0",
                status="candidate",
                content_hash="orphan-hash",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_session_scope_rolls_back_failed_transaction(migrated_engine: Engine) -> None:
    factory = create_session_factory(migrated_engine)
    with pytest.raises(RuntimeError, match="force rollback"):
        with session_scope(factory) as session:
            session.add(
                DocumentModel(
                    tenant_id="tenant-test",
                    document_key="DOC-ROLLBACK",
                    title="Rollback",
                )
            )
            session.flush()
            raise RuntimeError("force rollback")

    with Session(migrated_engine) as session:
        count = len(
            session.scalars(
                select(DocumentModel).where(
                    DocumentModel.document_key == "DOC-ROLLBACK"
                )
            ).all()
        )
    assert count == 0


def test_embedding_dimension_and_document_version_compatibility(
    migrated_engine: Engine,
) -> None:
    factory = create_session_factory(migrated_engine)
    with session_scope(factory) as session:
        document_repository = PostgresDocumentRepository(session)
        document = document_repository.create_document(
            tenant_id="tenant-test", document_key="DOC-004", title="Vector test"
        )
        version = document_repository.create_candidate_version(
            document_id=document.id, version_label="1.0", content_hash="vector-hash"
        )
        chunk = ChunkModel(
            document_version_id=version.id,
            chunk_index=0,
            heading_path="Section",
            content_text="Bounded integration-test text.",
            content_hash="chunk-hash",
        )
        embedding_set = EmbeddingSetModel(
            document_version_id=version.id,
            model_name="deterministic-test-model",
            model_version="1",
            dimension=3,
            status="candidate",
        )
        session.add_all([chunk, embedding_set])
        session.flush()

        embedding_repository = PostgresEmbeddingRepository(session)
        with pytest.raises(EmbeddingCompatibilityError, match="dimension"):
            embedding_repository.add_embedding(
                chunk_id=chunk.id,
                embedding_set_id=embedding_set.id,
                values=[0.1, 0.2],
            )
        embedding_id = embedding_repository.add_embedding(
            chunk_id=chunk.id,
            embedding_set_id=embedding_set.id,
            values=[0.1, 0.2, 0.3],
        )
        stored = session.get(EmbeddingModel, embedding_id)
        assert stored is not None
        assert list(stored.embedding) == pytest.approx([0.1, 0.2, 0.3])
