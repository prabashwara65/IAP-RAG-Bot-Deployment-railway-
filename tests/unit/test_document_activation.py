"""Unit tests for automatic document activation."""

from unittest.mock import Mock
from uuid import uuid4

from sqlalchemy.orm import Session

from app.domain.documents import DocumentVersionStatus, EmbeddingSetStatus
from app.models.documents import DocumentModel, DocumentVersionModel, EmbeddingSetModel
from app.services.document_activation import activate_document


def test_activation_approves_and_activates_version_and_embedding_set() -> None:
    document_id = uuid4()
    version_id = uuid4()
    document = DocumentModel(
        id=document_id,
        tenant_id="tenant-test",
        document_key="UPLOAD-TEST",
        title="Uploaded CV",
        document_type="Other",
    )
    version = DocumentVersionModel(
        id=version_id,
        document_id=document_id,
        version_label="1.0",
        status=DocumentVersionStatus.CANDIDATE.value,
        content_hash="content-hash",
    )
    embedding_set = EmbeddingSetModel(
        id=uuid4(),
        document_version_id=version_id,
        model_name="deterministic-test",
        model_version="1",
        dimension=8,
        status=EmbeddingSetStatus.CANDIDATE.value,
    )
    session = Mock(spec=Session)
    session.scalar.side_effect = [document, version, version]
    session.scalars.return_value.all.return_value = [embedding_set]
    session.get.return_value = version

    activated = activate_document(session, "UPLOAD-TEST")

    assert activated.status is DocumentVersionStatus.ACTIVE
    assert version.approved_at is not None
    assert version.activated_at is not None
    assert document.document_type == "CV"
    assert embedding_set.status == EmbeddingSetStatus.ACTIVE.value
    session.add.assert_called_once()