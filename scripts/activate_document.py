"""Activate uploaded document versions using the governed lifecycle path."""

from __future__ import annotations

import argparse

from app.core.config import get_settings
from app.core.database import (
    create_database_engine,
    create_session_factory,
    session_scope,
)
from app.core.logging import get_logger
from app.services.document_activation import activate_all_documents, activate_document

logger = get_logger("scripts.activate_document")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("document_key", nargs="?", help="Document key to activate")
    parser.add_argument(
        "--all", action="store_true", help="Activate all eligible documents"
    )
    arguments = parser.parse_args()
    if arguments.all == (arguments.document_key is not None):
        parser.error("provide either a document_key or --all")

    settings = get_settings()
    engine = create_database_engine(settings)
    try:
        factory = create_session_factory(engine)
        with session_scope(factory) as session:
            if arguments.all:
                versions = activate_all_documents(session)
            else:
                assert arguments.document_key is not None
                versions = (activate_document(session, arguments.document_key),)
        logger.info("Activated %d document version(s)", len(versions))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()