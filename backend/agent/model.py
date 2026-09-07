"""LangChain chat model selection, mirroring LLM_PROVIDER/.env exactly.

This is a second model-calling path alongside backend/llm/providers.py — that
one stays in place for anything that just needs a single completion (none of
that code needs tool-calling). This module exists only because create_agent
requires a LangChain BaseChatModel, which providers.py's plain complete()
function can't be one of without a much larger rewrite. LLM_PROVIDER,
ANSWER_MODEL, and the .env keys are shared between both paths — provider
selection is one flag, everywhere in the app.
"""

from __future__ import annotations

import os

from ..config import (
    ANSWER_MODEL,
    EXTRACTION_MAX_RETRIES,
    EXTRACTION_MODEL,
    EXTRACTION_TIMEOUT_S,
    LLM_PROVIDER,
    MODEL_MAX_RETRIES,
    MODEL_TIMEOUT_S,
)
from ..llm.providers import LLMConfigError

# A Write/Ask/Recommend run can make several LLM calls in its ReAct loop
# (search_library, search_web, the final structured-output call) — each one
# independently retries on failure. LangChain's defaults are timeout=None (a
# single call can hang forever) and max_retries=6 with exponential backoff,
# which showed up in production as a single Write call taking 205s: Gemini's
# free tier was degraded, every call in the loop retried close to the default
# limit, and the compounded wall-clock time ran into minutes. Worse, the model
# eventually returned a response with 19 "outline" items instead of 4-6,
# several of them raw JSON-fragment text ("sources:[", "]}") rather than real
# content — consistent with the model losing track of its own output shape
# after being re-prompted several times under retry. MODEL_TIMEOUT_S /
# MODEL_MAX_RETRIES (config.py, overridable in .env) bound this to a worst
# case of roughly TIMEOUT * (RETRIES + 1) per call instead of an open-ended
# one; write_agent.py filters the output defensively too in case a similarly
# garbled response gets through anyway.


def _build(model_name: str, timeout_s: int, max_retries: int):
    if LLM_PROVIDER == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not key:
            raise LLMConfigError(
                "GEMINI_API_KEY is not set. Get a free key at "
                "https://aistudio.google.com/apikey and put it in .env"
            )
        return ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=key,
            timeout=timeout_s,
            max_retries=max_retries,
        )

    if LLM_PROVIDER == "anthropic":
        from langchain_anthropic import ChatAnthropic

        if not os.getenv("ANTHROPIC_API_KEY"):
            raise LLMConfigError(
                "ANTHROPIC_API_KEY is not set. Add it to .env, or switch providers "
                "with LLM_PROVIDER=gemini"
            )
        return ChatAnthropic(
            model=model_name,
            default_request_timeout=timeout_s,
            max_retries=max_retries,
        )

    if LLM_PROVIDER == "groq":
        from langchain_groq import ChatGroq

        if not os.getenv("GROQ_API_KEY"):
            raise LLMConfigError(
                "GROQ_API_KEY is not set. Get a free key at "
                "https://console.groq.com/keys and put it in .env"
            )
        return ChatGroq(
            model_name=model_name,
            request_timeout=timeout_s,
            max_retries=max_retries,
        )

    raise LLMConfigError(
        f"Unknown LLM_PROVIDER '{LLM_PROVIDER}'. Supported: gemini, anthropic, groq."
    )


def get_chat_model():
    """The interactive-path model (Ask, Recommend, Write) — fails fast."""
    return _build(ANSWER_MODEL, MODEL_TIMEOUT_S, MODEL_MAX_RETRIES)


def get_extraction_model():
    """The background-extraction-path model — a longer, more patient budget.
    See EXTRACTION_TIMEOUT_S in config.py for why this can't share the
    interactive path's tight timeout: it cut extraction off mid-generation on
    some books (a smaller book failed while a bigger one succeeded), not just
    on a genuinely dead connection."""
    return _build(EXTRACTION_MODEL, EXTRACTION_TIMEOUT_S, EXTRACTION_MAX_RETRIES)
