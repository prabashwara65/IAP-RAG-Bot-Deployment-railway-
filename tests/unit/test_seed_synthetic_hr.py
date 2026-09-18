"""Tests for the synthetic HR seed command's failure diagnostics.

The seed runs as a one-off ECS task, so its only observable output is the log
line that reaches CloudWatch. These tests capture what ``configure_logging``
actually writes, rather than a proxy, and assert both halves of the contract:
the failure must be diagnosable, and it must stay free of credential material.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from io import StringIO
from typing import Any

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings
from app.core.logging import configure_logging
from app.providers.gemini_embeddings import (
    GeminiEmbeddingError,
    GeminiEmbeddingErrorCode,
)
from app.seed_synthetic_hr import (
    EXIT_CONFIGURATION_ERROR,
    EXIT_FAILURE,
    EXIT_INCONSISTENT_STATE,
    EXIT_SUCCESS,
    SyntheticSeedStateError,
    main,
)

# Shaped like a credential but deliberately not one.
FAKE_API_KEY = "sk-test-not-a-real-key-0123456789"

# What the provider wrapper produces for a rejected key: the SDK exception type
# only, never its message.
AUTHENTICATION_FAILURE_MESSAGE = (
    "The Gemini embedding request failed: ClientError."
)


class _FakeEngine:
    """Records disposal so the ``finally`` branch can be asserted."""

    def __init__(self) -> None:
        self.disposed = False

    def dispose(self) -> None:
        self.disposed = True


class _SeedRun:
    """The observable result of one ``main()`` invocation."""

    def __init__(self, exit_code: int, output: str, engine: _FakeEngine, events: list[str]) -> None:
        self.exit_code = exit_code
        self.output = output
        self.engine = engine
        self.events = events

    @property
    def messages(self) -> list[str]:
        """Return the ``message`` field of every emitted JSON log record."""
        return [
            json.loads(line)["message"]
            for line in self.output.splitlines()
            if line.strip()
        ]

    @property
    def error_messages(self) -> list[str]:
        return [
            json.loads(line)["message"]
            for line in self.output.splitlines()
            if line.strip() and json.loads(line)["level"] == "ERROR"
        ]


def _run_main(
    monkeypatch: pytest.MonkeyPatch,
    *,
    seed: Callable[..., int],
    provider_error: GeminiEmbeddingError | None = None,
) -> _SeedRun:
    """Run ``main()`` with every collaborator replaced but its logic intact."""
    stream = StringIO()
    engine = _FakeEngine()
    events: list[str] = []

    monkeypatch.setattr(
        "app.seed_synthetic_hr.get_settings",
        lambda: Settings(_env_file=None),  # type: ignore[call-arg]
    )
    monkeypatch.setattr(
        "app.seed_synthetic_hr.configure_logging",
        lambda level: configure_logging(level, stream=stream),
    )

    def _provider(_settings: Settings) -> object:
        if provider_error is not None:
            raise provider_error
        return object()

    monkeypatch.setattr(
        "app.seed_synthetic_hr.gemini_embedding_provider_from_settings", _provider
    )
    monkeypatch.setattr(
        "app.seed_synthetic_hr.create_database_engine", lambda _settings: engine
    )
    monkeypatch.setattr(
        "app.seed_synthetic_hr.create_session_factory", lambda _engine: "session-factory"
    )

    @contextmanager
    def _session_scope(_factory: object) -> Iterator[object]:
        events.append("open")
        try:
            yield object()
        except BaseException:
            events.append("rollback")
            raise
        events.append("commit")

    monkeypatch.setattr("app.seed_synthetic_hr.session_scope", _session_scope)
    monkeypatch.setattr("app.seed_synthetic_hr.seed_synthetic_hr_corpus", seed)

    exit_code = main()
    return _SeedRun(exit_code, stream.getvalue(), engine, events)


def _raise(error: Exception) -> Callable[..., int]:
    def _seed(*_args: Any, **_kwargs: Any) -> int:
        raise error

    return _seed


def _succeed(count: int = 4) -> Callable[..., int]:
    def _seed(*_args: Any, **_kwargs: Any) -> int:
        return count

    return _seed


def test_a_gemini_failure_logs_the_stable_code_and_wrapper_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The exact regression: the ECS log said only the exception class name."""
    run = _run_main(
        monkeypatch,
        seed=_raise(
            GeminiEmbeddingError(
                GeminiEmbeddingErrorCode.PROVIDER_REQUEST_FAILED,
                AUTHENTICATION_FAILURE_MESSAGE,
            )
        ),
    )

    assert run.exit_code == EXIT_FAILURE
    assert len(run.error_messages) == 1
    message = run.error_messages[0]
    assert "provider_request_failed" in message
    assert AUTHENTICATION_FAILURE_MESSAGE in message
    assert "ClientError" in message
    assert "rolled back" in message
    # The old line carried the wrapper class name and nothing actionable.
    assert message != "Synthetic HR seed failed [GeminiEmbeddingError]; rolled back"


