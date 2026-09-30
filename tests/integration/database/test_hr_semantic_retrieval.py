"""PostgreSQL/pgvector integration tests for HR semantic retrieval."""

from collections.abc import Sequence
from datetime import UTC, datetime
from hashlib import sha256

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.core.database import create_session_factory, session_scope
from app.domain.documents import DocumentVersionStatus, EmbeddingSetStatus
from app.domain.retrieval import SemanticSearchRecord
from app.models.documents import (
    ChunkModel,
    DocumentModel,
    DocumentVersionModel,
    EmbeddingSetModel,
)
from app.providers.deterministic_embeddings import DeterministicEmbeddingProvider
from app.repositories.postgres.embeddings import PostgresEmbeddingRepository
from app.services.hr_chunking import HRDocumentChunk
from app.services.hr_embedding import embed_hr_chunks, persist_hr_chunk_embeddings
from app.services.hr_retrieval import retrieve_hr_chunks

MODEL_NAME = "synthetic-retrieval-model"
MODEL_VERSION = "1.0.0"
DIMENSION = 3
TENANT_ALPHA = "tenant-alpha"
TENANT_BETA = "tenant-beta"
QUERY_VECTOR = (1.0, 0.0, 0.0)


def _document(
    session: Session,
    *,
    tenant_id: str,
    document_key: str,
    title: str = "Synthetic HR Document",
    document_type: str = "Other",
) -> DocumentModel:
    model = DocumentModel(
        tenant_id=tenant_id,
        document_key=document_key,
        title=title,
        document_type=document_type,
    )
    session.add(model)
    session.flush()
    return model


def _version(
    session: Session,
    *,
    document: DocumentModel,
    status: DocumentVersionStatus,
) -> DocumentVersionModel:
    now = datetime.now(UTC)
    approved_states = {
        DocumentVersionStatus.APPROVED,
        DocumentVersionStatus.ACTIVE,
    }
    model = DocumentVersionModel(
        document_id=document.id,
        version_label="1.0",
        status=status.value,
        content_hash=f"content-hash-{document.document_key}",
        approved_at=now if status in approved_states else None,
        activated_at=now if status is DocumentVersionStatus.ACTIVE else None,
    )
    session.add(model)
    session.flush()
    return model


def _chunk(
    session: Session,
    *,
    version: DocumentVersionModel,
    chunk_index: int,
    content_text: str,
) -> ChunkModel:
    model = ChunkModel(
        document_version_id=version.id,
        chunk_index=chunk_index,
        heading_path=f"Synthetic HR Document > Section {chunk_index}",
        content_text=content_text,
        content_hash=sha256(content_text.encode("utf-8")).hexdigest(),
    )
    session.add(model)
    session.flush()
    return model


def _embedding_set(
    session: Session,
    *,
    version: DocumentVersionModel,
    model_name: str = MODEL_NAME,
    model_version: str = MODEL_VERSION,
    dimension: int = DIMENSION,
    set_status: EmbeddingSetStatus = EmbeddingSetStatus.ACTIVE,
) -> EmbeddingSetModel:
    model = EmbeddingSetModel(
        document_version_id=version.id,
        model_name=model_name,
        model_version=model_version,
        dimension=dimension,
        status=set_status.value,
    )
    session.add(model)
    session.flush()
    return model


def _searchable_chunk(
    session: Session,
    *,
    tenant_id: str,
    document_key: str,
    status: DocumentVersionStatus,
    values: Sequence[float],
    content_text: str = "Synthetic retrieval chunk.",
    model_name: str = MODEL_NAME,
    model_version: str = MODEL_VERSION,
    set_status: EmbeddingSetStatus = EmbeddingSetStatus.ACTIVE,
    title: str = "Synthetic HR Document",
) -> tuple[ChunkModel, EmbeddingSetModel]:
    """Create one document/version/chunk/embedding-set/embedding combination."""
    document = _document(
        session,
        tenant_id=tenant_id,
        document_key=document_key,
        title=title,
    )
    version = _version(session, document=document, status=status)
    chunk = _chunk(session, version=version, chunk_index=0, content_text=content_text)
    embedding_set = _embedding_set(
        session,
        version=version,
        model_name=model_name,
        model_version=model_version,
        dimension=len(values),
        set_status=set_status,
    )
    PostgresEmbeddingRepository(session).add_embedding(
        chunk_id=chunk.id,
        embedding_set_id=embedding_set.id,
        values=values,
    )
    return chunk, embedding_set


