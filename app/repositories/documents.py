"""Document persistence contract independent from PostgreSQL details."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.domain.documents import (
    ApprovalDecisionType,
    DocumentRecord,
    DocumentVersionRecord,
)


class DocumentRepository(Protocol):
    def create_document(
        self,
        *,
        tenant_id: str,
        document_key: str,
        title: str,
        document_type: str = "Other",
    ) -> DocumentRecord: ...

    def get_document(self, document_id: UUID) -> DocumentRecord | None: ...

    def create_candidate_version(
        self,
        *,
        document_id: UUID,
        version_label: str,
        content_hash: str,
        source_path: str | None = None,
    ) -> DocumentVersionRecord: ...

    def get_version(self, version_id: UUID) -> DocumentVersionRecord | None: ...

    def list_active_versions(self, document_id: UUID) -> list[DocumentVersionRecord]: ...

    def record_approval(
        self,
        *,
        version_id: UUID,
        reviewer_actor_ref: str,
        decision: ApprovalDecisionType,
        correlation_id: str,
        reason_notes: str | None = None,
    ) -> DocumentVersionRecord: ...

    def activate_approved_version(self, version_id: UUID) -> DocumentVersionRecord: ...
