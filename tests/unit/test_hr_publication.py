"""Unit tests for deterministic HR approval and publication orchestration."""

from typing import Any
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest

from app.domain.documents import (
    ApprovalDecisionType,
    DocumentVersionRecord,
    DocumentVersionStatus,
)
from app.repositories.documents import DocumentRepository
from app.schemas.hr_documents import HRDocumentMetadata
from app.services.document_validation import DocumentValidationErrorCode
from app.services.hr_publication import (
    HRPublicationError,
    HRPublicationErrorCode,
    check_hr_publication_eligibility,
    publish_hr_document_version,
    record_hr_approval,
)


def _valid_payload() -> dict[str, Any]:
    return {
        "document_title": "Synthetic Leave Policy",
        "document_type": "Policy",
        "department": "Human Resources",
        "summary_purpose": "Explains synthetic leave rules for demonstration.",
        "language": "English",
        "version": "1.0",
        "effective_date": "2026-08-01",
        "content_owner": "Synthetic HR Team",
        "approval_status": "Approved",
        "approved_for_rag": "Approved",
        "document_status": "Approved",
        "access_level": "Internal General",
        "contains_personal_data": "No",
        "contains_confidential_data": "No",
        "synthetic": True,
        "official_company_document": False,
        "data_mode": "synthetic_demo",
        "document_content": "This is synthetic HR policy content.",
        "approved_by": "Synthetic Reviewer",
    }


def _document(**overrides: Any) -> HRDocumentMetadata:
    payload = _valid_payload()
    payload.update(overrides)
    return HRDocumentMetadata.model_validate(payload)


def _version(
    *,
    version_id: UUID | None = None,
    status: DocumentVersionStatus,
) -> DocumentVersionRecord:
    return DocumentVersionRecord(
        id=version_id or uuid4(),
        document_id=uuid4(),
        version_label="1.0",
        status=status,
        content_hash="synthetic-content-hash",
    )


def _repository() -> Mock:
    return Mock(spec=DocumentRepository)


def test_approved_synthetic_hr_document_is_eligible() -> None:
    result = check_hr_publication_eligibility(_document())

    assert result.is_eligible is True
    assert result.error_codes == ()
    assert result.reasons == ()


def test_invalid_document_is_not_eligible_and_preserves_validation_codes() -> None:
    result = check_hr_publication_eligibility(
        _document(access_level="Role Restricted")
    )

    assert result.is_eligible is False
    assert result.error_codes == (HRPublicationErrorCode.DOCUMENT_VALIDATION_FAILED,)
    assert result.issues[0].validation_error_codes == (
        DocumentValidationErrorCode.PERMITTED_ROLES_REQUIRED,
    )


@pytest.mark.parametrize("rag_status", ["Pending Review", "Rejected"])
def test_pending_or_rejected_rag_approval_blocks_publication(rag_status: str) -> None:
    result = check_hr_publication_eligibility(_document(approved_for_rag=rag_status))

    assert result.error_codes == (HRPublicationErrorCode.RAG_APPROVAL_MISSING,)


def test_missing_approver_blocks_publication() -> None:
    result = check_hr_publication_eligibility(_document(approved_by=None))

    assert result.error_codes == (HRPublicationErrorCode.APPROVER_MISSING,)


@pytest.mark.parametrize(
    ("overrides", "validation_code"),
    [
        (
            {"contains_personal_data": "Unsure"},
            DocumentValidationErrorCode.UNRESOLVED_DATA_BLOCKS_RAG,
        ),
        (
            {"redaction_status": "Pending"},
            DocumentValidationErrorCode.REDACTION_BLOCKS_RAG,
        ),
    ],
)
def test_unresolved_sensitivity_or_redaction_uses_existing_validation_gate(
    overrides: dict[str, str],
    validation_code: DocumentValidationErrorCode,
) -> None:
    result = check_hr_publication_eligibility(_document(**overrides))

    assert result.error_codes == (HRPublicationErrorCode.DOCUMENT_VALIDATION_FAILED,)
    assert result.issues[0].validation_error_codes == (validation_code,)


