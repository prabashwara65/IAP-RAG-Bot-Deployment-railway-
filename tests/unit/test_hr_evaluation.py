"""Deterministic unit tests for the HR RAG evaluation baseline.

Nothing here touches a database, a network, or a real model.
"""

from collections.abc import Sequence
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.domain.retrieval import SemanticSearchRecord
from app.evaluation.hr_cases import (
    HR_EVALUATION_CASES,
    HR_EVALUATION_DOCUMENTS,
    LEAVE_DOCUMENT_KEY,
    HREvaluationCase,
)
from app.evaluation.metrics import (
    RETRIEVAL_CUTOFFS,
    GroundingIssue,
    RetrievalMatch,
    RetrievalOutcome,
    score_grounding,
    score_retrieval,
    summarize_grounding,
    summarize_retrieval,
)
from app.evaluation.runner import evaluate_hr_rag, render_hr_evaluation_report
from app.providers.deterministic_llm import DeterministicLLMProvider
from app.repositories.embeddings import EmbeddingRepository
from app.services.hr_chunking import chunk_hr_markdown
from app.services.hr_markdown import render_hr_document_markdown
from app.services.hr_rag import HRGroundedAnswer, HRSourceCitation
from app.services.hr_retrieval import HRSemanticRetrievalResult

TENANT_ID = "tenant-evaluation"


class _StubEmbeddingProvider:
    """Embedding provider stub with a fixed vector and no semantics."""

    @property
    def model_name(self) -> str:
        return "stub-embedding-provider"

    @property
    def model_version(self) -> str:
        return "0.0.1"

    @property
    def dimension(self) -> int:
        return 2

    def embed_texts(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        return [(0.1, 0.2) for _ in texts]


def _record(document_key: str) -> SemanticSearchRecord:
    return SemanticSearchRecord(
        chunk_id=uuid4(),
        document_id=uuid4(),
        document_version_id=uuid4(),
        embedding_set_id=uuid4(),
        document_key=document_key,
        document_title=f"Synthetic {document_key}",
        chunk_index=0,
        heading_path=f"Synthetic {document_key} > Section 0",
        content_text=f"Synthetic content for {document_key}.",
        distance=0.1,
    )


def _result(
    document_key: str,
    *,
    content_text: str | None = None,
) -> HRSemanticRetrievalResult:
    record = _record(document_key)
    return HRSemanticRetrievalResult(
        chunk_id=record.chunk_id,
        document_id=record.document_id,
        document_version_id=record.document_version_id,
        embedding_set_id=record.embedding_set_id,
        document_key=record.document_key,
        document_title=record.document_title,
        chunk_index=record.chunk_index,
        heading_path=record.heading_path,
        content_text=content_text or record.content_text,
        distance=record.distance,
    )


EVIDENCE = "twenty-one working days"
EVIDENCE_CHUNK = f"Every full-time employee receives {EVIDENCE} of paid annual leave."
OTHER_CHUNK_OF_SAME_DOCUMENT = "Carried days expire on the last day of March."


def _leave_case(*, expected_evidence: str | None = EVIDENCE) -> HREvaluationCase:
    return HREvaluationCase(
        case_id="EVAL-X",
        question="q",
        expects_evidence=True,
        expected_document_key=LEAVE_DOCUMENT_KEY,
        expected_evidence=expected_evidence,
    )


def _answer(
    *,
    insufficient: bool,
    citation_ids: Sequence[str] = (),
) -> HRGroundedAnswer:
    citations = tuple(
        HRSourceCitation(
            citation_id=citation_id,
            chunk_id=uuid4(),
            document_id=uuid4(),
            document_version_id=uuid4(),
            document_key="HR-EVAL-LEAVE-001",
            document_title="Synthetic Annual Leave Policy",
            chunk_index=0,
            heading_path="Synthetic Annual Leave Policy > Entitlement",
            distance=0.1,
        )
        for citation_id in citation_ids
    )
    return HRGroundedAnswer(
        answer="Synthetic answer.",
        citations=citations,
        insufficient_evidence=insufficient,
    )


# --------------------------------------------------------------------------
# Dataset integrity
# --------------------------------------------------------------------------


def test_the_baseline_holds_between_ten_and_fifteen_cases() -> None:
    assert 10 <= len(HR_EVALUATION_CASES) <= 15


def test_case_identifiers_and_document_keys_are_unique() -> None:
    case_ids = [case.case_id for case in HR_EVALUATION_CASES]
    document_keys = [document.document_key for document in HR_EVALUATION_DOCUMENTS]

    assert len(set(case_ids)) == len(case_ids)
    assert len(set(document_keys)) == len(document_keys)


def test_every_expected_document_key_exists_in_the_corpus() -> None:
    document_keys = {document.document_key for document in HR_EVALUATION_DOCUMENTS}

    for case in HR_EVALUATION_CASES:
        if case.expects_evidence:
            assert case.expected_document_key in document_keys


def test_the_baseline_contains_evidence_and_no_evidence_cases() -> None:
    with_evidence = [case for case in HR_EVALUATION_CASES if case.expects_evidence]
    without_evidence = [
        case for case in HR_EVALUATION_CASES if not case.expects_evidence
    ]

    assert len(with_evidence) >= 6
    assert len(without_evidence) >= 3


def test_every_corpus_document_renders_and_chunks_through_the_real_pipeline() -> None:
    for document in HR_EVALUATION_DOCUMENTS:
        chunks = chunk_hr_markdown(render_hr_document_markdown(document.metadata))

        assert chunks
        assert all(chunk.content_text.strip() for chunk in chunks)


def test_expected_evidence_actually_appears_in_the_expected_document() -> None:
    chunk_text_by_key = {
        document.document_key: "\n".join(
            chunk.content_text
            for chunk in chunk_hr_markdown(
                render_hr_document_markdown(document.metadata)
            )
        )
        for document in HR_EVALUATION_DOCUMENTS
    }

    for case in HR_EVALUATION_CASES:
        if case.expected_evidence is None or case.expected_document_key is None:
            continue
        assert case.expected_evidence in chunk_text_by_key[case.expected_document_key]


def test_the_corpus_contains_no_company_or_person_specific_values() -> None:
    rendered = "\n".join(
        render_hr_document_markdown(document.metadata)
        for document in HR_EVALUATION_DOCUMENTS
    ).casefold()

    assert "apps technologies" not in rendered
    for document in HR_EVALUATION_DOCUMENTS:
        assert document.metadata.synthetic is True
        assert document.metadata.official_company_document is False


def test_an_inconsistent_case_definition_is_rejected() -> None:
    with pytest.raises(ValueError, match="expected document key"):
        HREvaluationCase(case_id="BAD-1", question="q", expects_evidence=True)

    with pytest.raises(ValueError, match="must not name a document"):
        HREvaluationCase(
            case_id="BAD-2",
            question="q",
            expects_evidence=False,
            expected_document_key=LEAVE_DOCUMENT_KEY,
        )


# --------------------------------------------------------------------------
# Retrieval scoring
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("position", "expected_rank"),
    [(0, 1), (1, 2), (2, 3), (4, 5)],
)
def test_the_first_matching_rank_is_recorded(position: int, expected_rank: int) -> None:
    results = [_result("OTHER") for _ in range(5)]
    results[position] = _result(LEAVE_DOCUMENT_KEY, content_text=EVIDENCE_CHUNK)

    outcome = score_retrieval(_leave_case(), results)

    assert outcome.first_document_rank == expected_rank
    assert outcome.first_evidence_rank == expected_rank
    assert outcome.evidence_hit_at(expected_rank) is True
    assert outcome.evidence_hit_at(expected_rank - 1) is False
    assert outcome.match_at(expected_rank) is RetrievalMatch.EVIDENCE


