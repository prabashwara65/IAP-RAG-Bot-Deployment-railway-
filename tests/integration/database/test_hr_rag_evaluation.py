"""End-to-end HR RAG evaluation against real PostgreSQL + pgvector.

Deterministic providers are used throughout, so this suite needs no API key and
no network. It proves the evaluation harness measures the real pipeline; it
deliberately does not assert semantic Hit@K numbers, because the deterministic
embedding provider is hash based and carries no meaning. Semantic quality is
measured by scripts/hr_rag_evaluation.py against the real models.
"""

import pytest
from sqlalchemy import Engine

from app.core.database import create_session_factory, session_scope
from app.evaluation.corpus import load_hr_evaluation_corpus
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
    score_retrieval,
)
from app.evaluation.runner import evaluate_hr_rag, render_hr_evaluation_report
from app.providers.deterministic_embeddings import DeterministicEmbeddingProvider
from app.providers.deterministic_llm import DeterministicLLMProvider
from app.repositories.postgres.embeddings import PostgresEmbeddingRepository
from app.services.hr_retrieval import DEFAULT_TOP_K, retrieve_hr_chunks

TENANT_ID = "tenant-evaluation"
DIMENSION = 64
EVIDENCE_CASES = tuple(case for case in HR_EVALUATION_CASES if case.expects_evidence)
NO_EVIDENCE_CASES = tuple(
    case for case in HR_EVALUATION_CASES if not case.expects_evidence
)


def _provider() -> DeterministicEmbeddingProvider:
    return DeterministicEmbeddingProvider(dimension=DIMENSION)


def test_the_evaluation_corpus_is_published_through_the_real_pipeline(
    migrated_engine: Engine,
) -> None:
    factory = create_session_factory(migrated_engine)
    with session_scope(factory) as session:
        corpus = load_hr_evaluation_corpus(
            session,
            tenant_id=TENANT_ID,
            embedding_provider=_provider(),
        )

        assert corpus.document_count == len(HR_EVALUATION_DOCUMENTS)
        assert corpus.chunk_count >= DEFAULT_TOP_K
        assert set(corpus.chunk_texts_by_document_key) == {
            document.document_key for document in HR_EVALUATION_DOCUMENTS
        }
        assert all(corpus.chunk_texts_by_document_key.values())


def test_an_exact_chunk_query_is_retrieved_first_from_its_own_document(
    migrated_engine: Engine,
) -> None:
    """Control case proving retrieval plumbing works without semantic embeddings."""
    provider = _provider()
    factory = create_session_factory(migrated_engine)
    with session_scope(factory) as session:
        corpus = load_hr_evaluation_corpus(
            session,
            tenant_id=TENANT_ID,
            embedding_provider=provider,
        )
        exact_chunk_text = corpus.chunk_texts_by_document_key[LEAVE_DOCUMENT_KEY][0]

        results = retrieve_hr_chunks(
            query=exact_chunk_text,
            tenant_id=TENANT_ID,
            provider=provider,
            repository=PostgresEmbeddingRepository(session),
        )

        assert results
        assert results[0].document_key == LEAVE_DOCUMENT_KEY
        assert results[0].content_text == exact_chunk_text
        assert results[0].distance == pytest.approx(0.0, abs=1e-6)


def test_the_evaluation_harness_scores_every_case_against_the_live_services(
    migrated_engine: Engine,
) -> None:
    provider = _provider()
    factory = create_session_factory(migrated_engine)
    with session_scope(factory) as session:
        load_hr_evaluation_corpus(
            session,
            tenant_id=TENANT_ID,
            embedding_provider=provider,
        )

        report = evaluate_hr_rag(
            tenant_id=TENANT_ID,
            embedding_provider=provider,
            llm_provider=DeterministicLLMProvider(),
            repository=PostgresEmbeddingRepository(session),
        )

        assert report.total_cases == len(HR_EVALUATION_CASES)
        assert report.top_k == DEFAULT_TOP_K
        assert report.retrieval.evaluated_cases == len(EVIDENCE_CASES)
        assert report.grounding.evaluated_cases == len(HR_EVALUATION_CASES)

        evidence_hits = [
            report.retrieval.evidence_hits[cutoff] for cutoff in RETRIEVAL_CUTOFFS
        ]
        document_hits = [
            report.retrieval.document_hits[cutoff] for cutoff in RETRIEVAL_CUTOFFS
        ]
        assert evidence_hits == sorted(evidence_hits)
        assert document_hits == sorted(document_hits)
        assert all(0 <= hit <= len(EVIDENCE_CASES) for hit in evidence_hits)
        # Evidence-aware scoring can never exceed document-level scoring.
        assert all(
            report.retrieval.evidence_hits[cutoff]
            <= report.retrieval.document_hits[cutoff]
            for cutoff in RETRIEVAL_CUTOFFS
        )
        assert all(report.retrieval.document_only(cutoff) >= 0 for cutoff in RETRIEVAL_CUTOFFS)
        for outcome in report.retrieval_outcomes:
            for rank in (outcome.first_document_rank, outcome.first_evidence_rank):
                assert rank is None or 1 <= rank <= DEFAULT_TOP_K
            if outcome.first_evidence_rank is not None:
                assert outcome.first_document_rank is not None
                assert outcome.first_document_rank <= outcome.first_evidence_rank
        assert render_hr_evaluation_report(report)


