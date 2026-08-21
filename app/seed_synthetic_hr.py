"""One-off command that persists the synthetic HR evaluation corpus.

Unlike ``scripts/hr_rag_evaluation.py``, which deliberately rolls its
transaction back, this command commits. It exists so that a freshly migrated
database can serve the grounded HR answer endpoint, both locally and in a
controlled portfolio deployment.

The tenant is fixed and the corpus is fixed. This command accepts no arguments,
no alternative tenant, and no external document source, because the underlying
loader activates document versions without a human approval decision and must
never be pointed at real HR content.

Run with::

    python -m app.seed_synthetic_hr
"""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import (
    create_database_engine,
    create_session_factory,
    session_scope,
)
from app.core.logging import configure_logging, get_logger
from app.evaluation.corpus import load_hr_evaluation_corpus
from app.evaluation.hr_cases import HR_EVALUATION_DOCUMENTS
from app.models.documents import DocumentModel
from app.providers.embeddings import EmbeddingProvider
from app.providers.openai_embeddings import (
    OpenAIEmbeddingError,
    openai_embedding_provider_from_settings,
)

SYNTHETIC_TENANT_ID = "tenant-synthetic"

EXIT_SUCCESS = 0
EXIT_FAILURE = 1
EXIT_CONFIGURATION_ERROR = 2
EXIT_INCONSISTENT_STATE = 3

logger = get_logger("seed.synthetic_hr")


class SyntheticSeedState(StrEnum):
    """How much of the synthetic corpus the fixed tenant already holds."""

    ABSENT = "absent"
    COMPLETE = "complete"
    PARTIAL = "partial"


class SyntheticSeedStateError(RuntimeError):
    """Raised when the corpus is neither fully absent nor fully present.

    A partial corpus is never repaired automatically. Loading the missing
    documents would leave the present ones on their original embedding set,
    and deleting the present ones is destructive, so the safe action is to
    stop and let a human decide.
    """


def expected_document_keys() -> frozenset[str]:
    """Return every synthetic document key the corpus is expected to contain."""
    return frozenset(document.document_key for document in HR_EVALUATION_DOCUMENTS)


def _seeded_document_keys(session: Session, expected: frozenset[str]) -> frozenset[str]:
    """Return the expected synthetic keys already present for the fixed tenant."""
    statement = select(DocumentModel.document_key).where(
        DocumentModel.tenant_id == SYNTHETIC_TENANT_ID,
        DocumentModel.document_key.in_(sorted(expected)),
    )
    return frozenset(session.scalars(statement))


def classify_seed_state(
    present: frozenset[str],
    expected: frozenset[str],
) -> SyntheticSeedState:
    """Classify the corpus as absent, complete, or partially seeded.

    ``documents`` carries a unique constraint on ``(tenant_id, document_key)``,
    so a rerun over a complete corpus would fail rather than duplicate rows.
    Classifying first turns that into a clear no-op, while still refusing to
    write over an inconsistent half-seeded tenant.
    """
    if not present:
        return SyntheticSeedState.ABSENT
    if present >= expected:
        return SyntheticSeedState.COMPLETE
    return SyntheticSeedState.PARTIAL


def seed_synthetic_hr_corpus(
    session: Session,
    *,
    embedding_provider: EmbeddingProvider,
) -> int:
    """Load the synthetic corpus once and report how many documents were written.

    Returns zero when the corpus is already complete, so a rerun is safe and
    costs no embedding calls. Raises ``SyntheticSeedStateError`` when the
    tenant holds only some of the expected documents; nothing is written in
    that case.
    """
    expected = expected_document_keys()
    present = _seeded_document_keys(session, expected)
    state = classify_seed_state(present, expected)

    if state is SyntheticSeedState.COMPLETE:
        logger.info(
            "Synthetic HR corpus already seeded; nothing was written "
            f"(tenant={SYNTHETIC_TENANT_ID}, documents={len(present)})"
        )
        return 0

    if state is SyntheticSeedState.PARTIAL:
        raise SyntheticSeedStateError(
            "Partially seeded synthetic HR corpus; refusing to write. "
            f"tenant={SYNTHETIC_TENANT_ID} "
            f"expected={len(expected)} present={len(present)} "
            f"missing={sorted(expected - present)}"
        )

    corpus = load_hr_evaluation_corpus(
        session,
        tenant_id=SYNTHETIC_TENANT_ID,
        embedding_provider=embedding_provider,
    )
    logger.info(
        "Synthetic HR corpus loaded "
        f"(tenant={corpus.tenant_id}, documents={corpus.document_count}, "
        f"chunks={corpus.chunk_count})"
    )
    return corpus.document_count


def main() -> int:
    """Build the configured collaborators, seed once, and commit."""
    settings: Settings = get_settings()
    configure_logging(settings.log_level)
    logger.info(f"Synthetic HR seed started (tenant={SYNTHETIC_TENANT_ID})")

    try:
        embedding_provider = openai_embedding_provider_from_settings(settings)
    except OpenAIEmbeddingError as error:
        # Only the stable failure code is reported; the credential and the
        # provider message never reach the log.
        logger.error(f"Embedding provider unavailable [{error.code.value}]")
        return EXIT_CONFIGURATION_ERROR

    engine = create_database_engine(settings)
    try:
        with session_scope(create_session_factory(engine)) as session:
            seed_synthetic_hr_corpus(session, embedding_provider=embedding_provider)
    except SyntheticSeedStateError as error:
        # Raised before any write, and ``session_scope`` rolled back regardless.
        logger.error(f"Synthetic HR seed refused: {error}")
        return EXIT_INCONSISTENT_STATE
    except OpenAIEmbeddingError as error:
        # ``session_scope`` has already rolled the transaction back.
        #
        # ``str(error)`` is the embedding provider's own wrapper message. Every
        # branch in ``app.providers.openai_embeddings`` builds that message from
        # a fixed string, a count, or ``type(sdk_error).__name__`` alone, and
        # never interpolates the SDK message, request headers, response body, or
        # the credential. Logging the stable code alongside it turns an opaque
        # deployment failure into an actionable one without weakening that
        # guarantee.
        logger.error(
            f"Synthetic HR seed failed [{error.code.value}]: {error}; rolled back"
        )
        return EXIT_FAILURE
    except SQLAlchemyError as error:
        # ``session_scope`` has already rolled the transaction back. The
        # exception type alone is reported, because SQLAlchemy messages can
        # carry connection and statement detail.
        logger.error(f"Synthetic HR seed failed [{type(error).__name__}]; rolled back")
        return EXIT_FAILURE
    finally:
        engine.dispose()

    logger.info("Synthetic HR seed completed successfully")
    return EXIT_SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())
