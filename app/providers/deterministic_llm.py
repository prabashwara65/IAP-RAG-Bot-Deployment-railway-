"""Deterministic, dependency-free language model stand-in for tests and local runs.

WARNING: this provider is NOT a language model. It performs no reasoning,
no reading comprehension, and no summarization. It inspects the supplied user
prompt for source markers such as ``[S1]`` and returns a fixed sentence citing
the first marker it finds. It exists only to exercise prompt construction,
citation validation, and grounding behaviour without network access,
credentials, or model downloads. Never use it to answer a real question.
"""

from __future__ import annotations

import re

DETERMINISTIC_LLM_MODEL_NAME = "deterministic-echo-llm"
DETERMINISTIC_LLM_MODEL_VERSION = "1.0.0"
GROUNDED_ANSWER_TEMPLATE = "The supplied HR sources address this question. {marker}"
UNGROUNDED_ANSWER = "The supplied HR sources were not recognised."

_SOURCE_MARKER_PATTERN = re.compile(r"\[S\d+\]")


class DeterministicLLMProvider:
    """Cite the first source marker found in the prompt, with no reasoning."""

    @property
    def model_name(self) -> str:
        return DETERMINISTIC_LLM_MODEL_NAME

    @property
    def model_version(self) -> str:
        return DETERMINISTIC_LLM_MODEL_VERSION

    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        """Return a fixed sentence citing the first supplied source marker."""
        markers = _SOURCE_MARKER_PATTERN.findall(user_prompt)
        if not markers:
            return UNGROUNDED_ANSWER
        return GROUNDED_ANSWER_TEMPLATE.format(marker=markers[0])
