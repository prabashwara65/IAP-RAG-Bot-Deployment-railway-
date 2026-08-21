"""Deterministic cross-field validation for governed HR documents."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.schemas.hr_documents import (
    AccessLevel,
    ApprovalStatus,
    DataDeclaration,
    DataMode,
    Department,
    DocumentStatus,
    DocumentType,
    HRDocumentMetadata,
    Language,
    RagApprovalStatus,
    RedactionStatus,
)


class DocumentValidationErrorCode(StrEnum):
    DOCUMENT_TYPE_OTHER_REQUIRED = "document_type_other_required"
    DEPARTMENT_OTHER_REQUIRED = "department_other_required"
    LANGUAGE_OTHER_REQUIRED = "language_other_required"
    LAST_REVIEW_BEFORE_EFFECTIVE = "last_review_before_effective"
    NEXT_REVIEW_NOT_AFTER_REFERENCE = "next_review_not_after_reference"
    PERMITTED_ROLES_REQUIRED = "permitted_roles_required"
    ROLE_LISTS_OVERLAP = "role_lists_overlap"
    RAG_BLOCKED_BY_ACCESS_LEVEL = "rag_blocked_by_access_level"
    RAG_REQUIRES_DOCUMENT_APPROVAL = "rag_requires_document_approval"
    ACTIVE_REQUIRES_DOCUMENT_APPROVAL = "active_requires_document_approval"
    ACTIVE_REQUIRES_RAG_APPROVAL = "active_requires_rag_approval"
    ACTIVE_REQUIRES_APPROVER = "active_requires_approver"
    UNRESOLVED_DATA_BLOCKS_ACTIVE = "unresolved_data_blocks_active"
    UNRESOLVED_DATA_BLOCKS_RAG = "unresolved_data_blocks_rag"
    REDACTION_BLOCKS_ACTIVE = "redaction_blocks_active"
    REDACTION_BLOCKS_RAG = "redaction_blocks_rag"
    REDACTION_STATUS_REQUIRED = "redaction_status_required"
    SENSITIVE_DATA_REDACTION_NOT_REQUIRED = "sensitive_data_redaction_not_required"
    SYNTHETIC_REQUIRED = "synthetic_required"
    OFFICIAL_DOCUMENT_PROHIBITED = "official_document_prohibited"
    INVALID_DATA_MODE = "invalid_data_mode"


@dataclass(frozen=True, slots=True)
class DocumentValidationError:
    """One stable validation failure suitable for API error translation."""

    code: DocumentValidationErrorCode
    fields: tuple[str, ...]
    message: str


@dataclass(frozen=True, slots=True)
class DocumentValidationResult:
    """Ordered cross-field validation outcome."""

    errors: tuple[DocumentValidationError, ...]

    @property
    def is_valid(self) -> bool:
        return not self.errors


def validate_hr_document(document: HRDocumentMetadata) -> DocumentValidationResult:
    """Validate metadata relationships in a stable, side-effect-free rule order."""
    errors: list[DocumentValidationError] = []

    def add(
        code: DocumentValidationErrorCode,
        fields: tuple[str, ...],
        message: str,
    ) -> None:
        errors.append(DocumentValidationError(code=code, fields=fields, message=message))

    if document.document_type is DocumentType.OTHER and document.document_type_other is None:
        add(
            DocumentValidationErrorCode.DOCUMENT_TYPE_OTHER_REQUIRED,
            ("document_type", "document_type_other"),
            "document_type_other is required when document_type is Other.",
        )
    if document.department is Department.OTHER and document.department_other is None:
        add(
            DocumentValidationErrorCode.DEPARTMENT_OTHER_REQUIRED,
            ("department", "department_other"),
            "department_other is required when department is Other.",
        )
    if document.language is Language.OTHER and document.language_other is None:
        add(
            DocumentValidationErrorCode.LANGUAGE_OTHER_REQUIRED,
            ("language", "language_other"),
            "language_other is required when language is Other.",
        )

    if (
        document.last_review_date is not None
        and document.last_review_date < document.effective_date
    ):
        add(
            DocumentValidationErrorCode.LAST_REVIEW_BEFORE_EFFECTIVE,
            ("last_review_date", "effective_date"),
            "last_review_date cannot be before effective_date.",
        )
    review_reference = document.last_review_date or document.effective_date
    if document.next_review_date is not None and document.next_review_date <= review_reference:
        add(
            DocumentValidationErrorCode.NEXT_REVIEW_NOT_AFTER_REFERENCE,
            ("next_review_date", "last_review_date", "effective_date"),
            "next_review_date must be after last_review_date, or after effective_date when "
            "last_review_date is absent.",
        )

    if document.access_level is AccessLevel.ROLE_RESTRICTED and not document.permitted_roles:
        add(
            DocumentValidationErrorCode.PERMITTED_ROLES_REQUIRED,
            ("access_level", "permitted_roles"),
            "permitted_roles must contain at least one role for Role Restricted access.",
        )
    permitted = {role.casefold() for role in document.permitted_roles or ()}
    restricted = {role.casefold() for role in document.restricted_roles or ()}
    if permitted & restricted:
        add(
            DocumentValidationErrorCode.ROLE_LISTS_OVERLAP,
            ("permitted_roles", "restricted_roles"),
            "A role cannot appear in both permitted_roles and restricted_roles.",
        )

    if (
        document.access_level is AccessLevel.DO_NOT_ADD_TO_RAG
        and document.approved_for_rag is RagApprovalStatus.APPROVED
    ):
        add(
            DocumentValidationErrorCode.RAG_BLOCKED_BY_ACCESS_LEVEL,
            ("access_level", "approved_for_rag"),
            "approved_for_rag cannot be Approved when access_level is Do Not Add to RAG.",
        )
    if (
        document.approved_for_rag is RagApprovalStatus.APPROVED
        and document.approval_status is not ApprovalStatus.APPROVED
    ):
        add(
            DocumentValidationErrorCode.RAG_REQUIRES_DOCUMENT_APPROVAL,
            ("approved_for_rag", "approval_status"),
            "approval_status must be Approved before approved_for_rag can be Approved.",
        )
    if (
        document.approval_status is not ApprovalStatus.APPROVED
        and document.document_status is DocumentStatus.ACTIVE
    ):
        add(
            DocumentValidationErrorCode.ACTIVE_REQUIRES_DOCUMENT_APPROVAL,
            ("approval_status", "document_status"),
            "document_status cannot be Active unless approval_status is Approved.",
        )
    if (
        document.document_status is DocumentStatus.ACTIVE
        and document.approved_for_rag is not RagApprovalStatus.APPROVED
    ):
        add(
            DocumentValidationErrorCode.ACTIVE_REQUIRES_RAG_APPROVAL,
            ("document_status", "approved_for_rag"),
            "approved_for_rag must be Approved before document_status can be Active.",
        )
    if document.document_status is DocumentStatus.ACTIVE and document.approved_by is None:
        add(
            DocumentValidationErrorCode.ACTIVE_REQUIRES_APPROVER,
            ("document_status", "approved_by"),
            "approved_by is required before document_status can be Active.",
        )

    unresolved_data = (
        document.contains_personal_data is DataDeclaration.UNSURE
        or document.contains_confidential_data is DataDeclaration.UNSURE
    )
    if unresolved_data and document.document_status is DocumentStatus.ACTIVE:
        add(
            DocumentValidationErrorCode.UNRESOLVED_DATA_BLOCKS_ACTIVE,
            ("contains_personal_data", "contains_confidential_data", "document_status"),
            "Unresolved personal or confidential data prevents Active status.",
        )
    if unresolved_data and document.approved_for_rag is RagApprovalStatus.APPROVED:
        add(
            DocumentValidationErrorCode.UNRESOLVED_DATA_BLOCKS_RAG,
            ("contains_personal_data", "contains_confidential_data", "approved_for_rag"),
            "Unresolved personal or confidential data prevents RAG approval.",
        )

    unresolved_redaction = document.redaction_status in {
        RedactionStatus.REQUIRED,
        RedactionStatus.PENDING,
    }
    if unresolved_redaction and document.document_status is DocumentStatus.ACTIVE:
        add(
            DocumentValidationErrorCode.REDACTION_BLOCKS_ACTIVE,
            ("redaction_status", "document_status"),
            "Required or pending redaction prevents Active status.",
        )
    if unresolved_redaction and document.approved_for_rag is RagApprovalStatus.APPROVED:
        add(
            DocumentValidationErrorCode.REDACTION_BLOCKS_RAG,
            ("redaction_status", "approved_for_rag"),
            "Required or pending redaction prevents RAG approval.",
        )
    declared_sensitive_data = (
        document.contains_personal_data is DataDeclaration.YES
        or document.contains_confidential_data is DataDeclaration.YES
    )
    if declared_sensitive_data and document.redaction_status is None:
        add(
            DocumentValidationErrorCode.REDACTION_STATUS_REQUIRED,
            ("contains_personal_data", "contains_confidential_data", "redaction_status"),
            "redaction_status is required when personal or confidential data is Yes.",
        )
    if (
        declared_sensitive_data
        and document.redaction_status is RedactionStatus.NOT_REQUIRED
    ):
        add(
            DocumentValidationErrorCode.SENSITIVE_DATA_REDACTION_NOT_REQUIRED,
            ("contains_personal_data", "contains_confidential_data", "redaction_status"),
            "redaction_status cannot be Not Required when personal or confidential data is Yes.",
        )

    if document.synthetic is not True:
        add(
            DocumentValidationErrorCode.SYNTHETIC_REQUIRED,
            ("synthetic",),
            "synthetic must be true during Phase 1 development.",
        )
    if document.official_company_document is not False:
        add(
            DocumentValidationErrorCode.OFFICIAL_DOCUMENT_PROHIBITED,
            ("official_company_document",),
            "official_company_document must be false during Phase 1 development.",
        )
    if str(document.data_mode) != DataMode.SYNTHETIC_DEMO.value:
        add(
            DocumentValidationErrorCode.INVALID_DATA_MODE,
            ("data_mode",),
            "data_mode must be synthetic_demo during Phase 1 development.",
        )

    return DocumentValidationResult(errors=tuple(errors))