def test_the_citation_validator_holds_across_the_whole_corpus(
    migrated_engine: Engine,
) -> None:
    provider = _provider()
    factory = create_session_factory(migrated_engine)
    with session_scope(factory) as session:
        load_hr_evaluation_corpus(
            session,
            tenant_id=TENANT_ID,
            embedding_provider=provider,
        )

        report = evaluate_hr_rag(
            tenant_id=TENANT_ID,
            embedding_provider=provider,
            llm_provider=DeterministicLLMProvider(),
            repository=PostgresEmbeddingRepository(session),
        )

        assert report.grounding.invalid_citation_references == 0
        for outcome in report.grounding_outcomes:
            assert all(
                citation_id.startswith("S") for citation_id in outcome.citation_ids
            )


def test_a_tenant_without_any_corpus_declines_to_answer(
    migrated_engine: Engine,
) -> None:
    provider = _provider()
    factory = create_session_factory(migrated_engine)
    with session_scope(factory) as session:
        load_hr_evaluation_corpus(
            session,
            tenant_id=TENANT_ID,
            embedding_provider=provider,
        )

        report = evaluate_hr_rag(
            tenant_id="tenant-without-any-hr-documents",
            embedding_provider=provider,
            llm_provider=DeterministicLLMProvider(),
            repository=PostgresEmbeddingRepository(session),
        )

        assert report.retrieval.evidence_hits[DEFAULT_TOP_K] == 0
        assert report.retrieval.document_hits[DEFAULT_TOP_K] == 0
        assert report.grounding.insufficient_context_checks_passed is True
        assert all(
            outcome.insufficient_evidence and not outcome.citation_ids
            for outcome in report.grounding_outcomes
        )


def test_retrieval_returns_top_k_even_for_an_unrelated_question(
    migrated_engine: Engine,
) -> None:
    """Documents a real limitation: retrieval applies no relevance floor.

    Every question that reaches a populated tenant receives ``top_k`` chunks,
    however far away they are, so "no relevant evidence" can only be decided by
    the answering model rather than by retrieval.
    """
    provider = _provider()
    factory = create_session_factory(migrated_engine)
    with session_scope(factory) as session:
        load_hr_evaluation_corpus(
            session,
            tenant_id=TENANT_ID,
            embedding_provider=provider,
        )

        results = retrieve_hr_chunks(
            query=NO_EVIDENCE_CASES[0].question,
            tenant_id=TENANT_ID,
            provider=provider,
            repository=PostgresEmbeddingRepository(session),
        )

        assert len(results) == DEFAULT_TOP_K
        assert all(result.distance >= 0.0 for result in results)


def test_the_echo_model_cannot_decline_so_no_evidence_cases_are_flagged(
    migrated_engine: Engine,
) -> None:
    """Documents the deterministic provider's ceiling for this measurement.

    ``DeterministicLLMProvider`` always cites the first supplied source, so it
    can never produce the insufficient-evidence reply. Every no-evidence case is
    therefore reported as an unsupported answer here. Whether a real model
    declines is measured by scripts/hr_rag_evaluation.py.
    """
    provider = _provider()
    factory = create_session_factory(migrated_engine)
    with session_scope(factory) as session:
        load_hr_evaluation_corpus(
            session,
            tenant_id=TENANT_ID,
            embedding_provider=provider,
        )

        report = evaluate_hr_rag(
            tenant_id=TENANT_ID,
            embedding_provider=provider,
            llm_provider=DeterministicLLMProvider(),
            repository=PostgresEmbeddingRepository(session),
        )

        assert report.grounding.insufficient_context_failures == len(NO_EVIDENCE_CASES)
        flagged = [
            outcome.case_id
            for outcome in report.grounding_outcomes
            if GroundingIssue.UNSUPPORTED_ANSWER in outcome.issues
        ]
        assert flagged == [case.case_id for case in NO_EVIDENCE_CASES]


def test_evidence_aware_scoring_separates_the_right_chunk_from_the_right_document(
    migrated_engine: Engine,
) -> None:
    """A whole document being retrieved is not proof the answer chunk was."""
    provider = _provider()
    factory = create_session_factory(migrated_engine)
    with session_scope(factory) as session:
        corpus = load_hr_evaluation_corpus(
            session,
            tenant_id=TENANT_ID,
            embedding_provider=provider,
        )
        leave_chunks = corpus.chunk_texts_by_document_key[LEAVE_DOCUMENT_KEY]
        entitlement_chunk = next(
            text for text in leave_chunks if "twenty-one working days" in text
        )
        other_chunk = next(
            text for text in leave_chunks if "twenty-one working days" not in text
        )

        # Querying a non-entitlement chunk verbatim retrieves the right document
        # at rank one, while the chunk carrying the expected evidence is absent.
        results = retrieve_hr_chunks(
            query=other_chunk,
            tenant_id=TENANT_ID,
            provider=provider,
            repository=PostgresEmbeddingRepository(session),
        )
        case = HREvaluationCase(
            case_id="EVAL-EVIDENCE-CONTROL",
            question=other_chunk,
            expects_evidence=True,
            expected_document_key=LEAVE_DOCUMENT_KEY,
            expected_evidence="twenty-one working days",
        )

        outcome = score_retrieval(case, results)

        assert results[0].document_key == LEAVE_DOCUMENT_KEY
        assert outcome.first_document_rank == 1
        assert outcome.match_at(1) is RetrievalMatch.DOCUMENT_ONLY
        assert not outcome.evidence_hit_at(1)
        assert entitlement_chunk not in [result.content_text for result in results[:1]]
