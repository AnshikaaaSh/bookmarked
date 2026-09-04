"""The single entry point for every model call in the app.

Feature code calls `complete(system=..., user=...)` and never knows which provider
is configured. Set LLM_PROVIDER in .env to switch.
"""

from __future__ import annotations

from ..config import ANSWER_MODEL, LLM_PROVIDER
from .providers import PROVIDERS, LLMConfigError, LLMUnavailableError

# Kept for backwards compatibility with earlier imports.
MissingAPIKey = LLMConfigError


def complete(
    *,
    system: str,
    user: str,
    model: str | None = None,
    max_tokens: int = 4000,
    effort: str = "medium",  # accepted for call-site compatibility; provider-specific
) -> str:
    """Run one completion and return its text."""
    provider = PROVIDERS.get(LLM_PROVIDER)
    if provider is None:
        raise LLMConfigError(
            f"Unknown LLM_PROVIDER '{LLM_PROVIDER}'. "
            f"Supported: {', '.join(sorted(PROVIDERS))}."
        )
    return provider(system, user, model or ANSWER_MODEL, max_tokens)


__all__ = ["complete", "LLMConfigError", "LLMUnavailableError", "MissingAPIKey"]
