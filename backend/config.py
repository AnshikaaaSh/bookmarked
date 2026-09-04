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
}
_defaults = _DEFAULT_MODELS.get(LLM_PROVIDER, _DEFAULT_MODELS["gemini"])

ANSWER_MODEL = os.getenv("ANSWER_MODEL") or _defaults["answer"]
EXTRACTION_MODEL = os.getenv("EXTRACTION_MODEL") or _defaults["extraction"]

# --- Retrieval -----------------------------------------------------------
TOP_K = int(os.getenv("TOP_K", "6"))
CHUNK_TARGET_CHARS = int(os.getenv("CHUNK_TARGET_CHARS", "1200"))
CHUNK_OVERLAP_CHARS = int(os.getenv("CHUNK_OVERLAP_CHARS", "150"))


def ensure_dirs() -> None:
    for d in (NOTES_DIR, TEXTS_DIR, ARTICLES_DIR, GRAPH_DIR, LOG_DIR):
        d.mkdir(parents=True, exist_ok=True)
