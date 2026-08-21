"""Deterministic orchestration for HR document approval and publication."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from app.domain.documents import (
    ApprovalDecisionType,
    DocumentVersionRecord,
    DocumentVersionStatus,
)
from app.repositories.documents import DocumentRepository
from app.schemas.hr_documents import (
    ApprovalStatus,
    DocumentStatus,
    HRDocumentMetadata,
    RagApprovalStatus,
)
from app.services.document_validation import (
    DocumentValidationErrorCode,
    validate_hr_document,
)
from app.services.hr_markdown import (
    HRMarkdownValidationError,
    render_hr_document_markdown,
)


class HRPublicationErrorCode(StrEnum):
    DOCUMENT_VALIDATION_FAILED = "document_validation_failed"
    MARKDOWN_RENDERING_FAILED = "markdown_rendering_failed"
    APPROVAL_MISSING = "approval_missing"
    RAG_APPROVAL_MISSING = "rag_approval_missing"
    APPROVER_MISSING = "approver_missing"
    DOCUMENT_NOT_APPROVED = "document_not_approved"
    VERSION_NOT_FOUND = "version_not_found"
    VERSION_NOT_APPROVED = "version_not_approved"


@dataclass(frozen=True, slots=True)
class PublicationEligibilityIssue:
    """One stable publication blocker with optional source-validation detail."""

    code: HRPublicationErrorCode
    reason: str
    validation_error_codes: tuple[DocumentValidationErrorCode, ...] = ()


@dataclass(frozen=True, slots=True)
class PublicationEligibilityResult:
    """Ordered, deterministic HR publication eligibility result."""

    issues: tuple[PublicationEligibilityIssue, ...]

    @property
    def is_eligible(self) -> bool:
        return not self.issues

    @property
    def error_codes(self) -> tuple[HRPublicationErrorCode, ...]:
        return tuple(issue.code for issue in self.issues)

    @property
    def reasons(self) -> tuple[str, ...]:
        return tuple(issue.reason for issue in self.issues)


class HRPublicationError(RuntimeError):
    """Raised when a publication operation cannot cross a governed gate."""

    def __init__(self, issues: tuple[PublicationEligibilityIssue, ...]) -> None:
        self.issues = issues
        super().__init__(str(self))

    @property
    def error_codes(self) -> tuple[HRPublicationErrorCode, ...]:
        return tuple(issue.code for issue in self.issues)

    def __str__(self) -> str:
        codes = ", ".join(issue.code.value for issue in self.issues)
        return f"HR publication blocked: {codes}"


def _issue(code: HRPublicationErrorCode, reason: str) -> PublicationEligibilityIssue:
    return PublicationEligibilityIssue(code=code, reason=reason)


def check_hr_publication_eligibility(
    document: HRDocumentMetadata,
) -> PublicationEligibilityResult:
    """Check deterministic document and rendering gates before persistence access."""
    validation = validate_hr_document(document)
    if not validation.is_valid:
        return PublicationEligibilityResult(
            issues=(
                PublicationEligibilityIssue(
                    code=HRPublicationErrorCode.DOCUMENT_VALIDATION_FAILED,
                    reason="The HR document failed deterministic validation.",
                    validation_error_codes=tuple(error.code for error in validation.errors),
                ),
            )
        )

    try:
        render_hr_document_markdown(document)
    except HRMarkdownValidationError as error:
        return PublicationEligibilityResult(
            issues=(
                PublicationEligibilityIssue(
                    code=HRPublicationErrorCode.MARKDOWN_RENDERING_FAILED,
                    reason="The HR document could not be rendered as standardized Markdown.",
                    validation_error_codes=error.error_codes,
                ),
            )
        )

    issues: list[PublicationEligibilityIssue] = []
    if document.approval_status is not ApprovalStatus.APPROVED:
        issues.append(
            _issue(
                HRPublicationErrorCode.APPROVAL_MISSING,
                "approval_status must be Approved before publication.",
            )
        )
    if document.approved_for_rag is not RagApprovalStatus.APPROVED:
        issues.append(
            _issue(
                HRPublicationErrorCode.RAG_APPROVAL_MISSING,
                "approved_for_rag must be Approved before publication.",
            )
        )
    if document.approved_by is None:
        issues.append(
            _issue(
                HRPublicationErrorCode.APPROVER_MISSING,
                "approved_by must be present before publication.",
            )
        )
    if document.document_status is not DocumentStatus.APPROVED:
        issues.append(
            _issue(
                HRPublicationErrorCode.DOCUMENT_NOT_APPROVED,
                "document_status must be Approved before publication.",
            )
        )

    return PublicationEligibilityResult(issues=tuple(issues))


def record_hr_approval(
    repository: DocumentRepository,
    *,
    version_id: UUID,
    reviewer_actor_ref: str,
    decision: ApprovalDecisionType,
    correlation_id: str,
    reason_notes: str | None = None,
) -> DocumentVersionRecord:
    """Delegate an HR approval decision to the document repository."""
    return repository.record_approval(
        version_id=version_id,
        reviewer_actor_ref=reviewer_actor_ref,
        decision=decision,
        correlation_id=correlation_id,
        reason_notes=reason_notes,
    )


def publish_hr_document_version(
    repository: DocumentRepository,
    *,
    version_id: UUID,
    document: HRDocumentMetadata,
) -> DocumentVersionRecord:
    """Activate an eligible HR document whose stored version is already approved."""
    eligibility = check_hr_publication_eligibility(document)
    if not eligibility.is_eligible:
        raise HRPublicationError(eligibility.issues)

    version = repository.get_version(version_id)
    if version is None:
        raise HRPublicationError(
            (
                _issue(
                    HRPublicationErrorCode.VERSION_NOT_FOUND,
                    "The document version does not exist.",
                ),
            )
        )
    if version.status is not DocumentVersionStatus.APPROVED:
        raise HRPublicationError(
            (
                _issue(
                    HRPublicationErrorCode.VERSION_NOT_APPROVED,
                    "The repository document version must be approved before publication.",
                ),
            )
        )

    return repository.activate_approved_version(version_id)
