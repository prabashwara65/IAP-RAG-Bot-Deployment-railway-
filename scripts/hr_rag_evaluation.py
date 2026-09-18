"""Manual HR RAG evaluation against the real Gemini models.

This script is never run by pytest. It seeds the synthetic evaluation corpus
into the disposable test database, measures the existing retrieval and grounded
answer services, prints the summary, and then rolls back so no rows remain.

Requires:
    GEMINI_API_KEY      real credential, read from the environment or .env
    TEST_DATABASE_URL   disposable PostgreSQL + pgvector database, already migrated

Usage:
    TEST_DATABASE_URL=postgresql+psycopg://... python -m scripts.hr_rag_evaluation

Cost is roughly two short query embeddings per case plus one small completion
per case.
"""

from __future__ import annotations

import os
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.evaluation.corpus import load_hr_evaluation_corpus
from app.evaluation.metrics import RetrievalMatch
from app.evaluation.runner import (
    HREvaluationReport,
    evaluate_hr_rag,
    render_hr_evaluation_report,
)
from app.providers.gemini_embeddings import (
    GeminiEmbeddingError,
    gemini_embedding_provider_from_settings,
)
from app.providers.gemini_llm import GeminiLLMError, gemini_llm_provider_from_settings
from app.repositories.postgres.embeddings import PostgresEmbeddingRepository


def _print_retrieval_misses(report: HREvaluationReport) -> None:
    """List every case whose expected evidence did not reach the model.

    Evidence-aware retrieval is the headline metric, so a case counts as a miss
    unless a chunk carrying the expected evidence was retrieved. The two failure
    shapes are separated because they need different fixes: a wrong chunk points
    at chunking or ranking, a wrong document points at the embedding.
    """
    cutoff = report.top_k
    wrong_chunk = [
        outcome
        for outcome in report.retrieval_outcomes
        if outcome.match_at(cutoff) is RetrievalMatch.DOCUMENT_ONLY
    ]
    wrong_document = [
        outcome
        for outcome in report.retrieval_outcomes
        if outcome.match_at(cutoff) is RetrievalMatch.MISS
    ]

    print(f"Evidence misses within top_k={cutoff}: {len(wrong_chunk) + len(wrong_document)}")
    print(f"  right document, wrong chunk: {len(wrong_chunk)}")
    for outcome in wrong_chunk:
        print(
            f"    {outcome.case_id}: {outcome.expected_document_key} "
            f"at rank {outcome.first_document_rank}, "
            f"but no retrieved chunk contained {outcome.expected_evidence!r}"
        )
    print(f"  expected document not retrieved: {len(wrong_document)}")
    for outcome in wrong_document:
        print(
            f"    {outcome.case_id}: expected {outcome.expected_document_key}, "
            f"got {list(outcome.retrieved_document_keys)}"
        )


def main() -> int:
    """Seed, evaluate, print, and roll back."""
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        print(
            "TEST_DATABASE_URL is required; the evaluation never writes to a real database."
        )
        return 2

    settings = get_settings()
    try:
        embedding_provider = gemini_embedding_provider_from_settings(settings)
        llm_provider = gemini_llm_provider_from_settings(settings)
    except (GeminiEmbeddingError, GeminiLLMError) as error:
        print(f"CONFIGURATION FAILED [{error.code.value}]: {error}")
        return 2

    print(
        f"embedding={embedding_provider.model_version} "
        f"dimension={embedding_provider.dimension} llm={llm_provider.model_version}"
    )

    tenant_id = f"evaluation-{uuid4()}"
    engine = create_engine(database_url, pool_pre_ping=True, hide_parameters=True)
    session = Session(engine)
    try:
        corpus = load_hr_evaluation_corpus(
            session,
            tenant_id=tenant_id,
            embedding_provider=embedding_provider,
        )
        print(f"documents={corpus.document_count} chunks={corpus.chunk_count}")

        report = evaluate_hr_rag(
            tenant_id=tenant_id,
            embedding_provider=embedding_provider,
            llm_provider=llm_provider,
            repository=PostgresEmbeddingRepository(session),
        )
        print()
        print(render_hr_evaluation_report(report))
        print()
        _print_retrieval_misses(report)
    finally:
        session.rollback()
        session.close()
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
