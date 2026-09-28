"""Add a single synthetic HR document to the OIAP database.

WARNING: This bypasses human approval and activates the version directly.
For synthetic demo/evaluation data only. Never point this at a tenant
holding real HR content.

Usage:
    python3 -m scripts.add_document data/synthetic/hr/my-policy.md
"""

from __future__ import annotations

import re
import sys
from datetime import date, datetime
from pathlib import Path

import yaml

from app.core.config import get_settings
from app.core.database import (
    create_database_engine,
    create_session_factory,
    session_scope,
)
from app.evaluation.corpus import load_hr_evaluation_corpus
from app.evaluation.hr_cases import HREvaluationDocument
from app.providers.gemini_embeddings import gemini_embedding_provider_from_settings
from app.schemas.hr_documents import HRDocumentMetadata


FRONT_MATTER_PATTERN = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


def parse_markdown_file(path: Path) -> tuple[dict, str]:
    """Split YAML front-matter from the Markdown body."""
    text = path.read_text(encoding="utf-8")
    match = FRONT_MATTER_PATTERN.match(text)
    if not match:
        raise ValueError(
            f"{path}: missing YAML front-matter. "
            "File must start with '---' and end the front-matter with '---'."
        )
    raw_metadata = yaml.safe_load(match.group(1))
    body = match.group(2).strip()
    if not isinstance(raw_metadata, dict):
        raise ValueError(f"{path}: YAML front-matter must be a mapping.")
    return raw_metadata, body


def _parse_date(value) -> date:
    """Accept a date object or an ISO date string."""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise ValueError(f"Cannot parse date from {value!r}")


def build_hr_document(
    raw_metadata: dict,
    body: str,
    *,
    document_key: str,
) -> HREvaluationDocument:
    """Build an HREvaluationDocument from parsed YAML and a Markdown body."""
    metadata = HRDocumentMetadata.model_validate(
        {
            "document_title": raw_metadata["title"],
            "document_type": raw_metadata.get("document_type", "Policy"),
            "department": raw_metadata.get("department", "Human Resources"),
            "summary_purpose": raw_metadata.get(
                "summary_purpose", raw_metadata["title"]
            ),
            "language": raw_metadata.get("language", "English"),
            "version": str(raw_metadata.get("version", "1.0")),
            "effective_date": _parse_date(
                raw_metadata.get("effective_date", "2026-01-01")
            ),
            "content_owner": raw_metadata.get(
                "content_owner", "Synthetic HR Team"
            ),
            "approval_status": raw_metadata.get("approval_status", "Approved"),
            "approved_for_rag": raw_metadata.get(
                "approved_for_rag", "Approved"
            ),
            "document_status": raw_metadata.get("document_status", "Approved"),
            "access_level": raw_metadata.get(
                "access_level", "Internal General"
            ),
            "contains_personal_data": raw_metadata.get(
                "contains_personal_data", "No"
            ),
            "contains_confidential_data": raw_metadata.get(
                "contains_confidential_data", "No"
            ),
            "synthetic": raw_metadata.get("synthetic", True),
            "official_company_document": raw_metadata.get(
                "official_company_document", False
            ),
            "data_mode": raw_metadata.get("data_mode", "synthetic_demo"),
            "approved_by": raw_metadata.get(
                "approved_by", "Synthetic Reviewer"
            ),
            "keywords": raw_metadata.get("keywords", []),
            "document_content": body,
        }
    )
    return HREvaluationDocument(
        document_key=document_key,
        metadata=metadata,
    )


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python3 -m scripts.add_document <path-to-md>")
        return 1

    md_path = Path(sys.argv[1])
    if not md_path.exists():
        print(f"❌ File not found: {md_path}")
        return 1

    # Parse the Markdown file
    try:
        raw_metadata, body = parse_markdown_file(md_path)
    except Exception as exc:
        print(f"❌ Failed to parse {md_path}: {exc}")
        return 1

    # Derive document_key from YAML or filename
    document_key = (
        raw_metadata.get("document_id")
        or raw_metadata.get("document_key")
        or md_path.stem.upper()
    )

    # Build the HREvaluationDocument
    try:
        hr_document = build_hr_document(
            raw_metadata, body, document_key=document_key
        )
    except Exception as exc:
        print(f"❌ Failed to build document object: {exc}")
        return 1

    # Set up config, DB, and embedding provider
    settings = get_settings()
    if settings.gemini_api_key is None:
        print("❌ GEMINI_API_KEY is not set. Export it before running.")
        return 1

    engine = create_database_engine(settings)
    factory = create_session_factory(engine)
    embedding_provider = gemini_embedding_provider_from_settings(settings)

    # Load into the database
    try:
        with session_scope(factory) as session:
            result = load_hr_evaluation_corpus(
                session,
                tenant_id="default",
                embedding_provider=embedding_provider,
                documents=(hr_document,),
            )
            session.commit()
    except Exception as exc:
        print(f"❌ Failed to load document: {exc}")
        return 1

    print(f"✅ Added: {hr_document.metadata.document_title}")
    print(f"   document_key : {hr_document.document_key}")
    print(f"   tenant_id    : {result.tenant_id}")
    print(f"   chunks       : {result.chunk_count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())