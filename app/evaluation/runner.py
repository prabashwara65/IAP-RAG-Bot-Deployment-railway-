"""Run the HR RAG evaluation baseline through the existing services.

Retrieval and answer generation are measured separately, each through its own
public entry point, so a retrieval regression is never hidden behind a good
answer. No similarity, ranking, or prompting logic is reimplemented here.

Every measurement produced here is STRUCTURAL: whether the expected evidence
reached the model, and whether the answer was attributed to supplied sources.
Factual answer correctness is not measured.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.core.config import get_settings
from app.evaluation.hr_cases import HR_EVALUATION_CASES, HREvaluationCase
from app.evaluation.metrics import (
    RETRIEVAL_CUTOFFS,
    GroundingIssue,
    GroundingOutcome,
    GroundingSummary,
    RetrievalOutcome,
    RetrievalSummary,
    failed_grounding_outcome,
    score_grounding,
    score_retrieval,
    summarize_grounding,
    summarize_retrieval,
)
from app.providers.embeddings import EmbeddingProvider
from app.providers.llm import LLMProvider
from app.repositories.embeddings import EmbeddingRepository
from app.services.hr_rag import HRRAGError, HRRAGErrorCode, answer_hr_question
from app.services.hr_retrieval import DEFAULT_TOP_K, retrieve_hr_chunks


@dataclass(frozen=True, slots=True)
class HREvaluationReport:
    """The full evaluation result for one corpus and question set."""

    total_cases: int
    top_k: int
    retrieval: RetrievalSummary
    retrieval_outcomes: tuple[RetrievalOutcome, ...]
    grounding: GroundingSummary
    grounding_outcomes: tuple[GroundingOutcome, ...]


def evaluate_hr_rag(
    *,
    tenant_id: str,
    embedding_provider: EmbeddingProvider,
    llm_provider: LLMProvider,
    repository: EmbeddingRepository,
    cases: Sequence[HREvaluationCase] = HR_EVALUATION_CASES,
    top_k: int = DEFAULT_TOP_K,
) -> HREvaluationReport:
    """Score every case against the live retrieval and grounded answer services.

    Each case runs retrieval once for the Hit@K measurement and then runs the
    grounded answer service, which performs its own retrieval. That costs one
    extra query embedding per case and is deliberate: measuring the two layers
    through their real entry points keeps production code untouched.
    """
    retrieval_outcomes: list[RetrievalOutcome] = []
    grounding_outcomes: list[GroundingOutcome] = []

    for case in cases:
        if case.expects_evidence:
            results = retrieve_hr_chunks(
                query=case.question,
                tenant_id=tenant_id,
                provider=embedding_provider,
                repository=repository,
                top_k=top_k,
                search_mode=(
                    "hybrid" if get_settings().use_hybrid_search else "vector"
                ),
            )
            retrieval_outcomes.append(score_retrieval(case, results))

        try:
            answer = answer_hr_question(
                question=case.question,
                tenant_id=tenant_id,
                embedding_provider=embedding_provider,
                llm_provider=llm_provider,
                repository=repository,
                top_k=top_k,
            )
        except HRRAGError as error:
            issue = (
                GroundingIssue.INVALID_CITATION_REFERENCE
                if error.code is HRRAGErrorCode.UNKNOWN_CITATION_ID
                else GroundingIssue.ANSWER_GENERATION_FAILED
            )
            grounding_outcomes.append(failed_grounding_outcome(case, issue))
            continue

        grounding_outcomes.append(score_grounding(case, answer))

    return HREvaluationReport(
        total_cases=len(cases),
        top_k=top_k,
        retrieval=summarize_retrieval(retrieval_outcomes),
        retrieval_outcomes=tuple(retrieval_outcomes),
        grounding=summarize_grounding(grounding_outcomes),
        grounding_outcomes=tuple(grounding_outcomes),
    )


def _check(passed: bool) -> str:
    return "PASS" if passed else "FAIL"


def render_hr_evaluation_report(report: HREvaluationReport) -> str:
    """Render one deterministic, human-readable evaluation summary."""
    evaluated = report.retrieval.evaluated_cases
    lines = [
        "HR RAG Evaluation",
        "",
        f"Cases: {report.total_cases}",
        f"top_k: {report.top_k}",
        "",
        "Retrieval (evidence-aware, the expected chunk was retrieved):",
    ]
    lines.extend(
        f"Hit@{cutoff}: {report.retrieval.evidence_hits[cutoff]}/{evaluated}"
        for cutoff in RETRIEVAL_CUTOFFS
    )

    lines.extend(("", "Retrieval (document-level, any chunk of the document):"))
    lines.extend(
        f"Hit@{cutoff}: {report.retrieval.document_hits[cutoff]}/{evaluated}"
        for cutoff in RETRIEVAL_CUTOFFS
    )

    lines.extend(("", "Right document, wrong chunk:"))
    lines.extend(
        f"@{cutoff}: {report.retrieval.document_only(cutoff)}"
        for cutoff in RETRIEVAL_CUTOFFS
    )

    lines.extend(
        (
            "",
            "Grounding (structural checks only, not factual correctness):",
            f"Citation checks: {_check(report.grounding.citation_checks_passed)}",
            f"Invalid citation references: {report.grounding.invalid_citation_references}",
            "Insufficient-context checks: "
            f"{_check(report.grounding.insufficient_context_checks_passed)}",
            "Unexpected insufficient evidence: "
            f"{report.grounding.unexpected_insufficient_evidence}",
        )
    )
    return "\n".join(lines)
