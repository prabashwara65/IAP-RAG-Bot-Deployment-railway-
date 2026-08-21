"""Governed metadata contract for synthetic HR documents."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

NonBlankString = Annotated[str, Field(min_length=1)]


class DocumentType(StrEnum):
    POLICY = "Policy"
    PROCEDURE = "Procedure"
    COMPANY_PROFILE = "Company Profile"
    ORGANIZATION_STRUCTURE = "Organization Structure"
    DEPARTMENT_DIRECTORY = "Department Directory"
    EMPLOYEE_RESPONSIBILITY_DIRECTORY = "Employee Responsibility Directory"
    RESPONSIBILITY_MATRIX = "Responsibility Matrix"
    APPROVAL_MATRIX = "Approval Matrix"
    ESCALATION_MATRIX = "Escalation Matrix"
    FAQ = "FAQ"
    TECHNICAL_GUIDELINE = "Technical Guideline"
    CONTACT_DIRECTORY = "Contact Directory"
    OTHER = "Other"


class Department(StrEnum):
    HUMAN_RESOURCES = "Human Resources"
    INFORMATION_TECHNOLOGY = "Information Technology"
    FINANCE = "Finance"
    OPERATIONS = "Operations"
    SOFTWARE_DEVELOPMENT = "Software Development"
    SALES = "Sales"
    CUSTOMER_SUPPORT = "Customer Support"
    MANAGEMENT = "Management"
    OTHER = "Other"


class Language(StrEnum):
    ENGLISH = "English"
    SINHALA = "Sinhala"
    TAMIL = "Tamil"
    OTHER = "Other"


class ApprovalStatus(StrEnum):
    PENDING_REVIEW = "Pending Review"
    APPROVED = "Approved"
    REJECTED = "Rejected"


class RagApprovalStatus(StrEnum):
    PENDING_REVIEW = "Pending Review"
    APPROVED = "Approved"
    REJECTED = "Rejected"


class DocumentStatus(StrEnum):
    DRAFT = "Draft"
    UNDER_REVIEW = "Under Review"
    APPROVED = "Approved"
    ACTIVE = "Active"
    SUPERSEDED = "Superseded"
    ARCHIVED = "Archived"
    REJECTED = "Rejected"


class AccessLevel(StrEnum):
    INTERNAL_GENERAL = "Internal General"
    DEPARTMENT_RESTRICTED = "Department Restricted"
    ROLE_RESTRICTED = "Role Restricted"
    MANAGEMENT_CONFIDENTIAL = "Management Confidential"
    DO_NOT_ADD_TO_RAG = "Do Not Add to RAG"


class DataDeclaration(StrEnum):
    YES = "Yes"
    NO = "No"
    UNSURE = "Unsure"


class RedactionStatus(StrEnum):
    NOT_REQUIRED = "Not Required"
    REQUIRED = "Required"
    PENDING = "Pending"
    COMPLETED = "Completed"


class DataMode(StrEnum):
    SYNTHETIC_DEMO = "synthetic_demo"


class HRDocumentMetadata(BaseModel):
    """Tenant-neutral HR document metadata and content."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    document_title: NonBlankString
    document_type: DocumentType
    department: Department
    summary_purpose: NonBlankString
    language: Language
    version: NonBlankString
    effective_date: date
    content_owner: NonBlankString
    approval_status: ApprovalStatus
    approved_for_rag: RagApprovalStatus
    document_status: DocumentStatus
    access_level: AccessLevel
    contains_personal_data: DataDeclaration
    contains_confidential_data: DataDeclaration
    synthetic: bool
    official_company_document: bool
    data_mode: DataMode
    document_content: NonBlankString

    last_review_date: date | None = None
    next_review_date: date | None = None
    approved_by: NonBlankString | None = None
    permitted_roles: list[NonBlankString] | None = None
    restricted_roles: list[NonBlankString] | None = None
    redaction_status: RedactionStatus | None = None
    section_headings: list[NonBlankString] | None = None
    related_documents: list[NonBlankString] | None = None
    keywords: list[NonBlankString] | None = None
    reviewer_notes: NonBlankString | None = None
    document_type_other: NonBlankString | None = None
    department_other: NonBlankString | None = None
    language_other: NonBlankString | None = None

    @field_validator(
        "permitted_roles",
        "restricted_roles",
        "section_headings",
        "related_documents",
        "keywords",
        mode="after",
    )
    @classmethod
    def reject_empty_lists(cls, value: list[str] | None) -> list[str] | None:
        """Treat explicitly supplied empty collections as absent metadata."""
        return value or None
