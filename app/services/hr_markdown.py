"""Deterministic standardized Markdown rendering for validated HR documents."""

from __future__ import annotations

import json
from datetime import date
from enum import StrEnum

from app.schemas.hr_documents import HRDocumentMetadata
from app.services.document_validation import (
    DocumentValidationError,
    DocumentValidationErrorCode,
    validate_hr_document,
)

SYNTHETIC_DOCUMENT_NOTICE = (
    "SYNTHETIC DEMO DOCUMENT — This document was created only for OIAP development, "
    "testing, and demonstration. It is not an official company HR policy or procedure."
)

type YAMLScalar = str | bool | date | StrEnum | None
type YAMLValue = YAMLScalar | list[str]


class HRMarkdownValidationError(ValueError):
    """Raised when deterministic document validation prevents rendering."""

    def __init__(self, validation_errors: tuple[DocumentValidationError, ...]) -> None:
        self.validation_errors = validation_errors
        super().__init__(str(self))

    def __str__(self) -> str:
        codes = ", ".join(error.code.value for error in self.validation_errors)
        return f"HR document failed deterministic validation: {codes}"

    @property
    def error_codes(self) -> tuple[DocumentValidationErrorCode, ...]:
        """Expose stable validation codes without parsing an exception message."""
        return tuple(error.code for error in self.validation_errors)


def _front_matter_fields(document: HRDocumentMetadata) -> tuple[tuple[str, YAMLValue], ...]:
    """Return front-matter values in the governed output order."""
    return (
        ("document_title", document.document_title),
        ("document_type", document.document_type),
        ("department", document.department),
        ("language", document.language),
        ("version", document.version),
        ("effective_date", document.effective_date),
        ("last_review_date", document.last_review_date),
        ("next_review_date", document.next_review_date),
        ("content_owner", document.content_owner),
        ("approved_by", document.approved_by),
        ("approval_status", document.approval_status),
        ("approved_for_rag", document.approved_for_rag),
        ("document_status", document.document_status),
        ("access_level", document.access_level),
        ("permitted_roles", document.permitted_roles or []),
        ("restricted_roles", document.restricted_roles or []),
        ("contains_personal_data", document.contains_personal_data),
        ("contains_confidential_data", document.contains_confidential_data),
        ("redaction_status", document.redaction_status),
        ("synthetic", document.synthetic),
        ("official_company_document", document.official_company_document),
        ("data_mode", document.data_mode),
        ("keywords", document.keywords or []),
        ("related_documents", document.related_documents or []),
    )


def _yaml_string(value: str) -> str:
    """Encode a string as a JSON scalar, which is also valid YAML 1.2."""
    return json.dumps(value, ensure_ascii=False)


def _serialize_yaml_value(value: YAMLValue) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, date):
        return _yaml_string(value.isoformat())
    if isinstance(value, StrEnum):
        return _yaml_string(value.value)
    if isinstance(value, str):
        return _yaml_string(value)
    return "[" + ", ".join(_yaml_string(item) for item in value) + "]"


def _append_optional_list_section(lines: list[str], heading: str, values: list[str] | None) -> None:
    if values:
        lines.extend((f"## {heading}", ""))
        lines.extend(f"- {value}" for value in values)
        lines.append("")


def _append_optional_text_section(lines: list[str], heading: str, value: str | None) -> None:
    if value is not None:
        lines.extend((f"## {heading}", "", value, ""))


def render_hr_document_markdown(document: HRDocumentMetadata) -> str:
    """Render a validated HR document as deterministic Markdown with YAML metadata."""
    validation = validate_hr_document(document)
    if not validation.is_valid:
        raise HRMarkdownValidationError(validation.errors)

    lines = ["---"]
    lines.extend(
        f"{field_name}: {_serialize_yaml_value(value)}"
        for field_name, value in _front_matter_fields(document)
    )
    lines.extend(
        (
            "---",
            "",
            f"# {document.document_title}",
            "",
            f"> {SYNTHETIC_DOCUMENT_NOTICE}",
            "",
            "## Purpose",
            "",
            document.summary_purpose,
            "",
            "## Document Content",
            "",
            document.document_content,
            "",
        )
    )

    _append_optional_list_section(lines, "Section Headings", document.section_headings)
    _append_optional_list_section(lines, "Related Documents", document.related_documents)
    _append_optional_list_section(lines, "Keywords", document.keywords)
    _append_optional_text_section(lines, "Reviewer Notes", document.reviewer_notes)
    _append_optional_text_section(
        lines,
        "Other Document Type Details",
        document.document_type_other,
    )
    _append_optional_text_section(lines, "Other Department Details", document.department_other)
    _append_optional_text_section(lines, "Other Language Details", document.language_other)

    return "\n".join(lines).rstrip() + "\n"
