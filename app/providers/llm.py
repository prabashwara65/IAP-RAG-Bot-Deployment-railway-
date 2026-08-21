"""Vendor-neutral language model contract.

The contract describes only what the grounded answer service needs: an
identified model and one synchronous completion from a system and user prompt.
It carries no transport, credential, streaming, tool-calling, or conversation
concept, so a hosted, local, or remote implementation can satisfy it without
leaking vendor concerns into services.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    """Minimal contract every language model backend must satisfy."""

    @property
    def model_name(self) -> str:
        """Stable model identifier recorded with generated answers."""
        ...

    @property
    def model_version(self) -> str:
        """Stable version identifier for the model that produced the text."""
        ...

    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        """Return one completion for the supplied prompts."""
        ...
