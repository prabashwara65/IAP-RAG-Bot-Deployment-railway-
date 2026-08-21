"""Structural tests for the governed HR document metadata contract."""

from typing import Any

import pytest
from pydantic import ValidationError

from app.schemas.hr_documents import HRDocumentMetadata


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


def test_valid_synthetic_hr_document_is_parsed() -> None:
    document = HRDocumentMetadata.model_validate(_valid_payload())

    assert document.document_title == "Synthetic Leave Policy"
    assert document.document_type.value == "Policy"
    assert document.synthetic is True
    assert document.official_company_document is False
    assert document.data_mode.value == "synthetic_demo"


@pytest.mark.parametrize(
    "field",
    [
        "document_title",
        "document_type",
        "department",
        "summary_purpose",
        "language",
        "version",
        "effective_date",
        "content_owner",
        "approval_status",
        "approved_for_rag",
        "document_status",
        "access_level",
        "contains_personal_data",
        "contains_confidential_data",
        "synthetic",
        "official_company_document",
        "data_mode",
        "document_content",
    ],
)
def test_each_required_field_must_be_present(field: str) -> None:
    payload = _valid_payload()
    del payload[field]

    with pytest.raises(ValidationError) as exc_info:
        HRDocumentMetadata.model_validate(payload)

    assert exc_info.value.errors()[0]["loc"] == (field,)


@pytest.mark.parametrize(
    "field",
    [
        "document_title",
        "summary_purpose",
        "version",
        "content_owner",
        "document_content",
    ],
)
def test_required_text_cannot_be_blank(field: str) -> None:
    payload = _valid_payload()
    payload[field] = "   "

    with pytest.raises(ValidationError) as exc_info:
        HRDocumentMetadata.model_validate(payload)

    assert exc_info.value.errors()[0]["loc"] == (field,)


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("document_type", "Memo"),
        ("department", "Legal"),
        ("language", "French"),
        ("approval_status", "Waiting"),
        ("approved_for_rag", "Yes"),
        ("document_status", "Published"),
        ("access_level", "Public"),
        ("contains_personal_data", "Unknown"),
        ("contains_confidential_data", "Unknown"),
        ("redaction_status", "In Progress"),
        ("data_mode", "production"),
    ],
)
def test_invalid_controlled_values_are_rejected(field: str, invalid_value: str) -> None:
    payload = _valid_payload()
    payload[field] = invalid_value

    with pytest.raises(ValidationError) as exc_info:
        HRDocumentMetadata.model_validate(payload)

    assert exc_info.value.errors()[0]["loc"] == (field,)


def test_unknown_metadata_fields_are_rejected() -> None:
    payload = _valid_payload()
    payload["tenant_specific_approver"] = "Named Person"

    with pytest.raises(ValidationError) as exc_info:
        HRDocumentMetadata.model_validate(payload)

    assert exc_info.value.errors()[0]["type"] == "extra_forbidden"


def test_blank_items_in_metadata_lists_are_rejected() -> None:
    payload = _valid_payload()
    payload["keywords"] = ["leave", "   "]

    with pytest.raises(ValidationError) as exc_info:
        HRDocumentMetadata.model_validate(payload)

    assert exc_info.value.errors()[0]["loc"] == ("keywords", 1)