def test_the_right_document_without_the_expected_evidence_is_not_an_evidence_hit() -> None:
    """The central weakness this scoring closes: right document, wrong chunk."""
    results = [_result(LEAVE_DOCUMENT_KEY, content_text=OTHER_CHUNK_OF_SAME_DOCUMENT)]

    outcome = score_retrieval(_leave_case(), results)

    assert outcome.first_document_rank == 1
    assert outcome.first_evidence_rank is None
    assert outcome.document_hit_at(1) is True
    assert outcome.evidence_hit_at(1) is False
    assert all(not outcome.evidence_hit_at(cutoff) for cutoff in RETRIEVAL_CUTOFFS)
    assert outcome.match_at(1) is RetrievalMatch.DOCUMENT_ONLY


def test_the_three_retrieval_states_are_distinguishable() -> None:
    case = _leave_case()

    evidence = score_retrieval(
        case,
        [_result(LEAVE_DOCUMENT_KEY, content_text=EVIDENCE_CHUNK)],
    )
    document_only = score_retrieval(
        case,
        [_result(LEAVE_DOCUMENT_KEY, content_text=OTHER_CHUNK_OF_SAME_DOCUMENT)],
    )
    miss = score_retrieval(case, [_result("OTHER", content_text=EVIDENCE_CHUNK)])

    assert evidence.match_at(5) is RetrievalMatch.EVIDENCE
    assert document_only.match_at(5) is RetrievalMatch.DOCUMENT_ONLY
    assert miss.match_at(5) is RetrievalMatch.MISS
    assert miss.first_document_rank is None
    assert miss.first_evidence_rank is None


