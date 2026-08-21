"""Document lifecycle values and repository-facing records."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class DocumentVersionStatus(StrEnum):
    """Persisted foundation states; workflow transitions arrive in later phases."""

    CANDIDATE = "candidate"
    APPROVED = "approved"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"
    FAILED = "failed"


class EmbeddingSetStatus(StrEnum):
    """Embedding set lifecycle states; only active sets are searchable."""

    CANDIDATE = "candidate"
    ACTIVE = "active"
    ARCHIVED = "archived"
    FAILED = "failed"


class ApprovalDecisionType(StrEnum):
    """Human decision values recorded independently from future orchestration."""

    APPROVED = "approved"
    REJECTED = "rejected"
    CHANGES_REQUESTED = "changes_requested"


@dataclass(frozen=True, slots=True)
class DocumentRecord:
    id: UUID
    tenant_id: str
    document_key: str
    title: str


@dataclass(frozen=True, slots=True)
class DocumentVersionRecord:
    id: UUID
    document_id: UUID
    version_label: str
    status: DocumentVersionStatus
    content_hash: str
