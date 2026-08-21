"""Tests for deterministic standardized HR document Markdown rendering."""

import json
from typing import Any

import pytest

from app.schemas.hr_documents import HRDocumentMetadata
from app.services.document_validation import DocumentValidationErrorCode
from app.services.hr_markdown import (
    SYNTHETIC_DOCUMENT_NOTICE,
    HRMarkdownValidationError,
    render_hr_document_markdown,
)

EXPECTED_FRONT_MATTER_FIELDS = [
    "document_title",
    "document_type",
    "department",
    "language",
    "version",
    "effective_date",
    "last_review_date",
    "next_review_date",
    "content_owner",
    "approved_by",
    "approval_status",
    "approved_for_rag",
    "document_status",
    "access_level",
    "permitted_roles",
    "restricted_roles",
    "contains_personal_data",
    "contains_confidential_data",
    "redaction_status",
    "synthetic",
    "official_company_document",
    "data_mode",
    "keywords",
    "related_documents",
]


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


def _front_matter_lines(markdown: str) -> list[str]:
    lines = markdown.splitlines()
    closing_delimiter = lines.index("---", 1)
    return lines[1:closing_delimiter]


def test_valid_document_renders_standardized_markdown() -> None:
    markdown = render_hr_document_markdown(_document())

    assert markdown.startswith('---\ndocument_title: "Synthetic Leave Policy"\n')
    assert "\n# Synthetic Leave Policy\n" in markdown
    assert "\n## Purpose\n\nExplains synthetic leave rules for demonstration.\n" in markdown
    assert "\n## Document Content\n\nThis is synthetic HR policy content.\n" in markdown
    assert markdown.endswith("\n")


def test_same_input_produces_identical_output() -> None:
    document = _document()

    assert render_hr_document_markdown(document) == render_hr_document_markdown(document)


def test_front_matter_uses_explicit_stable_field_order() -> None:
    field_names = [line.split(":", 1)[0] for line in _front_matter_lines(
        render_hr_document_markdown(_document())
    )]

    assert field_names == EXPECTED_FRONT_MATTER_FIELDS


def test_enums_dates_booleans_and_missing_values_use_governed_yaml_scalars() -> None:
    front_matter = _front_matter_lines(render_hr_document_markdown(_document()))

    assert 'document_type: "Policy"' in front_matter
    assert 'department: "Human Resources"' in front_matter
    assert 'language: "English"' in front_matter
    assert 'effective_date: "2026-08-01"' in front_matter
    assert "last_review_date: null" in front_matter
    assert "next_review_date: null" in front_matter
    assert "approved_by: null" in front_matter
    assert "redaction_status: null" in front_matter
    assert "synthetic: true" in front_matter
    assert "official_company_document: false" in front_matter
    assert 'data_mode: "synthetic_demo"' in front_matter


def test_absent_or_empty_list_values_render_consistently() -> None:
    absent = render_hr_document_markdown(_document())
    explicitly_empty = render_hr_document_markdown(
        _document(permitted_roles=[], restricted_roles=[], keywords=[], related_documents=[])
    )

    for field in ("permitted_roles", "restricted_roles", "keywords", "related_documents"):
        assert f"{field}: []" in absent
        assert f"{field}: []" in explicitly_empty


def test_synthetic_notice_is_present_without_company_or_person_invention() -> None:
    markdown = render_hr_document_markdown(_document())

    assert f"> {SYNTHETIC_DOCUMENT_NOTICE}" in markdown
    assert "Apps Technologies" not in markdown
    assert "Jane Doe" not in markdown


def test_optional_metadata_sections_render_when_supplied() -> None:
    document = _document(
        document_type="Other",
        document_type_other="Synthetic Handbook",
        department="Other",
        department_other="Synthetic People Operations",
        language="Other",
        language_other="Synthetic Test Language",
        section_headings=["Scope", "Responsibilities"],
        related_documents=["Synthetic Code of Conduct"],
        keywords=["leave", "synthetic"],
        reviewer_notes="Reviewed only for demonstration.",
    )

    markdown = render_hr_document_markdown(document)

    assert "## Section Headings\n\n- Scope\n- Responsibilities" in markdown
    assert "## Related Documents\n\n- Synthetic Code of Conduct" in markdown
    assert "## Keywords\n\n- leave\n- synthetic" in markdown
    assert "## Reviewer Notes\n\nReviewed only for demonstration." in markdown
    assert "## Other Document Type Details\n\nSynthetic Handbook" in markdown
    assert "## Other Department Details\n\nSynthetic People Operations" in markdown
    assert "## Other Language Details\n\nSynthetic Test Language" in markdown


def test_optional_sections_are_omitted_when_values_are_absent() -> None:
    markdown = render_hr_document_markdown(_document())

    for heading in (
        "Section Headings",
        "Related Documents",
        "Keywords",
        "Reviewer Notes",
        "Other Document Type Details",
        "Other Department Details",
        "Other Language Details",
    ):
        assert f"## {heading}" not in markdown


def test_yaml_strings_with_special_characters_are_safely_escaped() -> None:
    title = 'Synthetic "Policy": #1\nSecond line'
    keywords = ["needs: review", "#synthetic", 'quoted "value"', "line\nbreak"]
    markdown = render_hr_document_markdown(_document(document_title=title, keywords=keywords))
    front_matter = _front_matter_lines(markdown)

    assert f"document_title: {json.dumps(title, ensure_ascii=False)}" in front_matter
    expected_keywords = "[" + ", ".join(
        json.dumps(value, ensure_ascii=False) for value in keywords
    ) + "]"
    assert f"keywords: {expected_keywords}" in front_matter
    assert "\\n" in front_matter[0]


def test_invalid_document_is_refused_with_stable_validation_codes() -> None:
    document = _document(access_level="Role Restricted")

    with pytest.raises(HRMarkdownValidationError) as exc_info:
        render_hr_document_markdown(document)

    error = exc_info.value
    assert error.error_codes == (DocumentValidationErrorCode.PERMITTED_ROLES_REQUIRED,)
    assert error.validation_errors[0].fields == ("access_level", "permitted_roles")
    assert str(error) == (
        "HR document failed deterministic validation: permitted_roles_required"
    )
