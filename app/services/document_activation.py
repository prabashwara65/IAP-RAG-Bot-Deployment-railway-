"""Lifecycle-aware activation for uploaded documents."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.documents import (
    ApprovalDecisionType,
    DocumentVersionRecord,
    DocumentVersionStatus,
    EmbeddingSetStatus,
)
from app.models.documents import (
    DocumentModel,
    DocumentVersionModel,
    EmbeddingSetModel,
)
from app.repositories.postgres.documents import (
    DocumentNotFoundError,
    InvalidLifecycleTransitionError,
    PostgresDocumentRepository,
)
from app.services.hr_publication import record_hr_approval

AUTO_ACTIVATION_ACTOR = "system:auto-activation"


def activate_document(
    session: Session,
    document_key: str,
    *,
    version_id: UUID | None = None,
) -> DocumentVersionRecord:
    """Approve and activate the latest version for one document key atomically."""
    document = session.scalar(
        select(DocumentModel)
        .where(DocumentModel.document_key == document_key)
        .with_for_update()
    )
    if document is None:
        raise DocumentNotFoundError(f"Document {document_key!r} does not exist")

    version_statement = select(DocumentVersionModel).where(
        DocumentVersionModel.document_id == document.id,
        DocumentVersionModel.status.in_(
            (
                DocumentVersionStatus.CANDIDATE.value,
                DocumentVersionStatus.APPROVED.value,
                DocumentVersionStatus.ACTIVE.value,
            ),
        ),
    )
    if version_id is not None:
        version_statement = version_statement.where(DocumentVersionModel.id == version_id)
    version = session.scalar(
        version_statement.order_by(
            DocumentVersionModel.created_at.desc(), DocumentVersionModel.id.desc()
        )
        .limit(1)
        .with_for_update()
    )
    if version is None:
        raise DocumentNotFoundError(f"Document {document_key!r} has no versions")

    embedding_sets = session.scalars(
        select(EmbeddingSetModel)
        .where(EmbeddingSetModel.document_version_id == version.id)
        .with_for_update()
    ).all()
    if not embedding_sets:
        raise InvalidLifecycleTransitionError(
            "A document version needs an embedding set before activation"
        )
    if any(
        embedding_set.status
        not in {EmbeddingSetStatus.CANDIDATE.value, EmbeddingSetStatus.ACTIVE.value}
        for embedding_set in embedding_sets
    ):
        raise InvalidLifecycleTransitionError(
            "Only candidate or active embedding sets can be activated"
        )

    repository = PostgresDocumentRepository(session)
    if version.status == DocumentVersionStatus.CANDIDATE.value:
        record_hr_approval(
            repository,
            version_id=version.id,
            reviewer_actor_ref=AUTO_ACTIVATION_ACTOR,
            decision=ApprovalDecisionType.APPROVED,
            correlation_id=f"auto-activation:{document_key}"[:128],
            reason_notes="Automatically approved for the demonstration upload workflow.",
        )
    elif version.status != DocumentVersionStatus.APPROVED.value and (
        version.status != DocumentVersionStatus.ACTIVE.value
    ):
        raise InvalidLifecycleTransitionError(
            f"Document version in {version.status!r} state cannot be activated"
        )

    if version.status != DocumentVersionStatus.ACTIVE.value:
        activated_version = repository.activate_approved_version(version.id)
    else:
        if version.approved_at is None:
            raise InvalidLifecycleTransitionError(
                "An active document version must have an approval timestamp"
            )
        if version.activated_at is None:
            version.activated_at = datetime.now(UTC)
        activated_version = repository.get_version(version.id)
        if activated_version is None:
            raise DocumentNotFoundError("Document version does not exist")

    document.document_type = "CV"
    for embedding_set in embedding_sets:
        embedding_set.status = EmbeddingSetStatus.ACTIVE.value
    session.flush()
    return activated_version


def activate_all_documents(session: Session) -> tuple[DocumentVersionRecord, ...]:
    """Activate eligible documents in one transaction, in stable key order."""
    document_keys = session.scalars(
        select(DocumentModel.document_key)
        .join(
            DocumentVersionModel,
            DocumentVersionModel.document_id == DocumentModel.id,
        )
        .where(
            DocumentVersionModel.status.in_(
                (
                    DocumentVersionStatus.CANDIDATE.value,
                    DocumentVersionStatus.APPROVED.value,
                    DocumentVersionStatus.ACTIVE.value,
                )
            )
        )
        .distinct()
        .order_by(DocumentModel.document_key)
    ).all()
    return tuple(activate_document(session, key) for key in document_keys)