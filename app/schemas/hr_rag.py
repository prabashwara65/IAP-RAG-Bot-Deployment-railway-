"""Request and response contracts for the HR grounded answer endpoint."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.hr_documents import DocumentType
from app.services.hr_rag import HRGroundedAnswer, HRSourceCitation

MAX_QUESTION_LENGTH = 2000
MAX_TENANT_ID_LENGTH = 120


class HRAskRequest(BaseModel):
    """One grounded HR question for one tenant.

    ``tenant_id`` is supplied by the caller because the platform has no
    authentication layer yet, so there is no authenticated principal to derive
    it from. This is request routing, not authorization: it does not prove the
    caller may read that tenant's HR content. Authentication must arrive before
    this endpoint is exposed outside a trusted network.

    ``str_strip_whitespace`` combined with ``min_length`` rejects blank and
    whitespace-only values, matching the HR metadata schema convention.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str = Field(min_length=1, max_length=MAX_QUESTION_LENGTH)
    tenant_id: str = Field(min_length=1, max_length=MAX_TENANT_ID_LENGTH)
    document_type: DocumentType | None = None


class HRAnswerCitation(BaseModel):
    """One approved HR source the answer referenced.

    Internal identifiers (chunk, document, version, and embedding set UUIDs)
    are deliberately not exposed. ``document_key`` is the stable business
    identifier a client needs to locate the source.
    """

    model_config = ConfigDict(extra="forbid")

    citation_id: str
    document_key: str
    document_title: str
    heading_path: str
    chunk_index: int
    distance: float

    @classmethod
    def from_domain(cls, citation: HRSourceCitation) -> HRAnswerCitation:
        """Project one domain citation onto the public contract."""
        return cls(
            citation_id=citation.citation_id,
            document_key=citation.document_key,
            document_title=citation.document_title,
            heading_path=citation.heading_path,
            chunk_index=citation.chunk_index,
            distance=citation.distance,
        )


class HRAskResponse(BaseModel):
    """A grounded HR answer with the sources it referenced.

    ``insufficient_evidence`` is a normal successful outcome, not an error: it
    reports that the approved HR sources did not support an answer.
    """

    model_config = ConfigDict(extra="forbid")

    answer: str
    citations: list[HRAnswerCitation]
    insufficient_evidence: bool

    @classmethod
    def from_domain(cls, answer: HRGroundedAnswer) -> HRAskResponse:
        """Project one grounded answer onto the public contract."""
        return cls(
            answer=answer.answer,
            citations=[
                HRAnswerCitation.from_domain(citation) for citation in answer.citations
            ],
            insufficient_evidence=answer.insufficient_evidence,
        )
