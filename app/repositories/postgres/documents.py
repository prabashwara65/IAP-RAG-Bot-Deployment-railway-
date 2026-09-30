"""SQLAlchemy implementation of the document repository contract."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.domain.documents import (
    ApprovalDecisionType,
    DocumentRecord,
    DocumentVersionRecord,
    DocumentVersionStatus,
)
from app.models.documents import (
    ApprovalDecisionModel,
    DocumentModel,
    DocumentVersionModel,
)


class DocumentNotFoundError(LookupError):
    """Raised when a requested document or version does not exist."""


class InvalidLifecycleTransitionError(ValueError):
    """Raised when a repository operation would bypass lifecycle controls."""


class PostgresDocumentRepository:
    """Persist documents while keeping lifecycle rules out of ORM mappings."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_document(
        self,
        *,
        tenant_id: str,
        document_key: str,
        title: str,
        document_type: str = "Other",
    ) -> DocumentRecord:
        model = DocumentModel(
            tenant_id=tenant_id,
            document_key=document_key,
            title=title,
            document_type=document_type,
        )
        self._session.add(model)
        self._session.flush()
        return self._to_document_record(model)

    def get_document(self, document_id: UUID) -> DocumentRecord | None:
        model = self._session.get(DocumentModel, document_id)
        return None if model is None else self._to_document_record(model)

    def create_candidate_version(
        self,
        *,
        document_id: UUID,
        version_label: str,
        content_hash: str,
        source_path: str | None = None,
    ) -> DocumentVersionRecord:
        if self._session.get(DocumentModel, document_id) is None:
            raise DocumentNotFoundError("Document does not exist")
        model = DocumentVersionModel(
            document_id=document_id,
            version_label=version_label,
            status=DocumentVersionStatus.CANDIDATE.value,
            content_hash=content_hash,
            source_path=source_path,
        )
        self._session.add(model)
        self._session.flush()
        return self._to_version_record(model)

    def get_version(self, version_id: UUID) -> DocumentVersionRecord | None:
        model = self._session.get(DocumentVersionModel, version_id)
        return None if model is None else self._to_version_record(model)

    def list_active_versions(self, document_id: UUID) -> list[DocumentVersionRecord]:
        statement = (
            select(DocumentVersionModel)
            .where(
                DocumentVersionModel.document_id == document_id,
                DocumentVersionModel.status == DocumentVersionStatus.ACTIVE.value,
            )
            .order_by(DocumentVersionModel.activated_at, DocumentVersionModel.id)
        )
        return [
            self._to_version_record(model)
            for model in self._session.scalars(statement).all()
        ]

    def record_approval(
        self,
        *,
        version_id: UUID,
        reviewer_actor_ref: str,
        decision: ApprovalDecisionType,
        correlation_id: str,
        reason_notes: str | None = None,
    ) -> DocumentVersionRecord:
        model = self._session.get(DocumentVersionModel, version_id)
        if model is None:
            raise DocumentNotFoundError("Document version does not exist")
        if model.status != DocumentVersionStatus.CANDIDATE.value:
            raise InvalidLifecycleTransitionError(
                "Only candidate versions can receive an approval decision"
            )

        now = datetime.now(UTC)
        self._session.add(
            ApprovalDecisionModel(
                document_version_id=version_id,
                reviewer_actor_ref=reviewer_actor_ref,
                decision=decision.value,
                reason_notes=reason_notes,
                correlation_id=correlation_id,
                decided_at=now,
            )
        )
        if decision is ApprovalDecisionType.APPROVED:
            model.status = DocumentVersionStatus.APPROVED.value
            model.approved_at = now
        else:
            model.status = DocumentVersionStatus.FAILED.value
        self._session.flush()
        return self._to_version_record(model)

    def activate_approved_version(self, version_id: UUID) -> DocumentVersionRecord:
        statement = (
            select(DocumentVersionModel)
            .where(DocumentVersionModel.id == version_id)
            .with_for_update()
        )
        model = self._session.scalar(statement)
        if model is None:
            raise DocumentNotFoundError("Document version does not exist")
        if (
            model.status != DocumentVersionStatus.APPROVED.value
            or model.approved_at is None
        ):
            raise InvalidLifecycleTransitionError(
                "Only approved document versions can become active"
            )

        self._session.execute(
            update(DocumentVersionModel)
            .where(
                DocumentVersionModel.document_id == model.document_id,
                DocumentVersionModel.id != model.id,
                DocumentVersionModel.status == DocumentVersionStatus.ACTIVE.value,
            )
            .values(status=DocumentVersionStatus.SUPERSEDED.value)
        )
        model.status = DocumentVersionStatus.ACTIVE.value
        model.activated_at = datetime.now(UTC)
        self._session.flush()
        return self._to_version_record(model)

    @staticmethod
    def _to_document_record(model: DocumentModel) -> DocumentRecord:
        return DocumentRecord(
            id=model.id,
            tenant_id=model.tenant_id,
            document_key=model.document_key,
            title=model.title,
        )

    @staticmethod
    def _to_version_record(model: DocumentVersionModel) -> DocumentVersionRecord:
        return DocumentVersionRecord(
            id=model.id,
            document_id=model.document_id,
            version_label=model.version_label,
            status=DocumentVersionStatus(model.status),
            content_hash=model.content_hash,
        )