def test_the_evidence_chunk_may_rank_below_the_first_document_chunk() -> None:
    results = [
        _result(LEAVE_DOCUMENT_KEY, content_text=OTHER_CHUNK_OF_SAME_DOCUMENT),
        _result("OTHER"),
        _result(LEAVE_DOCUMENT_KEY, content_text=EVIDENCE_CHUNK),
    ]

    outcome = score_retrieval(_leave_case(), results)

    assert outcome.first_document_rank == 1
    assert outcome.first_evidence_rank == 3
    assert outcome.match_at(1) is RetrievalMatch.DOCUMENT_ONLY
    assert outcome.match_at(3) is RetrievalMatch.EVIDENCE


def test_evidence_matching_ignores_letter_case() -> None:
    results = [
        _result(LEAVE_DOCUMENT_KEY, content_text=EVIDENCE_CHUNK.upper()),
    ]

    outcome = score_retrieval(_leave_case(), results)

    assert outcome.first_evidence_rank == 1


def test_a_case_without_expected_evidence_falls_back_to_the_document_rank() -> None:
    results = [_result(LEAVE_DOCUMENT_KEY, content_text=OTHER_CHUNK_OF_SAME_DOCUMENT)]

    outcome = score_retrieval(_leave_case(expected_evidence=None), results)

    assert outcome.first_document_rank == 1
    assert outcome.first_evidence_rank == 1
    assert outcome.match_at(1) is RetrievalMatch.EVIDENCE


def test_only_the_first_occurrence_sets_each_rank() -> None:
    results = [
        _result("OTHER"),
        _result(LEAVE_DOCUMENT_KEY, content_text=EVIDENCE_CHUNK),
        _result(LEAVE_DOCUMENT_KEY, content_text=EVIDENCE_CHUNK),
    ]

    outcome = score_retrieval(_leave_case(), results)

    assert outcome.first_document_rank == 2
    assert outcome.first_evidence_rank == 2


def test_a_missing_expected_document_is_recorded_as_a_miss() -> None:
    outcome = score_retrieval(_leave_case(), [_result("OTHER")] * 5)

    assert outcome.first_document_rank is None
    assert outcome.first_evidence_rank is None
    assert all(not outcome.document_hit_at(cutoff) for cutoff in RETRIEVAL_CUTOFFS)
    assert all(outcome.match_at(cutoff) is RetrievalMatch.MISS for cutoff in RETRIEVAL_CUTOFFS)


def test_the_retrieved_document_keys_are_recorded_in_order() -> None:
    outcome = score_retrieval(
        _leave_case(),
        [_result("A"), _result("B"), _result(LEAVE_DOCUMENT_KEY, content_text=EVIDENCE_CHUNK)],
    )

    assert outcome.retrieved_document_keys == ("A", "B", LEAVE_DOCUMENT_KEY)
    assert outcome.expected_evidence == EVIDENCE


def test_scoring_a_case_without_an_expected_document_is_refused() -> None:
    case = HREvaluationCase(case_id="EVAL-X", question="q", expects_evidence=False)

    with pytest.raises(ValueError, match="expected document key"):
        score_retrieval(case, [])


def test_hit_counts_are_cumulative_across_cutoffs() -> None:
    outcomes = (
        RetrievalOutcome("A", LEAVE_DOCUMENT_KEY, EVIDENCE, (), 1, 1),
        RetrievalOutcome("B", LEAVE_DOCUMENT_KEY, EVIDENCE, (), 3, 3),
        RetrievalOutcome("C", LEAVE_DOCUMENT_KEY, EVIDENCE, (), 5, 5),
        RetrievalOutcome("D", LEAVE_DOCUMENT_KEY, EVIDENCE, (), None, None),
    )

    summary = summarize_retrieval(outcomes)

    assert summary.evaluated_cases == 4
    assert summary.evidence_hits == {1: 1, 3: 2, 5: 3}
    assert summary.document_hits == {1: 1, 3: 2, 5: 3}
    assert summary.evidence_hit_rate(5) == pytest.approx(0.75)
    assert summary.document_hit_rate(5) == pytest.approx(0.75)
    assert summary.evidence_hits[1] <= summary.evidence_hits[3] <= summary.evidence_hits[5]


