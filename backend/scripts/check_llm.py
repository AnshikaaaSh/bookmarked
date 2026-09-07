"""Verify the LLM setup without starting the app.

    python -m backend.scripts.check_llm          # send one tiny test prompt
    python -m backend.scripts.check_llm --list   # list models your key can use

Run this right after putting your API key in .env. It costs a fraction of a cent
(nothing on a free tier) and tells you exactly what's wrong if something is.
"""

from __future__ import annotations

import argparse
import os
import sys

from ..config import ANSWER_MODEL, EXTRACTION_MODEL, LLM_PROVIDER
from ..llm import LLMConfigError, complete


def _list_gemini() -> int:
    from google import genai

    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not key:
        print("GEMINI_API_KEY is not set — add it to .env first.")
        return 1

    client = genai.Client(api_key=key)
    print("Models your key can call for text generation:\n")
    for model in client.models.list():
        actions = getattr(model, "supported_actions", None) or []
        if not actions or "generateContent" in actions:
            print(f"  {model.name}")
    return 0


def _list_groq() -> int:
    import groq

    key = os.getenv("GROQ_API_KEY")
    if not key:
        print("GROQ_API_KEY is not set — add it to .env first.")
        return 1

    client = groq.Groq(api_key=key)
    print("Models your key can call:\n")
    for model in client.models.list().data:
        print(f"  {model.id}")
    return 0


def list_models() -> int:
    if LLM_PROVIDER == "gemini":
        return _list_gemini()
    if LLM_PROVIDER == "groq":
        return _list_groq()
    print(f"--list isn't implemented for {LLM_PROVIDER} — Anthropic doesn't expose a "
          f"model-listing endpoint the same way; see console.anthropic.com for its catalog.")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the LLM setup.")
    parser.add_argument("--list", action="store_true", help="List available models.")
    args = parser.parse_args(argv)

    print(f"provider         {LLM_PROVIDER}")
    print(f"answer model     {ANSWER_MODEL}")
    print(f"extraction model {EXTRACTION_MODEL}")

    key_names = {
        "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
        "anthropic": ("ANTHROPIC_API_KEY",),
        "groq": ("GROQ_API_KEY",),
    }
    found = [n for n in key_names.get(LLM_PROVIDER, ()) if os.getenv(n)]
    print(f"api key          {'set via ' + found[0] if found else 'NOT SET'}\n")

    if args.list:
        return list_models()

    try:
        reply = complete(
            system="You are a test harness. Reply with exactly the word: ready",
            user="Say ready.",
            max_tokens=200,
        )
    except LLMConfigError as exc:
        print(f"SETUP PROBLEM\n  {exc}")
        return 1
    except Exception as exc:  # noqa: BLE001 — surface anything else verbatim
        print(f"CALL FAILED\n  {type(exc).__name__}: {exc}")
        return 1

    print(f"OK — model replied: {reply[:120]!r}")
    print("\nYou're set. Start the app with: uvicorn backend.main:app --reload")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