def _build_dataset(session: Session) -> dict[str, ChunkModel]:
    """Build a controlled multi-tenant dataset with matching and excluded rows."""
    repository = PostgresEmbeddingRepository(session)

    # Tenant alpha: one active document holding three ranked chunks.
    ranked_document = _document(
        session,
        tenant_id=TENANT_ALPHA,
        document_key="DOC-ALPHA-RANKED",
        title="Synthetic Leave Policy",
    )
    ranked_version = _version(
        session,
        document=ranked_document,
        status=DocumentVersionStatus.ACTIVE,
    )
    ranked_set = _embedding_set(session, version=ranked_version)
    ranked_vectors = {
        0: (1.0, 0.0, 0.0),
        1: (0.8, 0.6, 0.0),
        2: (0.0, 1.0, 0.0),
    }
    dataset: dict[str, ChunkModel] = {}
    for chunk_index, values in ranked_vectors.items():
        chunk = _chunk(
            session,
            version=ranked_version,
            chunk_index=chunk_index,
            content_text=f"Synthetic ranked chunk {chunk_index}.",
        )
        repository.add_embedding(
            chunk_id=chunk.id,
            embedding_set_id=ranked_set.id,
            values=values,
        )
        dataset[f"ranked_{chunk_index}"] = chunk

    # Tenant alpha: a second active document that ties with ranked chunk 2.
    dataset["tied"], _ = _searchable_chunk(
        session,
        tenant_id=TENANT_ALPHA,
        document_key="DOC-ALPHA-TIED",
        status=DocumentVersionStatus.ACTIVE,
        values=(0.0, 0.0, 1.0),
        content_text="Synthetic orthogonal chunk.",
        title="Synthetic Travel Policy",
    )

    # Tenant alpha: perfect matches that must all be excluded by a filter.
    for status in (
        DocumentVersionStatus.CANDIDATE,
        DocumentVersionStatus.APPROVED,
        DocumentVersionStatus.SUPERSEDED,
        DocumentVersionStatus.ARCHIVED,
        DocumentVersionStatus.FAILED,
    ):
        dataset[f"status_{status.value}"], _ = _searchable_chunk(
            session,
            tenant_id=TENANT_ALPHA,
            document_key=f"DOC-ALPHA-{status.value.upper()}",
            status=status,
            values=QUERY_VECTOR,
        )

    dataset["other_model"], _ = _searchable_chunk(
        session,
        tenant_id=TENANT_ALPHA,
        document_key="DOC-ALPHA-OTHER-MODEL",
        status=DocumentVersionStatus.ACTIVE,
        values=QUERY_VECTOR,
        model_name="another-embedding-model",
    )
    dataset["other_model_version"], _ = _searchable_chunk(
        session,
        tenant_id=TENANT_ALPHA,
        document_key="DOC-ALPHA-OTHER-VERSION",
        status=DocumentVersionStatus.ACTIVE,
        values=QUERY_VECTOR,
        model_version="9.9.9",
    )
    dataset["other_dimension"], _ = _searchable_chunk(
        session,
        tenant_id=TENANT_ALPHA,
        document_key="DOC-ALPHA-OTHER-DIMENSION",
        status=DocumentVersionStatus.ACTIVE,
        values=(1.0, 0.0, 0.0, 0.0),
    )

    # Tenant beta: a perfect match that must never reach tenant alpha.
    dataset["other_tenant"], _ = _searchable_chunk(
        session,
        tenant_id=TENANT_BETA,
        document_key="DOC-BETA-ACTIVE",
        status=DocumentVersionStatus.ACTIVE,
        values=QUERY_VECTOR,
    )

    session.flush()
    return dataset


def _search(
    session: Session,
    *,
    tenant_id: str = TENANT_ALPHA,
    top_k: int = 10,
    document_type: str | None = None,
) -> tuple[SemanticSearchRecord, ...]:
    return PostgresEmbeddingRepository(session).search_similar_chunks(
        tenant_id=tenant_id,
        query_vector=QUERY_VECTOR,
        top_k=top_k,
        model_name=MODEL_NAME,
        model_version=MODEL_VERSION,
        document_type=document_type,
    )


def test_search_can_filter_by_document_type(migrated_engine: Engine) -> None:
    factory = create_session_factory(migrated_engine)
    with session_scope(factory) as session:
        cv_chunk, _ = _searchable_chunk(
            session,
            tenant_id=TENANT_ALPHA,
            document_key="DOC-ALPHA-CV",
            status=DocumentVersionStatus.ACTIVE,
            values=QUERY_VECTOR,
            title="Applicant CV",
        )
        version = session.get(DocumentVersionModel, cv_chunk.document_version_id)
        assert version is not None
        document = session.get(DocumentModel, version.document_id)
        assert document is not None
        document.document_type = "CV"
        session.flush()

        records = _search(session, document_type="CV")

        assert [record.chunk_id for record in records] == [cv_chunk.id]