def test_the_summary_separates_evidence_hits_from_document_only_matches() -> None:
    outcomes = (
        RetrievalOutcome("A", LEAVE_DOCUMENT_KEY, EVIDENCE, (), 1, 1),
        RetrievalOutcome("B", LEAVE_DOCUMENT_KEY, EVIDENCE, (), 1, None),
        RetrievalOutcome("C", LEAVE_DOCUMENT_KEY, EVIDENCE, (), 2, 4),
        RetrievalOutcome("D", LEAVE_DOCUMENT_KEY, EVIDENCE, (), None, None),
    )

    summary = summarize_retrieval(outcomes)

    assert summary.document_hits == {1: 2, 3: 3, 5: 3}
    assert summary.evidence_hits == {1: 1, 3: 1, 5: 2}
    assert summary.document_only(1) == 1
    assert summary.document_only(3) == 2
    assert summary.document_only(5) == 1
    assert all(
        summary.evidence_hits[cutoff] <= summary.document_hits[cutoff]
        for cutoff in RETRIEVAL_CUTOFFS
    )


def test_an_empty_summary_reports_a_zero_rate() -> None:
    summary = summarize_retrieval(())

    assert summary.evaluated_cases == 0
    assert summary.evidence_hit_rate(1) == 0.0
    assert summary.document_hit_rate(1) == 0.0
    assert summary.document_only(1) == 0


# --------------------------------------------------------------------------
# Grounding scoring
# --------------------------------------------------------------------------


def test_a_cited_answer_for_an_evidence_case_passes() -> None:
    case = HREvaluationCase(
        case_id="EVAL-X",
        question="q",
        expects_evidence=True,
        expected_document_key=LEAVE_DOCUMENT_KEY,
    )

    outcome = score_grounding(case, _answer(insufficient=False, citation_ids=["S1"]))

    assert outcome.passed
    assert outcome.citation_ids == ("S1",)


def test_an_uncited_answer_for_an_evidence_case_is_a_citation_failure() -> None:
    case = HREvaluationCase(
        case_id="EVAL-X",
        question="q",
        expects_evidence=True,
        expected_document_key=LEAVE_DOCUMENT_KEY,
    )

    outcome = score_grounding(case, _answer(insufficient=False))

    assert outcome.issues == (GroundingIssue.MISSING_CITATION,)
    assert summarize_grounding([outcome]).citation_checks_passed is False


def test_an_insufficient_answer_for_an_evidence_case_is_recorded_separately() -> None:
    case = HREvaluationCase(
        case_id="EVAL-X",
        question="q",
        expects_evidence=True,
        expected_document_key=LEAVE_DOCUMENT_KEY,
    )

    outcome = score_grounding(case, _answer(insufficient=True))
    summary = summarize_grounding([outcome])

    assert outcome.issues == (GroundingIssue.UNEXPECTED_INSUFFICIENT_EVIDENCE,)
    assert summary.unexpected_insufficient_evidence == 1
    assert summary.citation_checks_passed is True


def test_an_insufficient_answer_for_a_no_evidence_case_passes() -> None:
    case = HREvaluationCase(case_id="EVAL-X", question="q", expects_evidence=False)

    outcome = score_grounding(case, _answer(insufficient=True))

    assert outcome.passed
    assert summarize_grounding([outcome]).insufficient_context_checks_passed is True


@pytest.mark.parametrize(
    "answer",
    [
        _answer(insufficient=False),
        _answer(insufficient=False, citation_ids=["S1"]),
        _answer(insufficient=True, citation_ids=["S1"]),
    ],
)
def test_answering_a_no_evidence_case_is_an_unsupported_answer(
    answer: HRGroundedAnswer,
) -> None:
    case = HREvaluationCase(case_id="EVAL-X", question="q", expects_evidence=False)

    outcome = score_grounding(case, answer)
    summary = summarize_grounding([outcome])

    assert outcome.issues == (GroundingIssue.UNSUPPORTED_ANSWER,)
    assert summary.insufficient_context_checks_passed is False


# --------------------------------------------------------------------------
# Runner
# --------------------------------------------------------------------------


def _evaluation_cases() -> tuple[HREvaluationCase, ...]:
    return (
        HREvaluationCase(
            case_id="EVAL-HIT",
            question="hit question",
            expects_evidence=True,
            expected_document_key=LEAVE_DOCUMENT_KEY,
        ),
        HREvaluationCase(
            case_id="EVAL-MISS",
            question="miss question",
            expects_evidence=True,
            expected_document_key="HR-EVAL-REMOTE-002",
        ),
        HREvaluationCase(
            case_id="EVAL-NONE",
            question="unrelated question",
            expects_evidence=False,
        ),
    )


