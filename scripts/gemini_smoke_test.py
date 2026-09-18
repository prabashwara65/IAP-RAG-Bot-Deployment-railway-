"""Manual Gemini connectivity check.

This script performs one real, tiny API call and is never run by pytest. It
exists so a developer can verify credentials and model access without adding a
production endpoint.

Usage:
    GEMINI_API_KEY=... GEMINI_MODEL=gemini-2.5-flash python -m scripts.gemini_smoke_test
"""

from __future__ import annotations

from app.core.config import get_settings
from app.providers.gemini_llm import GeminiLLMError, gemini_llm_provider_from_settings

EXPECTED_ANSWER = "OIAP_GEMINI_OK"
SMOKE_SYSTEM_PROMPT = "You are a test assistant. Reply with exactly: OIAP_GEMINI_OK"
SMOKE_USER_PROMPT = "Run the smoke test."


def main() -> int:
    """Send one minimal prompt and report whether the expected reply came back."""
    try:
        provider = gemini_llm_provider_from_settings(get_settings())
    except GeminiLLMError as error:
        print(f"CONFIGURATION FAILED [{error.code.value}]: {error}")
        return 2

    print(f"provider={provider.model_name} model={provider.model_version}")
    try:
        answer = provider.generate(
            system_prompt=SMOKE_SYSTEM_PROMPT,
            user_prompt=SMOKE_USER_PROMPT,
        )
    except GeminiLLMError as error:
        print(f"REQUEST FAILED [{error.code.value}]: {error}")
        return 1

    normalized = answer.strip()
    print(f"response={normalized!r}")
    if normalized != EXPECTED_ANSWER:
        print(f"SMOKE TEST FAILED: expected {EXPECTED_ANSWER!r}")
        return 1

    print("SMOKE TEST OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
