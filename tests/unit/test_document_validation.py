"""Cross-field tests for deterministic HR document validation."""

from typing import Any

import pytest

from app.schemas.hr_documents import HRDocumentMetadata
from app.services.document_validation import (
    DocumentValidationErrorCode,
    validate_hr_document,
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
    }


def _document(**overrides: Any) -> HRDocumentMetadata:
    payload = _valid_payload()
    payload.update(overrides)
    return HRDocumentMetadata.model_validate(payload)


def _codes(document: HRDocumentMetadata) -> tuple[DocumentValidationErrorCode, ...]:
    return tuple(error.code for error in validate_hr_document(document).errors)


def test_valid_synthetic_hr_document_has_no_cross_field_errors() -> None:
    result = validate_hr_document(_document())

    assert result.is_valid is True
    assert result.errors == ()


@pytest.mark.parametrize(
    ("field", "companion", "code"),
    [
        (
            "document_type",
            "document_type_other",
            DocumentValidationErrorCode.DOCUMENT_TYPE_OTHER_REQUIRED,
        ),
        (
            "department",
            "department_other",
            DocumentValidationErrorCode.DEPARTMENT_OTHER_REQUIRED,
        ),
        ("language", "language_other", DocumentValidationErrorCode.LANGUAGE_OTHER_REQUIRED),
    ],
)
def test_other_requires_its_companion_field(
    field: str,
    companion: str,
    code: DocumentValidationErrorCode,
) -> None:
    document = _document(**{field: "Other"})
    result = validate_hr_document(document)

    assert _codes(document) == (code,)
    assert companion in result.errors[0].fields


def test_other_with_companion_field_is_valid() -> None:
    document = _document(document_type="Other", document_type_other="Synthetic Memo")

    assert validate_hr_document(document).is_valid is True


def test_last_review_date_cannot_precede_effective_date() -> None:
    document = _document(last_review_date="2026-07-31")

    assert _codes(document) == (
        DocumentValidationErrorCode.LAST_REVIEW_BEFORE_EFFECTIVE,
    )


@pytest.mark.parametrize(
    "dates",
    [
        {"next_review_date": "2026-08-01"},
        {"last_review_date": "2026-08-10", "next_review_date": "2026-08-10"},
    ],
)
def test_next_review_date_must_be_after_its_reference(dates: dict[str, str]) -> None:
    document = _document(**dates)

    assert _codes(document) == (
        DocumentValidationErrorCode.NEXT_REVIEW_NOT_AFTER_REFERENCE,
    )


def test_role_restricted_access_requires_permitted_roles() -> None:
    document = _document(access_level="Role Restricted")

    assert _codes(document) == (DocumentValidationErrorCode.PERMITTED_ROLES_REQUIRED,)


def test_role_overlap_is_detected_case_insensitively() -> None:
    document = _document(
        access_level="Role Restricted",
        permitted_roles=["HR Reviewer"],
        restricted_roles=["hr reviewer"],
    )

    assert _codes(document) == (DocumentValidationErrorCode.ROLE_LISTS_OVERLAP,)


def test_rag_approval_requires_document_approval() -> None:
    document = _document(approval_status="Pending Review")

    assert _codes(document) == (
        DocumentValidationErrorCode.RAG_REQUIRES_DOCUMENT_APPROVAL,
    )


def test_do_not_add_to_rag_conflicts_with_rag_approval() -> None:
    document = _document(access_level="Do Not Add to RAG")

    assert _codes(document) == (
        DocumentValidationErrorCode.RAG_BLOCKED_BY_ACCESS_LEVEL,
    )


def test_unapproved_document_cannot_be_active() -> None:
    document = _document(
        approval_status="Rejected",
        approved_for_rag="Rejected",
        document_status="Active",
        approved_by="Synthetic Approver",
    )

    assert _codes(document) == (
        DocumentValidationErrorCode.ACTIVE_REQUIRES_DOCUMENT_APPROVAL,
        DocumentValidationErrorCode.ACTIVE_REQUIRES_RAG_APPROVAL,
    )


