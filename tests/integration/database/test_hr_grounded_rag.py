"""End-to-end grounded RAG over real PostgreSQL + pgvector, with no external services."""

from datetime import UTC, datetime
from hashlib import sha256

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.core.database import create_session_factory, session_scope
from app.domain.documents import DocumentVersionStatus, EmbeddingSetStatus
from app.models.documents import (
    ChunkModel,
    DocumentModel,
    DocumentVersionModel,
    EmbeddingSetModel,
)
from app.providers.deterministic_embeddings import DeterministicEmbeddingProvider
from app.providers.deterministic_llm import DeterministicLLMProvider
from app.repositories.postgres.embeddings import PostgresEmbeddingRepository
from app.services.hr_chunking import HRDocumentChunk
from app.services.hr_embedding import embed_hr_chunks, persist_hr_chunk_embeddings
from app.services.hr_rag import (
    INSUFFICIENT_EVIDENCE_ANSWER,
    answer_hr_question,
)

TENANT_ID = "tenant-alpha"
DIMENSION = 8
DOCUMENT_TITLE = "Synthetic Leave Policy"
DOCUMENT_KEY = "HR-SYNTHETIC-LEAVE-001"
CONTENTS = (
    "Synthetic annual leave entitlement details for demonstration.",
    "Synthetic remote working arrangement details for demonstration.",
    "Synthetic expense reimbursement details for demonstration.",
)


class _CountingLLMProvider:
    """Deterministic provider wrapper that records how often it was called."""

    def __init__(self) -> None:
        self._inner = DeterministicLLMProvider()
        self.call_count = 0

    @property
    def model_name(self) -> str:
        return self._inner.model_name

    @property
    def model_version(self) -> str:
        return self._inner.model_version

    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        self.call_count += 1
        return self._inner.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )


def _seed_active_hr_document(
    session: Session,
    provider: DeterministicEmbeddingProvider,
) -> list[ChunkModel]:
    """Store one active HR document version with embedded, searchable chunks."""
    now = datetime.now(UTC)
    document = DocumentModel(
        tenant_id=TENANT_ID,
        document_key=DOCUMENT_KEY,
        title=DOCUMENT_TITLE,
    )
    session.add(document)
    session.flush()

    version = DocumentVersionModel(
        document_id=document.id,
        version_label="1.0",
        status=DocumentVersionStatus.ACTIVE.value,
        content_hash="content-hash-grounded-rag",
        approved_at=now,
        activated_at=now,
    )
    session.add(version)
    session.flush()

    chunk_models = [
        ChunkModel(
            document_version_id=version.id,
            chunk_index=index,
            heading_path=f"{DOCUMENT_TITLE} > Section {index}",
            content_text=content,
            content_hash=sha256(content.encode("utf-8")).hexdigest(),
        )
        for index, content in enumerate(CONTENTS)
    ]
    embedding_set = EmbeddingSetModel(
        document_version_id=version.id,
        model_name=provider.model_name,
        model_version=provider.model_version,
        dimension=provider.dimension,
        status=EmbeddingSetStatus.ACTIVE.value,
    )
    session.add_all([*chunk_models, embedding_set])
    session.flush()

    chunks = tuple(
        HRDocumentChunk(
            chunk_index=model.chunk_index,
            heading_path=model.heading_path,
            content_text=model.content_text,
            content_hash=model.content_hash,
        )
        for model in chunk_models
    )
    persist_hr_chunk_embeddings(
        PostgresEmbeddingRepository(session),
        embedding_set_id=embedding_set.id,
        embeddings=embed_hr_chunks(chunks, provider),
        chunk_ids={model.chunk_index: model.id for model in chunk_models},
    )
    session.flush()
    return chunk_models


def test_stored_chunks_produce_a_grounded_answer_with_a_valid_citation(
    migrated_engine: Engine,
) -> None:
    embedding_provider = DeterministicEmbeddingProvider(dimension=DIMENSION)
    llm_provider = _CountingLLMProvider()
    factory = create_session_factory(migrated_engine)
    with session_scope(factory) as session:
        chunk_models = _seed_active_hr_document(session, embedding_provider)

        answer = answer_hr_question(
            question=CONTENTS[1],
            tenant_id=TENANT_ID,
            embedding_provider=embedding_provider,
            llm_provider=llm_provider,
            repository=PostgresEmbeddingRepository(session),
            top_k=3,
        )

        assert llm_provider.call_count == 1
        assert answer.insufficient_evidence is False
        assert answer.answer
        assert [citation.citation_id for citation in answer.citations] == ["S1"]

        citation = answer.citations[0]
        assert citation.chunk_id == chunk_models[1].id
        assert citation.document_key == DOCUMENT_KEY
        assert citation.document_title == DOCUMENT_TITLE
        assert citation.chunk_index == chunk_models[1].chunk_index
        assert citation.heading_path == chunk_models[1].heading_path
        assert citation.distance == pytest.approx(0.0, abs=1e-6)
        assert f"[{citation.citation_id}]" in answer.answer


def test_the_same_question_produces_an_identical_grounded_answer(
    migrated_engine: Engine,
) -> None:
    embedding_provider = DeterministicEmbeddingProvider(dimension=DIMENSION)
    factory = create_session_factory(migrated_engine)
    with session_scope(factory) as session:
        _seed_active_hr_document(session, embedding_provider)
        repository = PostgresEmbeddingRepository(session)

        answers = [
            answer_hr_question(
                question=CONTENTS[0],
                tenant_id=TENANT_ID,
                embedding_provider=embedding_provider,
                llm_provider=DeterministicLLMProvider(),
                repository=repository,
            )
            for _ in range(2)
        ]

        assert answers[0] == answers[1]


def test_a_tenant_without_approved_evidence_never_reaches_the_model(
    migrated_engine: Engine,
) -> None:
    embedding_provider = DeterministicEmbeddingProvider(dimension=DIMENSION)
    llm_provider = _CountingLLMProvider()
    factory = create_session_factory(migrated_engine)
    with session_scope(factory) as session:
        _seed_active_hr_document(session, embedding_provider)

        answer = answer_hr_question(
            question=CONTENTS[0],
            tenant_id="tenant-without-documents",
            embedding_provider=embedding_provider,
            llm_provider=llm_provider,
            repository=PostgresEmbeddingRepository(session),
        )

        assert llm_provider.call_count == 0
        assert answer.insufficient_evidence is True
        assert answer.answer == INSUFFICIENT_EVIDENCE_ANSWER
        assert answer.citations == ()