@pytest.mark.parametrize(
    "code",
    [
        GeminiEmbeddingErrorCode.PROVIDER_REQUEST_FAILED,
        GeminiEmbeddingErrorCode.PROVIDER_DIMENSION_MISMATCH,
        GeminiEmbeddingErrorCode.INVALID_PROVIDER_RESPONSE,
    ],
)
def test_every_embedding_failure_code_reaches_the_log(
    monkeypatch: pytest.MonkeyPatch,
    code: GeminiEmbeddingErrorCode,
) -> None:
    run = _run_main(
        monkeypatch, seed=_raise(GeminiEmbeddingError(code, "sanitized detail"))
    )

    assert run.exit_code == EXIT_FAILURE
    assert code.value in run.error_messages[0]


def test_a_gemini_failure_never_logs_credential_material(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A provider message is only logged because the wrapper sanitizes it."""
    run = _run_main(
        monkeypatch,
        seed=_raise(
            GeminiEmbeddingError(
                GeminiEmbeddingErrorCode.PROVIDER_REQUEST_FAILED,
                AUTHENTICATION_FAILURE_MESSAGE,
            )
        ),
    )

    assert FAKE_API_KEY not in run.output
    assert "Bearer" not in run.output
    assert "Authorization" not in run.output
    assert "api_key" not in run.output


def test_a_gemini_failure_rolls_back_and_disposes_the_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _run_main(
        monkeypatch,
        seed=_raise(
            GeminiEmbeddingError(
                GeminiEmbeddingErrorCode.PROVIDER_REQUEST_FAILED,
                AUTHENTICATION_FAILURE_MESSAGE,
            )
        ),
    )

    assert run.events == ["open", "rollback"]
    assert run.engine.disposed is True


def test_a_database_failure_still_reports_only_the_exception_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SQLAlchemy messages can carry host and statement detail, so they stay out."""
    sensitive = "password authentication failed for user oiap at 10.0.1.5"
    run = _run_main(monkeypatch, seed=_raise(SQLAlchemyError(sensitive)))

    assert run.exit_code == EXIT_FAILURE
    assert "SQLAlchemyError" in run.error_messages[0]
    assert "rolled back" in run.error_messages[0]
    assert sensitive not in run.output
    assert run.engine.disposed is True


def test_a_partial_seed_state_keeps_its_own_exit_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _run_main(
        monkeypatch, seed=_raise(SyntheticSeedStateError("expected=4 present=2"))
    )

    assert run.exit_code == EXIT_INCONSISTENT_STATE
    assert "refused" in run.error_messages[0]
    assert run.engine.disposed is True


def test_a_missing_credential_is_reported_before_any_database_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _run_main(
        monkeypatch,
        seed=_succeed(),
        provider_error=GeminiEmbeddingError(
            GeminiEmbeddingErrorCode.MISSING_API_KEY,
            "GEMINI_API_KEY is not configured.",
        ),
    )

    assert run.exit_code == EXIT_CONFIGURATION_ERROR
    assert "missing_api_key" in run.error_messages[0]
    assert run.events == []


def test_a_successful_seed_commits_and_exits_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _run_main(monkeypatch, seed=_succeed())

    assert run.exit_code == EXIT_SUCCESS
    assert run.events == ["open", "commit"]
    assert run.error_messages == []
    assert "completed successfully" in run.messages[-1]
    assert run.engine.disposed is True
