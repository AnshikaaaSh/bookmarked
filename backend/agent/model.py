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

from ..config import ANSWER_MODEL, EXTRACTION_MODEL, LLM_PROVIDER
from ..llm.providers import LLMConfigError


def _build(model_name: str):
    if LLM_PROVIDER == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not key:
            raise LLMConfigError(
                "GEMINI_API_KEY is not set. Get a free key at "
                "https://aistudio.google.com/apikey and put it in .env"
            )
        return ChatGoogleGenerativeAI(model=model_name, google_api_key=key)

    if LLM_PROVIDER == "anthropic":
        from langchain_anthropic import ChatAnthropic

        if not os.getenv("ANTHROPIC_API_KEY"):
            raise LLMConfigError(
                "ANTHROPIC_API_KEY is not set. Add it to .env, or switch providers "
                "with LLM_PROVIDER=gemini"
            )
        return ChatAnthropic(model=model_name)

    raise LLMConfigError(f"Unknown LLM_PROVIDER '{LLM_PROVIDER}'. Supported: gemini, anthropic.")


def get_chat_model():
    """The interactive-path model (Ask, Recommend)."""
    return _build(ANSWER_MODEL)


def get_extraction_model():
    """The background-extraction-path model — see EXTRACTION_MODEL in config.py
    for why this can differ from the interactive model."""
    return _build(EXTRACTION_MODEL)