def test_nearest_chunks_are_returned_first_with_cosine_distances(
    migrated_engine: Engine,
) -> None:
    factory = create_session_factory(migrated_engine)
    with session_scope(factory) as session:
        dataset = _build_dataset(session)

        records = _search(session)

        assert [record.chunk_id for record in records[:2]] == [
            dataset["ranked_0"].id,
            dataset["ranked_1"].id,
        ]
        assert records[0].distance == pytest.approx(0.0, abs=1e-6)
        assert records[1].distance == pytest.approx(0.2, abs=1e-6)
        # Orthogonal unit vectors are cosine distance 1.0; Euclidean would be ~1.414.
        assert records[2].distance == pytest.approx(1.0, abs=1e-6)
        assert records[3].distance == pytest.approx(1.0, abs=1e-6)
        assert [record.distance for record in records] == sorted(
            record.distance for record in records
        )


def test_only_compatible_active_rows_of_the_requested_tenant_are_returned(
    migrated_engine: Engine,
) -> None:
    factory = create_session_factory(migrated_engine)
    with session_scope(factory) as session:
        dataset = _build_dataset(session)

        records = _search(session)

        assert {record.chunk_id for record in records} == {
            dataset["ranked_0"].id,
            dataset["ranked_1"].id,
            dataset["ranked_2"].id,
            dataset["tied"].id,
        }
        excluded = {
            label: chunk.id
            for label, chunk in dataset.items()
            if label.startswith("status_")
            or label in {"other_model", "other_model_version", "other_dimension", "other_tenant"}
        }
        returned = {record.chunk_id for record in records}
        assert [label for label, chunk_id in excluded.items() if chunk_id in returned] == []


def test_tenant_isolation_returns_only_the_other_tenant_rows(
    migrated_engine: Engine,
) -> None:
    factory = create_session_factory(migrated_engine)
    with session_scope(factory) as session:
        dataset = _build_dataset(session)

        records = _search(session, tenant_id=TENANT_BETA)

        assert [record.chunk_id for record in records] == [dataset["other_tenant"].id]
        assert _search(session, tenant_id="tenant-unknown") == ()


def test_top_k_limits_the_returned_matches(migrated_engine: Engine) -> None:
    factory = create_session_factory(migrated_engine)
    with session_scope(factory) as session:
        dataset = _build_dataset(session)

        records = _search(session, top_k=2)

        assert [record.chunk_id for record in records] == [
            dataset["ranked_0"].id,
            dataset["ranked_1"].id,
        ]
        assert len(_search(session, top_k=1)) == 1


def test_equal_distances_use_deterministic_secondary_ordering(
    migrated_engine: Engine,
) -> None:
    factory = create_session_factory(migrated_engine)
    with session_scope(factory) as session:
        _build_dataset(session)

        records = _search(session)
        tied = [
            record
            for record in records
            if record.distance == pytest.approx(1.0, abs=1e-6)
        ]

        assert len(tied) == 2
        assert tied == sorted(
            tied,
            key=lambda record: (
                record.document_id,
                record.document_version_id,
                record.chunk_index,
                record.chunk_id,
            ),
        )
        assert [record.chunk_id for record in _search(session)] == [
            record.chunk_id for record in _search(session)
        ]


def test_returned_metadata_maps_to_the_matching_chunk_document_and_version(
    migrated_engine: Engine,
) -> None:
    factory = create_session_factory(migrated_engine)
    with session_scope(factory) as session:
        dataset = _build_dataset(session)
        expected = dataset["ranked_1"]
        version = session.get(DocumentVersionModel, expected.document_version_id)
        assert version is not None
        document = session.get(DocumentModel, version.document_id)
        assert document is not None

        record = next(
            record for record in _search(session) if record.chunk_id == expected.id
        )

        assert record.document_id == document.id
        assert record.document_version_id == version.id
        assert record.document_key == "DOC-ALPHA-RANKED"
        assert record.document_title == "Synthetic Leave Policy"
        assert record.chunk_index == expected.chunk_index
        assert record.heading_path == expected.heading_path
        assert record.content_text == expected.content_text


