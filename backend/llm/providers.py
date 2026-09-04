"""Provider implementations behind one `complete()` signature.

Every model call in the app goes through this module, so switching providers is
a one-line change in .env and never touches feature code. Adding a provider means
writing one function with this shape and registering it in PROVIDERS:

    def _complete(system: str, user: str, model: str, max_tokens: int) -> str

Currently implemented: gemini (free tier) and anthropic. Groq, OpenRouter and
Ollama all speak an OpenAI-compatible API, so each is a similar small function.
"""

from __future__ import annotations

import os
import time


class LLMConfigError(RuntimeError):
    """Setup problem the user can fix — missing key, unknown model, bad provider."""


class LLMUnavailableError(RuntimeError):
    """The provider is transiently down (5xx) even after retrying. Not the
    user's fault and not fixable by changing config — just try again shortly."""


# --- Gemini --------------------------------------------------------------


def _gemini_client():
    try:
        from google import genai
    except ImportError as exc:
        raise LLMConfigError("google-genai is not installed: pip install google-genai") from exc

    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not key:
        raise LLMConfigError(
            "GEMINI_API_KEY is not set. Get a free key at https://aistudio.google.com/apikey "
            "and put it in .env"
        )
    return genai.Client(api_key=key)


# Gemini's free tier flaps under load — a request can 503 "high demand" and
# succeed seconds later with no other change. Worth a few short retries before
# surfacing anything to the user; a ClientError (4xx) is never worth retrying,
# since the same bad request just fails the same way every time.
_MAX_RETRIES = 3
_RETRY_DELAYS = (1, 3, 6)  # seconds


def gemini_complete(system: str, user: str, model: str, max_tokens: int) -> str:
    from google.genai import errors, types

    client = _gemini_client()
    config = types.GenerateContentConfig(system_instruction=system, max_output_tokens=max_tokens)

    last_error: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            response = client.models.generate_content(model=model, contents=user, config=config)
            break
        except errors.ClientError as exc:
            message = str(exc)
            if "API key" in message or "API_KEY" in message:
                raise LLMConfigError(f"Gemini rejected the API key: {message}") from exc
            if "not found" in message.lower() or "no longer available" in message.lower():
                raise LLMConfigError(
                    f"Gemini model '{model}' isn't callable with this key (Google retires dated "
                    f"model names from new keys without much notice). Try ANSWER_MODEL="
                    f"gemini-flash-latest in .env, or run `python -m backend.scripts.check_llm "
                    f"--list` to see what your key can actually call — the list can include "
                    f"names generate_content then rejects."
                ) from exc
            if "RESOURCE_EXHAUSTED" in message or "429" in message:
                raise LLMConfigError(
                    "Gemini free-tier rate limit hit. Wait a minute, or set a smaller model "
                    "in .env (ANSWER_MODEL=gemini-flash-lite-latest)."
                ) from exc
            raise
        except errors.ServerError as exc:
            last_error = exc
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_RETRY_DELAYS[attempt])
    else:
        raise LLMUnavailableError(
            f"Gemini is currently overloaded (tried {_MAX_RETRIES} times over "
            f"{sum(_RETRY_DELAYS)}s). This is Google's free-tier capacity, not your setup — "
            f"just try again shortly."
        ) from last_error

    text = response.text
    if not text:
        # Usually a safety block or an empty candidate list.
        raise RuntimeError(f"Gemini returned no text. Full response: {response}")
    return text.strip()


# --- Anthropic -----------------------------------------------------------


def anthropic_complete(system: str, user: str, model: str, max_tokens: int) -> str:
    try:
        import anthropic
    except ImportError as exc:
        raise LLMConfigError("anthropic is not installed: pip install anthropic") from exc

    if not os.getenv("ANTHROPIC_API_KEY"):
        raise LLMConfigError(
            "ANTHROPIC_API_KEY is not set. Add it to .env, or switch providers with "
            "LLM_PROVIDER=gemini"
        )

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": user}],
    )

    if response.stop_reason == "refusal":
        detail = getattr(response.stop_details, "explanation", "") or ""
        raise RuntimeError(f"The model declined this request. {detail}".strip())

    return "\n".join(b.text for b in response.content if b.type == "text").strip()


PROVIDERS = {
    "gemini": gemini_complete,
    "anthropic": anthropic_complete,
}
