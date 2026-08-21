"""Deterministic validation shared by every provider-produced vector.

The helper stays free of embedding- or retrieval-specific error codes so each
service can map a failure onto its own stable code without duplicating the
component checks.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from math import isfinite


class VectorIssue(StrEnum):
    """Neutral reasons a vector cannot be accepted."""

    DIMENSION_MISMATCH = "dimension_mismatch"
    MALFORMED_VALUE = "malformed_value"
    NON_FINITE_VALUE = "non_finite_value"


class VectorValidationError(ValueError):
    """Raised when a vector fails a deterministic structural check."""

    def __init__(
        self,
        issue: VectorIssue,
        message: str,
        *,
        position: int | None = None,
    ) -> None:
        self.issue = issue
        self.position = position
        super().__init__(message)


def validate_vector(
    vector: Sequence[object],
    *,
    dimension: int,
) -> tuple[float, ...]:
    """Return the vector as finite floats or raise a neutral validation error."""
    values = tuple(vector)
    if len(values) != dimension:
        raise VectorValidationError(
            VectorIssue.DIMENSION_MISMATCH,
            f"Vector has {len(values)} components where {dimension} were expected.",
        )

    validated: list[float] = []
    for position, value in enumerate(values):
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise VectorValidationError(
                VectorIssue.MALFORMED_VALUE,
                f"Vector component {position} is not a real number.",
                position=position,
            )
        if not isfinite(value):
            raise VectorValidationError(
                VectorIssue.NON_FINITE_VALUE,
                f"Vector component {position} is not a finite value.",
                position=position,
            )
        validated.append(float(value))

    return tuple(validated)