def test_retrieval_service_ranks_an_exact_chunk_match_first(
    migrated_engine: Engine,
) -> None:
    provider = DeterministicEmbeddingProvider(dimension=8)
    contents = (
        "Synthetic annual leave entitlement details.",
        "Synthetic remote working arrangement details.",
        "Synthetic expense reimbursement details.",
    )
    factory = create_session_factory(migrated_engine)
    with session_scope(factory) as session:
        document = _document(
            session,
            tenant_id=TENANT_ALPHA,
            document_key="DOC-ALPHA-PROVIDER",
            title="Synthetic Leave Policy",
        )
        version = _version(
            session,
            document=document,
            status=DocumentVersionStatus.ACTIVE,
        )
        chunk_models = [
            _chunk(
                session,
                version=version,
                chunk_index=index,
                content_text=content,
            )
            for index, content in enumerate(contents)
        ]
        embedding_set = _embedding_set(
            session,
            version=version,
            model_name=provider.model_name,
            model_version=provider.model_version,
            dimension=provider.dimension,
        )
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

        results = retrieve_hr_chunks(
            query=contents[1],
            tenant_id=TENANT_ALPHA,
            provider=provider,
            repository=PostgresEmbeddingRepository(session),
            top_k=3,
        )

        assert len(results) == 3
        assert results[0].chunk_id == chunk_models[1].id
        assert results[0].content_text == contents[1]
        assert results[0].distance == pytest.approx(0.0, abs=1e-6)
        assert results[0].distance < results[1].distance
        assert results[0].document_key == "DOC-ALPHA-PROVIDER"


def test_retrieval_service_returns_nothing_for_an_unknown_tenant(
    migrated_engine: Engine,
) -> None:
    provider = DeterministicEmbeddingProvider(dimension=8)
    factory = create_session_factory(migrated_engine)
    with session_scope(factory) as session:
        _build_dataset(session)

        results = retrieve_hr_chunks(
            query="synthetic leave question",
            tenant_id="tenant-unknown",
            provider=provider,
            repository=PostgresEmbeddingRepository(session),
        )

        assert results == ()


def test_only_active_embedding_sets_are_searched(migrated_engine: Engine) -> None:
    """A candidate embedding set is invisible even when it holds a perfect match.

    Both sets sit on ACTIVE document versions of the same tenant and are
    compatible on model name, model version, and dimension, so the embedding
    set status is the only field that differs. They live on two documents
    because uq_embedding_sets_version_model allows one set per
    (document version, model name, model version).
    """
    factory = create_session_factory(migrated_engine)
    with session_scope(factory) as session:
        active_chunk, _ = _searchable_chunk(
            session,
            tenant_id=TENANT_ALPHA,
            document_key="DOC-ALPHA-ACTIVE-SET",
            status=DocumentVersionStatus.ACTIVE,
            values=(0.0, 1.0, 0.0),
            content_text="Synthetic chunk in an active embedding set.",
            set_status=EmbeddingSetStatus.ACTIVE,
        )
        candidate_chunk, candidate_set = _searchable_chunk(
            session,
            tenant_id=TENANT_ALPHA,
            document_key="DOC-ALPHA-CANDIDATE-SET",
            status=DocumentVersionStatus.ACTIVE,
            values=QUERY_VECTOR,
            content_text="Synthetic chunk in a candidate embedding set.",
            set_status=EmbeddingSetStatus.CANDIDATE,
        )
        session.flush()

        records = _search(session)

        assert [record.chunk_id for record in records] == [active_chunk.id]
        assert candidate_chunk.id not in {record.chunk_id for record in records}

        # Promoting the same set makes its perfect match rank first, proving the
        # exclusion came from the embedding set status and nothing else.
        candidate_set.status = EmbeddingSetStatus.ACTIVE.value
        session.flush()
        promoted = _search(session)

        assert [record.chunk_id for record in promoted] == [
            candidate_chunk.id,
            active_chunk.id,
        ]
        assert promoted[0].distance == pytest.approx(0.0, abs=1e-6)


@pytest.mark.parametrize(
    "set_status",
    [
        EmbeddingSetStatus.CANDIDATE,
        EmbeddingSetStatus.ARCHIVED,
        EmbeddingSetStatus.FAILED,
    ],
)
def test_non_active_embedding_sets_are_never_searched(
    migrated_engine: Engine,
    set_status: EmbeddingSetStatus,
) -> None:
    factory = create_session_factory(migrated_engine)
    with session_scope(factory) as session:
        _searchable_chunk(
            session,
            tenant_id=TENANT_ALPHA,
            document_key=f"DOC-ALPHA-SET-{set_status.value.upper()}",
            status=DocumentVersionStatus.ACTIVE,
            values=QUERY_VECTOR,
            set_status=set_status,
        )
        session.flush()

        assert _search(session) == ()