def test_eligibility_error_codes_have_stable_order() -> None:
    result = check_hr_publication_eligibility(
        _document(
            approval_status="Pending Review",
            approved_for_rag="Pending Review",
            approved_by=None,
            document_status="Under Review",
        )
    )

    assert result.error_codes == (
        HRPublicationErrorCode.APPROVAL_MISSING,
        HRPublicationErrorCode.RAG_APPROVAL_MISSING,
        HRPublicationErrorCode.APPROVER_MISSING,
        HRPublicationErrorCode.DOCUMENT_NOT_APPROVED,
    )


def test_record_hr_approval_delegates_all_values_and_preserves_correlation_id() -> None:
    repository = _repository()
    version_id = uuid4()
    approved = _version(version_id=version_id, status=DocumentVersionStatus.APPROVED)
    repository.record_approval.return_value = approved

    result = record_hr_approval(
        repository,
        version_id=version_id,
        reviewer_actor_ref="arbitrary-tenant-actor-ref",
        decision=ApprovalDecisionType.APPROVED,
        correlation_id="correlation-publication-test",
        reason_notes="Synthetic approval test.",
    )

    assert result == approved
    repository.record_approval.assert_called_once_with(
        version_id=version_id,
        reviewer_actor_ref="arbitrary-tenant-actor-ref",
        decision=ApprovalDecisionType.APPROVED,
        correlation_id="correlation-publication-test",
        reason_notes="Synthetic approval test.",
    )


@pytest.mark.parametrize(
    "status",
    [DocumentVersionStatus.CANDIDATE, DocumentVersionStatus.FAILED],
)
def test_publication_refuses_unapproved_repository_version(
    status: DocumentVersionStatus,
) -> None:
    repository = _repository()
    version = _version(status=status)
    repository.get_version.return_value = version

    with pytest.raises(HRPublicationError) as exc_info:
        publish_hr_document_version(
            repository,
            version_id=version.id,
            document=_document(),
        )

    assert exc_info.value.error_codes == (HRPublicationErrorCode.VERSION_NOT_APPROVED,)
    repository.activate_approved_version.assert_not_called()


def test_publication_refuses_missing_repository_version() -> None:
    repository = _repository()
    version_id = uuid4()
    repository.get_version.return_value = None

    with pytest.raises(HRPublicationError) as exc_info:
        publish_hr_document_version(
            repository,
            version_id=version_id,
            document=_document(),
        )

    assert exc_info.value.error_codes == (HRPublicationErrorCode.VERSION_NOT_FOUND,)
    repository.activate_approved_version.assert_not_called()


def test_publication_activates_an_approved_repository_version() -> None:
    repository = _repository()
    approved = _version(status=DocumentVersionStatus.APPROVED)
    active = DocumentVersionRecord(
        id=approved.id,
        document_id=approved.document_id,
        version_label=approved.version_label,
        status=DocumentVersionStatus.ACTIVE,
        content_hash=approved.content_hash,
    )
    repository.get_version.return_value = approved
    repository.activate_approved_version.return_value = active

    result = publish_hr_document_version(
        repository,
        version_id=approved.id,
        document=_document(),
    )

    assert result == active
    repository.get_version.assert_called_once_with(approved.id)
    repository.activate_approved_version.assert_called_once_with(approved.id)


def test_ineligible_document_is_refused_before_repository_access() -> None:
    repository = _repository()

    with pytest.raises(HRPublicationError) as exc_info:
        publish_hr_document_version(
            repository,
            version_id=uuid4(),
            document=_document(approved_by=None),
        )

    assert exc_info.value.error_codes == (HRPublicationErrorCode.APPROVER_MISSING,)
    repository.get_version.assert_not_called()
    repository.activate_approved_version.assert_not_called()