def test_the_runner_scores_retrieval_and_grounding_for_every_case() -> None:
    hit = (_record(LEAVE_DOCUMENT_KEY),)
    miss = (_record("HR-EVAL-EXPENSE-003"),)
    # The runner cases carry no expected_evidence, so evidence scoring falls
    # back to the document rank.
    repository = Mock(spec=EmbeddingRepository)
    # Two retrievals per evidence case (measurement plus the answer service),
    # one for the no-evidence case, which reaches the answer service only.
    repository.search_similar_chunks.side_effect = [hit, hit, miss, miss, ()]

    report = evaluate_hr_rag(
        tenant_id=TENANT_ID,
        embedding_provider=_StubEmbeddingProvider(),
        llm_provider=DeterministicLLMProvider(),
        repository=repository,
        cases=_evaluation_cases(),
    )

    assert report.total_cases == 3
    assert report.top_k == 5
    assert report.retrieval.evaluated_cases == 2
    assert report.retrieval.evidence_hits == {1: 1, 3: 1, 5: 1}
    assert report.retrieval.document_hits == {1: 1, 3: 1, 5: 1}
    assert [outcome.case_id for outcome in report.retrieval_outcomes] == [
        "EVAL-HIT",
        "EVAL-MISS",
    ]
    assert [outcome.case_id for outcome in report.grounding_outcomes] == [
        "EVAL-HIT",
        "EVAL-MISS",
        "EVAL-NONE",
    ]
    assert report.grounding.citation_checks_passed is True
    assert report.grounding.insufficient_context_checks_passed is True
    assert report.grounding.invalid_citation_references == 0


def test_no_evidence_cases_are_excluded_from_retrieval_scoring() -> None:
    repository = Mock(spec=EmbeddingRepository)
    repository.search_similar_chunks.return_value = ()

    report = evaluate_hr_rag(
        tenant_id=TENANT_ID,
        embedding_provider=_StubEmbeddingProvider(),
        llm_provider=DeterministicLLMProvider(),
        repository=repository,
        cases=(HREvaluationCase("EVAL-NONE", "q", expects_evidence=False),),
    )

    assert report.retrieval.evaluated_cases == 0
    assert report.grounding.evaluated_cases == 1
    assert report.grounding_outcomes[0].insufficient_evidence is True


class _HallucinatingLLM:
    """Language model stub that cites a source it was never given."""

    @property
    def model_name(self) -> str:
        return "hallucinating-stub"

    @property
    def model_version(self) -> str:
        return "0.0.1"

    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        return "Synthetic answer citing nothing real. [S99]"


def test_a_hallucinated_citation_is_reported_not_silently_counted_as_grounded() -> None:
    repository = Mock(spec=EmbeddingRepository)
    repository.search_similar_chunks.return_value = (_record(LEAVE_DOCUMENT_KEY),)

    report = evaluate_hr_rag(
        tenant_id=TENANT_ID,
        embedding_provider=_StubEmbeddingProvider(),
        llm_provider=_HallucinatingLLM(),
        repository=repository,
        cases=(
            HREvaluationCase(
                case_id="EVAL-HALLUCINATION",
                question="q",
                expects_evidence=True,
                expected_document_key=LEAVE_DOCUMENT_KEY,
            ),
        ),
    )

    assert report.grounding.invalid_citation_references == 1
    assert report.grounding.citation_checks_passed is False
    assert report.grounding_outcomes[0].issues == (
        GroundingIssue.INVALID_CITATION_REFERENCE,
    )


def test_the_rendered_report_contains_every_reported_metric() -> None:
    repository = Mock(spec=EmbeddingRepository)
    hit = (_record(LEAVE_DOCUMENT_KEY),)
    repository.search_similar_chunks.side_effect = [hit, hit, hit, hit, ()]

    report = evaluate_hr_rag(
        tenant_id=TENANT_ID,
        embedding_provider=_StubEmbeddingProvider(),
        llm_provider=DeterministicLLMProvider(),
        repository=repository,
        cases=_evaluation_cases(),
    )
    rendered = render_hr_evaluation_report(report)

    assert "HR RAG Evaluation" in rendered
    assert "Cases: 3" in rendered
    assert "top_k: 5" in rendered
    assert "Retrieval (evidence-aware" in rendered
    assert "Retrieval (document-level" in rendered
    assert "Right document, wrong chunk:" in rendered
    assert "structural checks only, not factual correctness" in rendered
    for cutoff in RETRIEVAL_CUTOFFS:
        assert f"Hit@{cutoff}: " in rendered
        assert f"@{cutoff}: " in rendered
    assert "Citation checks: PASS" in rendered
    assert "Invalid citation references: 0" in rendered
    assert "Insufficient-context checks: PASS" in rendered
    assert rendered == render_hr_evaluation_report(report)
