"""Synthetic HR corpus and question set for the RAG evaluation baseline.

The corpus is deliberately small, synthetic, and tenant-neutral. It carries no
real company, person, or policy: every document is demonstration content that
exists only so the retrieval and grounding layers can be measured.

Extend the baseline by appending to ``HR_EVALUATION_DOCUMENTS`` and
``HR_EVALUATION_CASES``. Nothing else needs to change.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.schemas.hr_documents import HRDocumentMetadata

LEAVE_DOCUMENT_KEY = "HR-EVAL-LEAVE-001"
REMOTE_DOCUMENT_KEY = "HR-EVAL-REMOTE-002"
EXPENSE_DOCUMENT_KEY = "HR-EVAL-EXPENSE-003"
PROBATION_DOCUMENT_KEY = "HR-EVAL-PROBATION-004"


@dataclass(frozen=True, slots=True)
class HREvaluationDocument:
    """One synthetic HR document published into the evaluation tenant."""

    document_key: str
    metadata: HRDocumentMetadata


@dataclass(frozen=True, slots=True)
class HREvaluationCase:
    """One evaluation question and what the pipeline is expected to do with it."""

    case_id: str
    question: str
    expects_evidence: bool
    expected_document_key: str | None = None
    expected_evidence: str | None = None

    def __post_init__(self) -> None:
        if self.expects_evidence and self.expected_document_key is None:
            raise ValueError(
                f"{self.case_id}: a case expecting evidence needs an expected document key."
            )
        if not self.expects_evidence and self.expected_document_key is not None:
            raise ValueError(
                f"{self.case_id}: a case expecting no evidence must not name a document."
            )


def _document(
    *,
    document_key: str,
    title: str,
    summary: str,
    content: str,
    keywords: list[str],
) -> HREvaluationDocument:
    """Build one approved, RAG-eligible synthetic document."""
    return HREvaluationDocument(
        document_key=document_key,
        metadata=HRDocumentMetadata.model_validate(
            {
                "document_title": title,
                "document_type": "Policy",
                "department": "Human Resources",
                "summary_purpose": summary,
                "language": "English",
                "version": "1.0",
                "effective_date": date(2026, 1, 1),
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
                "approved_by": "Synthetic Reviewer",
                "keywords": keywords,
                "document_content": content,
            }
        ),
    )


HR_EVALUATION_DOCUMENTS: tuple[HREvaluationDocument, ...] = (
    _document(
        document_key=LEAVE_DOCUMENT_KEY,
        title="Synthetic Annual Leave Policy",
        summary="Explains synthetic annual leave entitlement and how leave is requested.",
        keywords=["leave", "annual leave", "entitlement"],
        content=(
            "## Entitlement\n\n"
            "Every full-time employee receives twenty-one working days of paid annual "
            "leave in each calendar year. Part-time employees receive a pro-rated "
            "entitlement based on contracted hours.\n\n"
            "## Requesting Leave\n\n"
            "Annual leave must be requested at least ten working days before the first "
            "day of absence. The reporting manager approves or declines the request "
            "within three working days.\n\n"
            "## Carry Over\n\n"
            "A maximum of five unused annual leave days may be carried into the "
            "following calendar year. Carried days expire on the last day of March."
        ),
    ),
    _document(
        document_key=REMOTE_DOCUMENT_KEY,
        title="Synthetic Remote Working Policy",
        summary="Explains synthetic remote working eligibility, core hours, and equipment.",
        keywords=["remote work", "hybrid", "core hours"],
        content=(
            "## Eligibility\n\n"
            "Employees who have completed probation may work remotely for up to three "
            "days each week. Remote working is agreed in writing with the reporting "
            "manager.\n\n"
            "## Core Hours\n\n"
            "Remote employees remain reachable during the core hours of ten in the "
            "morning until four in the afternoon in their contracted time zone.\n\n"
            "## Equipment\n\n"
            "The company supplies a laptop and a headset for remote work. Employees "
            "are responsible for a reliable internet connection."
        ),
    ),
    _document(
        document_key=EXPENSE_DOCUMENT_KEY,
        title="Synthetic Expense Reimbursement Policy",
        summary="Explains how synthetic business expenses are claimed and approved.",
        keywords=["expenses", "reimbursement", "receipts"],
        content=(
            "## Claim Deadline\n\n"
            "Business expense claims must be submitted within thirty calendar days of "
            "the date the expense was incurred. Claims submitted after that period are "
            "declined.\n\n"
            "## Receipts\n\n"
            "Every claim requires an itemised receipt. Claims without a receipt are "
            "returned to the employee for correction.\n\n"
            "## Approval Limits\n\n"
            "A reporting manager approves claims up to five hundred units of currency. "
            "Larger claims require a department head approval as well."
        ),
    ),
    _document(
        document_key=PROBATION_DOCUMENT_KEY,
        title="Synthetic Probation and Confirmation Procedure",
        summary="Explains the synthetic probation period and the confirmation review.",
        keywords=["probation", "confirmation", "review"],
        content=(
            "## Probation Period\n\n"
            "New employees serve a probation period of six months from the start date. "
            "The probation period may be extended once by a maximum of three months.\n\n"
            "## Confirmation Review\n\n"
            "A confirmation review takes place in the final month of probation. The "
            "reporting manager records the outcome and shares it with the employee.\n\n"
            "## Notice During Probation\n\n"
            "During probation either party may end the employment with two weeks of "
            "written notice."
        ),
    ),
)


HR_EVALUATION_CASES: tuple[HREvaluationCase, ...] = (
    # Direct questions using wording close to the source documents.
    HREvaluationCase(
        case_id="EVAL-001",
        question="How many days of paid annual leave does a full-time employee receive?",
        expects_evidence=True,
        expected_document_key=LEAVE_DOCUMENT_KEY,
        expected_evidence="twenty-one working days",
    ),
    HREvaluationCase(
        case_id="EVAL-002",
        question="How many days each week may an employee work remotely?",
        expects_evidence=True,
        expected_document_key=REMOTE_DOCUMENT_KEY,
        expected_evidence="three days each week",
    ),
    HREvaluationCase(
        case_id="EVAL-003",
        question="Within how many days must a business expense claim be submitted?",
        expects_evidence=True,
        expected_document_key=EXPENSE_DOCUMENT_KEY,
        expected_evidence="thirty calendar days",
    ),
    HREvaluationCase(
        case_id="EVAL-004",
        question="How long is the probation period for a new employee?",
        expects_evidence=True,
        expected_document_key=PROBATION_DOCUMENT_KEY,
        expected_evidence="six months",
    ),
    # Paraphrased questions that avoid the source wording.
    HREvaluationCase(
        case_id="EVAL-005",
        question="What is my holiday allowance for the year?",
        expects_evidence=True,
        expected_document_key=LEAVE_DOCUMENT_KEY,
        expected_evidence="annual leave",
    ),
    HREvaluationCase(
        case_id="EVAL-006",
        question="How much notice do I need to give before taking time off?",
        expects_evidence=True,
        expected_document_key=LEAVE_DOCUMENT_KEY,
        expected_evidence="ten working days",
    ),
    HREvaluationCase(
        case_id="EVAL-007",
        question="When do I have to be online if I am working from home?",
        expects_evidence=True,
        expected_document_key=REMOTE_DOCUMENT_KEY,
        expected_evidence="core hours",
    ),
    HREvaluationCase(
        case_id="EVAL-008",
        question="Do I need to keep proof of purchase to get money back?",
        expects_evidence=True,
        expected_document_key=EXPENSE_DOCUMENT_KEY,
        expected_evidence="receipt",
    ),
    HREvaluationCase(
        case_id="EVAL-009",
        question="Can unused vacation days be moved into next year?",
        expects_evidence=True,
        expected_document_key=LEAVE_DOCUMENT_KEY,
        expected_evidence="carried",
    ),
    # Questions with no supporting evidence anywhere in the corpus.
    HREvaluationCase(
        case_id="EVAL-010",
        question="How do I order more paper for the office printer?",
        expects_evidence=False,
    ),
    HREvaluationCase(
        case_id="EVAL-011",
        question="What is the employee share option scheme worth this quarter?",
        expects_evidence=False,
    ),
    HREvaluationCase(
        case_id="EVAL-012",
        question="Which parking bay is reserved for visitors?",
        expects_evidence=False,
    ),
)