def test_active_document_requires_approver_metadata() -> None:
    document = _document(document_status="Active")

    assert _codes(document) == (DocumentValidationErrorCode.ACTIVE_REQUIRES_APPROVER,)


@pytest.mark.parametrize("rag_status", ["Pending Review", "Rejected"])
def test_active_document_requires_rag_approval(rag_status: str) -> None:
    document = _document(
        approved_for_rag=rag_status,
        document_status="Active",
        approved_by="Synthetic Approver",
    )

    assert _codes(document) == (
        DocumentValidationErrorCode.ACTIVE_REQUIRES_RAG_APPROVAL,
    )


@pytest.mark.parametrize("field", ["contains_personal_data", "contains_confidential_data"])
def test_unresolved_data_blocks_activation_and_rag_approval(field: str) -> None:
    document = _document(
        **{field: "Unsure"},
        document_status="Active",
        approved_by="Synthetic Approver",
    )

    assert _codes(document) == (
        DocumentValidationErrorCode.UNRESOLVED_DATA_BLOCKS_ACTIVE,
        DocumentValidationErrorCode.UNRESOLVED_DATA_BLOCKS_RAG,
    )


@pytest.mark.parametrize("redaction_status", ["Required", "Pending"])
def test_unresolved_redaction_blocks_activation_and_rag_approval(
    redaction_status: str,
) -> None:
    document = _document(
        redaction_status=redaction_status,
        document_status="Active",
        approved_by="Synthetic Approver",
    )

    assert _codes(document) == (
        DocumentValidationErrorCode.REDACTION_BLOCKS_ACTIVE,
        DocumentValidationErrorCode.REDACTION_BLOCKS_RAG,
    )


@pytest.mark.parametrize("field", ["contains_personal_data", "contains_confidential_data"])
def test_declared_sensitive_data_requires_redaction_status(field: str) -> None:
    document = _document(**{field: "Yes"})

    assert _codes(document) == (DocumentValidationErrorCode.REDACTION_STATUS_REQUIRED,)


@pytest.mark.parametrize("field", ["contains_personal_data", "contains_confidential_data"])
def test_declared_sensitive_data_rejects_not_required_redaction(field: str) -> None:
    document = _document(**{field: "Yes"}, redaction_status="Not Required")

    assert _codes(document) == (
        DocumentValidationErrorCode.SENSITIVE_DATA_REDACTION_NOT_REQUIRED,
    )


@pytest.mark.parametrize("field", ["contains_personal_data", "contains_confidential_data"])
def test_completed_redaction_is_acceptable_for_declared_sensitive_data(field: str) -> None:
    document = _document(**{field: "Yes"}, redaction_status="Completed")

    assert validate_hr_document(document).is_valid is True


def test_invalid_phase_one_boolean_flags_are_reported_in_fixed_order() -> None:
    document = _document(synthetic=False, official_company_document=True)

    assert _codes(document) == (
        DocumentValidationErrorCode.SYNTHETIC_REQUIRED,
        DocumentValidationErrorCode.OFFICIAL_DOCUMENT_PROHIBITED,
    )


def test_invalid_data_mode_is_rejected_by_the_schema() -> None:
    with pytest.raises(ValueError, match="synthetic_demo"):
        _document(data_mode="live_company_data")


def test_validation_errors_have_stable_codes_fields_and_messages() -> None:
    result = validate_hr_document(_document(access_level="Role Restricted"))

    assert result.errors[0].code == DocumentValidationErrorCode.PERMITTED_ROLES_REQUIRED
    assert result.errors[0].fields == ("access_level", "permitted_roles")
    assert result.errors[0].message == (
        "permitted_roles must contain at least one role for Role Restricted access."
    )
