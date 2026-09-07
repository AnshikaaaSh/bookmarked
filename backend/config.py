"""Central configuration. Everything path- or model-related resolves here."""

from __future__ import annotations

import os
from pathlib import Path

# .env is loaded by backend/__init__.py, which always runs before this module —
# doing it here too would just be a second load_dotenv() call for no benefit.
ROOT = Path(__file__).resolve().parent.parent

# --- Paths ---------------------------------------------------------------
DATA_DIR = ROOT / "data"
NOTES_DIR = DATA_DIR / "books"        # highlights / notes, chapter-tagged
TEXTS_DIR = DATA_DIR / "texts"        # full narrative text (needed for the graph)
ARTICLES_DIR = DATA_DIR / "articles"  # saved blog posts / articles

CHROMA_DIR = ROOT / ".chroma"
GRAPH_DIR = DATA_DIR / "graphs"       # one JSON graph per book
LOG_DIR = ROOT / "logs"
FRONTEND_DIR = ROOT / "frontend"

COLLECTION = "library"

# --- Models --------------------------------------------------------------
# One provider for every model call; swap it in .env without touching any feature
# code. Embeddings are always local and free, so this only affects generation.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()

# ANSWER_MODEL is the interactive path (Ask / Write). EXTRACTION_MODEL runs in
# background jobs where quality matters more than latency (NFR6 allows async),
# because extraction errors compound into the character graph.
# Gemini's dated model names (gemini-2.5-flash, ...) get retired from new keys
# faster than this file gets updated — a check_llm run in Sept 2026 hit exactly
# that. The "-latest" aliases stay pointed at whatever Google currently
# recommends, so they're the safer default even though they drift over time.
#
# gemini-flash-latest specifically resolves to a model with a stingy free-tier
# quota (20 requests/day, confirmed by hitting it repeatedly during Sept 2026
# testing) — unworkable for a project you're actively iterating on. The lite
# variant handled the same testing load without issue, so it's the default
# despite slightly lower quality; bump ANSWER_MODEL in .env if you have paid
# quota or the free limits change.
_DEFAULT_MODELS = {
    "gemini": {"answer": "gemini-flash-lite-latest", "extraction": "gemini-flash-lite-latest"},
    "anthropic": {"answer": "claude-opus-5", "extraction": "claude-opus-5"},
    # Added as an escape hatch for Gemini free-tier degradation — different
    # infra, so a Gemini outage doesn't take this down too. In practice it
    # turned out to have its own tradeoffs, not a clean win:
    #  - Intermittent malformed tool calls (~1-in-4 in testing) — the model
    #    invented a generic {cursor, id} shape instead of the tool's real
    #    {query} schema.
    #  - Combining `tools` with `response_format` (Recommend, Write) hit a
    #    hard 400 on Groq specifically ("json mode cannot be combined with
    #    tool/function calling") — fixed by forcing a tool-call-based
    #    structured-output strategy instead of letting create_agent
    #    auto-select one; see the ToolStrategy usage in recommend_agent.py /
    #    write_agent.py.
    #  - The free "on_demand" tier caps at 8000 tokens/minute *per request*,
    #    not just cumulatively — Recommend's request (system prompt + two
    #    tool schemas + retrieved chunks + its output schema) exceeded that
    #    on its own, confirmed on both gpt-oss-120b and the smaller 20b
    #    variant, with zero other usage in the window. Not a timing issue —
    #    no amount of waiting fixes a single request that's too large.
    #    Practically, this means Recommend does not work on Groq's free tier
    #    at all right now; Write is close to the same ceiling depending on
    #    how much gets retrieved; Ask (one tool, no output schema) is the
    #    one most likely to actually fit.
    # Gemini stays the default. This is a documented option, not a proven
    # upgrade — flip LLM_PROVIDER to try it, but don't assume it's more
    # reliable without re-checking, and expect Recommend specifically to fail.
    # `llama-3.3-70b-versatile` (an earlier default here) no longer exists in
    # Groq's catalog at all — reconfirmed with `check_llm --list` before
    # picking this one, same stale-model-name risk as Gemini's dated names.
    "groq": {"answer": "openai/gpt-oss-120b", "extraction": "openai/gpt-oss-120b"},
}
_defaults = _DEFAULT_MODELS.get(LLM_PROVIDER, _DEFAULT_MODELS["gemini"])

ANSWER_MODEL = os.getenv("ANSWER_MODEL") or _defaults["answer"]
EXTRACTION_MODEL = os.getenv("EXTRACTION_MODEL") or _defaults["extraction"]

# Per-call timeout and retry count for the interactive path (Ask, Recommend,
# Write — agent/model.py's get_chat_model()). Worst case per call is roughly
# MODEL_TIMEOUT_S * (MODEL_MAX_RETRIES + 1) — an agent run can chain several
# calls (tool use, then a final answer), so this compounds. Lower these when a
# provider is visibly degraded and you'd rather fail fast than wait out a slow
# response that might still succeed; raise them back once it recovers.
MODEL_TIMEOUT_S = int(os.getenv("MODEL_TIMEOUT_S", "12"))
MODEL_MAX_RETRIES = int(os.getenv("MODEL_MAX_RETRIES", "1"))

# Extraction (get_extraction_model()) is a separate, longer budget — it's an
# offline background job (NFR6 explicitly allows this to be slow), not a user
# waiting on a chat reply, and it sends a whole book's text in one call, which
# genuinely takes longer to process than an interactive turn. Sharing the
# interactive timeout here cut extraction off mid-generation on some books —
# smaller books failed while a bigger one succeeded, which only makes sense if
# the clock was the constraint, not the provider being down.
EXTRACTION_TIMEOUT_S = int(os.getenv("EXTRACTION_TIMEOUT_S", "90"))
EXTRACTION_MAX_RETRIES = int(os.getenv("EXTRACTION_MAX_RETRIES", "2"))

# --- Retrieval -----------------------------------------------------------
TOP_K = int(os.getenv("TOP_K", "6"))
CHUNK_TARGET_CHARS = int(os.getenv("CHUNK_TARGET_CHARS", "1200"))
CHUNK_OVERLAP_CHARS = int(os.getenv("CHUNK_OVERLAP_CHARS", "150"))


def ensure_dirs() -> None:
    for d in (NOTES_DIR, TEXTS_DIR, ARTICLES_DIR, GRAPH_DIR, LOG_DIR):
        d.mkdir(parents=True, exist_ok=True)
