"""Deterministic scoring for the HR RAG evaluation baseline.

Nothing here talks to a database, a provider, or a network. Retrieval and
answer generation are performed by the existing services; these functions only
score what those services returned. Ranking order is taken exactly as
retrieval produced it; no similarity is ever recomputed.

SCOPE: every check in this module is STRUCTURAL. Retrieval scoring asks whether
the expected source text was placed in front of the model, and grounding
scoring asks whether the answer was attributed to supplied sources. Neither
asks whether the answer is factually correct, complete, or well reasoned. A
case can pass every check here and still contain a wrong answer built from the
right evidence. Measuring factual correctness needs human review or a judge
model, and is deliberately out of scope.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from app.evaluation.hr_cases import HREvaluationCase
from app.services.hr_rag import HRGroundedAnswer
from app.services.hr_retrieval import HRSemanticRetrievalResult

RETRIEVAL_CUTOFFS: tuple[int, ...] = (1, 3, 5)


class RetrievalMatch(StrEnum):
    """How closely retrieval matched what a case expected, within one cutoff."""

    EVIDENCE = "document_and_evidence"
    DOCUMENT_ONLY = "document_without_evidence"
    MISS = "no_expected_document"


@dataclass(frozen=True, slots=True)
class RetrievalOutcome:
    """What retrieval returned for one case that expects supporting evidence.

    Two ranks are recorded because they answer different questions. The
    document rank shows whether the right source was reached at all. The
    evidence rank shows whether the specific chunk carrying the expected text
    was reached, which is what actually determines if the answering model could
    have grounded the answer. A multi-chunk document can be retrieved while the
    one chunk holding the answer is missing; only the evidence rank sees that.

    When a case declares no ``expected_evidence`` there is nothing further to
    verify, so the evidence rank equals the document rank.
    """

    case_id: str
    expected_document_key: str
    expected_evidence: str | None
    retrieved_document_keys: tuple[str, ...]
    first_document_rank: int | None
    first_evidence_rank: int | None

    def document_hit_at(self, cutoff: int) -> bool:
        """Report whether the expected document appeared within the first cutoff."""
        return self.first_document_rank is not None and self.first_document_rank <= cutoff

    def evidence_hit_at(self, cutoff: int) -> bool:
        """Report whether a chunk carrying the expected evidence appeared in time."""
        return self.first_evidence_rank is not None and self.first_evidence_rank <= cutoff

    def match_at(self, cutoff: int) -> RetrievalMatch:
        """Classify this case at one cutoff into the three distinguishable states."""
        if self.evidence_hit_at(cutoff):
            return RetrievalMatch.EVIDENCE
        if self.document_hit_at(cutoff):
            return RetrievalMatch.DOCUMENT_ONLY
        return RetrievalMatch.MISS


@dataclass(frozen=True, slots=True)
class RetrievalSummary:
    """Hit@K counts across every case that expects supporting evidence.

    ``evidence_hits`` is the headline measurement. ``document_hits`` is kept
    alongside it for diagnosis: the gap between the two is exactly the set of
    cases where retrieval reached the right document but not the chunk holding
    the answer.
    """

    evaluated_cases: int
    evidence_hits: Mapping[int, int]
    document_hits: Mapping[int, int]

    def evidence_hit_rate(self, cutoff: int) -> float:
        """Return the evidence-aware Hit@cutoff rate, or 0.0 when nothing ran."""
        if self.evaluated_cases == 0:
            return 0.0
        return self.evidence_hits[cutoff] / self.evaluated_cases

    def document_hit_rate(self, cutoff: int) -> float:
        """Return the document-level Hit@cutoff rate, or 0.0 when nothing ran."""
        if self.evaluated_cases == 0:
            return 0.0
        return self.document_hits[cutoff] / self.evaluated_cases

    def document_only(self, cutoff: int) -> int:
        """Count cases that reached the right document but not the right chunk."""
        return self.document_hits[cutoff] - self.evidence_hits[cutoff]


class GroundingIssue(StrEnum):
    """Stable reasons one case failed the grounding expectations."""

    MISSING_CITATION = "missing_citation"
    UNEXPECTED_INSUFFICIENT_EVIDENCE = "unexpected_insufficient_evidence"
    UNSUPPORTED_ANSWER = "unsupported_answer"
    INVALID_CITATION_REFERENCE = "invalid_citation_reference"
    ANSWER_GENERATION_FAILED = "answer_generation_failed"


@dataclass(frozen=True, slots=True)
class GroundingOutcome:
    """How the grounded answer layer behaved for one case."""

    case_id: str
    expects_evidence: bool
    insufficient_evidence: bool
    citation_ids: tuple[str, ...]
    issues: tuple[GroundingIssue, ...]

    @property
    def passed(self) -> bool:
        return not self.issues


@dataclass(frozen=True, slots=True)
class GroundingSummary:
    """Aggregate structural grounding health across every evaluated case.

    These counters describe attribution behaviour only. They say nothing about
    whether the answers were factually right.
    """

    evaluated_cases: int
    citation_failures: int
    invalid_citation_references: int
    insufficient_context_failures: int
    unexpected_insufficient_evidence: int

    @property
    def citation_checks_passed(self) -> bool:
        return self.citation_failures == 0 and self.invalid_citation_references == 0

    @property
    def insufficient_context_checks_passed(self) -> bool:
        return self.insufficient_context_failures == 0


def score_retrieval(
    case: HREvaluationCase,
    results: Sequence[HRSemanticRetrievalResult],
) -> RetrievalOutcome:
    """Score one retrieval case against the chunks actually returned.

    Ranks are one-based and taken from the order the retrieval service
    produced. No similarity is recomputed here; pgvector already ranked these.

    Evidence is detected by a case-insensitive substring search of
    ``expected_evidence`` in a retrieved chunk's ``content_text``. That is a
    structural proxy for "the answer text was actually in front of the model",
    not a semantic judgement about the chunk.
    """
    if case.expected_document_key is None:
        raise ValueError(
            f"{case.case_id}: retrieval scoring needs an expected document key."
        )

    needle = (
        case.expected_evidence.casefold()
        if case.expected_evidence is not None
        else None
    )
    first_document_rank: int | None = None
    first_evidence_rank: int | None = None
    for rank, result in enumerate(results, start=1):
        if result.document_key != case.expected_document_key:
            continue
        if first_document_rank is None:
            first_document_rank = rank
        if needle is None or needle in result.content_text.casefold():
            first_evidence_rank = rank
            break

    return RetrievalOutcome(
        case_id=case.case_id,
        expected_document_key=case.expected_document_key,
        expected_evidence=case.expected_evidence,
        retrieved_document_keys=tuple(result.document_key for result in results),
        first_document_rank=first_document_rank,
        first_evidence_rank=first_evidence_rank,
    )


def summarize_retrieval(
    outcomes: Sequence[RetrievalOutcome],
    *,
    cutoffs: Sequence[int] = RETRIEVAL_CUTOFFS,
) -> RetrievalSummary:
    """Count evidence-level and document-level hits within each cutoff."""
    return RetrievalSummary(
        evaluated_cases=len(outcomes),
        evidence_hits={
            cutoff: sum(1 for outcome in outcomes if outcome.evidence_hit_at(cutoff))
            for cutoff in cutoffs
        },
        document_hits={
            cutoff: sum(1 for outcome in outcomes if outcome.document_hit_at(cutoff))
            for cutoff in cutoffs
        },
    )


def score_grounding(
    case: HREvaluationCase,
    answer: HRGroundedAnswer,
) -> GroundingOutcome:
    """Score one grounded answer's STRUCTURE against what the case expects.

    A case that expects evidence must produce at least one citation. A case
    that expects no evidence must be reported as insufficient with no
    citations, so unsupported HR policy can never be presented as grounded.

    This checks attribution, not truth. An answer that cites a real source and
    still states the wrong entitlement passes every check here. Factual
    correctness is not measured anywhere in this baseline.
    """
    issues: list[GroundingIssue] = []
    if case.expects_evidence:
        if answer.insufficient_evidence:
            issues.append(GroundingIssue.UNEXPECTED_INSUFFICIENT_EVIDENCE)
        elif not answer.citations:
            issues.append(GroundingIssue.MISSING_CITATION)
    elif not answer.insufficient_evidence or answer.citations:
        issues.append(GroundingIssue.UNSUPPORTED_ANSWER)

    return GroundingOutcome(
        case_id=case.case_id,
        expects_evidence=case.expects_evidence,
        insufficient_evidence=answer.insufficient_evidence,
        citation_ids=tuple(citation.citation_id for citation in answer.citations),
        issues=tuple(issues),
    )


def failed_grounding_outcome(
    case: HREvaluationCase,
    issue: GroundingIssue,
) -> GroundingOutcome:
    """Record a case whose answer could not be produced at all."""
    return GroundingOutcome(
        case_id=case.case_id,
        expects_evidence=case.expects_evidence,
        insufficient_evidence=False,
        citation_ids=(),
        issues=(issue,),
    )


def summarize_grounding(outcomes: Sequence[GroundingOutcome]) -> GroundingSummary:
    """Aggregate grounding issues into the reported check results."""

    def _count(*issues: GroundingIssue) -> int:
        return sum(
            1
            for outcome in outcomes
            if any(issue in outcome.issues for issue in issues)
        )

    return GroundingSummary(
        evaluated_cases=len(outcomes),
        citation_failures=_count(
            GroundingIssue.MISSING_CITATION,
            GroundingIssue.ANSWER_GENERATION_FAILED,
        ),
        invalid_citation_references=_count(GroundingIssue.INVALID_CITATION_REFERENCE),
        insufficient_context_failures=_count(GroundingIssue.UNSUPPORTED_ANSWER),
        unexpected_insufficient_evidence=_count(
            GroundingIssue.UNEXPECTED_INSUFFICIENT_EVIDENCE
        ),
    )
