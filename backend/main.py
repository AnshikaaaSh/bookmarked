"""FastAPI app — serves the API and the frontend.

    uvicorn backend.main:app --reload

Route status:
  /api/ask              real — a LangGraph agent that decides for itself
                        whether to search the library, the web, or both
                        (build-order step 3)
  /api/sources          real
  /api/progress         real — persisted per-book reading position (FR7),
                        shared between the Ask and Graph tabs
  /api/graph/{id}       real store + filter — extraction is real
                        (build-order step 4); run backend/scripts/extract_graph.py
                        per book you want graphed
  /api/recommend        real — library-informed, web-grounded reasoning,
                        structured output (feature 2.5, build-order step 3)
  /api/write/outline    real — library + web grounded outline drafting,
                        structured output (feature 2.4, build-order step 6),
                        category picks a persona voice (or, for "poetry",
                        an entirely different output shape)
  /api/write/piece      real — expands an outline/poem draft into the actual
                        finished text; plain completion, no new retrieval
  /api/write/rewrite    real — regenerates one passage (a bullet, a poem
                        line, a whole piece), optionally steered by feedback;
                        NOT cached on purpose, see below

Ask, Recommend, Write/outline, and Write/piece all cache their response for
24h, keyed on the request + model (NFR2) — an identical repeated question
skips the LLM call entirely. Responses carry `"cached": true/false` so the
frontend/caller can tell. See backend/cache.py; `python -m
backend.scripts.clear_cache` busts it. Write/rewrite is deliberately excluded:
a cached "regenerate this" would deterministically return the same text every
time, defeating the point of asking again.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import cache
from .agent import ask as ask_library
from .agent import draft_outline
from .agent import recommend as recommend_agent
from .agent import rewrite as rewrite_text
from .agent import write_piece
from .config import ANSWER_MODEL, FRONTEND_DIR, LLM_PROVIDER, ensure_dirs
from .ingestion import ingest_all
from .llm import LLMUnavailableError, MissingAPIKey
from .schemas import (
    AskRequest,
    OutlineRequest,
    PieceRequest,
    ProgressRequest,
    RecommendRequest,
    RewriteRequest,
)
from .store import get_progress_store, get_store
from .store.graph_store import get_graph_store

@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_dirs()
    yield


app = FastAPI(title="bookmarked", version="0.1.0", lifespan=lifespan)

# Only needed if you open the HTML from disk instead of through this server.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def no_cache_frontend(request, call_next):
    """StaticFiles' default headers let browsers cache app.js/styles.css
    aggressively enough that an edit here can silently keep serving the old
    file until a hard refresh — confusing during active frontend iteration,
    since the server is verifiably serving the new file the whole time.
    Force revalidation on every load instead."""
    response = await call_next(request)
    if not request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store"
    return response


# --- API -----------------------------------------------------------------


@app.get("/api/health")
def health() -> dict:
    store = get_store()
    return {
        "status": "ok",
        "chunks": store.count(),
        "provider": LLM_PROVIDER,
        "answer_model": ANSWER_MODEL,
    }


@app.get("/api/sources")
def sources() -> dict:
    return {"sources": get_store().list_sources()}


@app.get("/api/progress")
def progress() -> dict:
    """Every book with a saved reading position. {} for anything not yet set —
    the frontend treats that as 'no position set' (unscoped Ask, position=1 in
    Graph), not an error."""
    return {"progress": get_progress_store().all()}


@app.put("/api/progress/{source_id}")
def set_progress(source_id: str, request: ProgressRequest) -> dict:
    if source_id not in {s["source_id"] for s in get_store().list_sources()}:
        raise HTTPException(status_code=404, detail=f"No source '{source_id}' in the library.")
    get_progress_store().set(source_id, request.position)
    return {"source_id": source_id, "position": request.position}


@app.post("/api/ingest")
def ingest() -> dict:
    """Re-ingest everything under data/. Safe to run repeatedly — sources are replaced."""
    reports = ingest_all(get_store())
    return {
        "ingested": [r.__dict__ for r in reports if r.ok],
        "failed": [r.__dict__ for r in reports if not r.ok],
    }


@app.post("/api/ask")
def ask(request: AskRequest) -> dict:
    key = {
        "question": request.question,
        "source_id": request.source_id,
        "position": request.position,
        "model": ANSWER_MODEL,
    }
    if cached := cache.get("ask", key):
        return {**cached, "cached": True}
    try:
        result = ask_library(
            request.question,
            source_id=request.source_id,
            position=request.position,
        ).to_dict()
    except (MissingAPIKey, LLMUnavailableError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    cache.set("ask", key, result)
    return {**result, "cached": False}


@app.post("/api/recommend")
def recommend(request: RecommendRequest) -> dict:
    key = {"liked": request.liked, "model": ANSWER_MODEL}
    if cached := cache.get("recommend", key):
        return {**cached, "cached": True}
    try:
        result = recommend_agent(request.liked).to_dict()
    except (MissingAPIKey, LLMUnavailableError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    cache.set("recommend", key, result)
    return {**result, "cached": False}


@app.post("/api/write/outline")
def outline(request: OutlineRequest) -> dict:
    key = {"topic": request.topic, "category": request.category, "model": ANSWER_MODEL}
    if cached := cache.get("write", key):
        return {**cached, "cached": True}
    try:
        result = draft_outline(request.topic, category=request.category).to_dict()
    except (MissingAPIKey, LLMUnavailableError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    cache.set("write", key, result)
    return {**result, "cached": False}


@app.post("/api/write/piece")
def piece(request: PieceRequest) -> dict:
    key = {
        "topic": request.topic,
        "category": request.category,
        "title": request.title,
        "outline": request.outline,
        "sources": request.sources,
        "themes": request.themes,
        "mood": request.mood,
        "form": request.form,
        "model": ANSWER_MODEL,
    }
    if cached := cache.get("write_piece", key):
        return {**cached, "cached": True}
    try:
        result = write_piece(
            request.topic,
            category=request.category,
            title=request.title,
            outline=request.outline,
            sources=request.sources,
            themes=request.themes,
            mood=request.mood,
            form=request.form,
        ).to_dict()
    except (MissingAPIKey, LLMUnavailableError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    cache.set("write_piece", key, result)
    return {**result, "cached": False}


@app.post("/api/write/rewrite")
def rewrite(request: RewriteRequest) -> dict:
    # Not cached — see module docstring.
    try:
        result = rewrite_text(
            request.topic,
            request.category,
            request.text,
            context=request.context,
            feedback=request.feedback,
        ).to_dict()
    except (MissingAPIKey, LLMUnavailableError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {**result, "cached": False}


@app.get("/api/graph/{source_id}")
def graph(source_id: str, position: int | None = Query(None, ge=0)) -> dict:
    """The character graph as of `position`. Never returns later entities (FR9).

    Omit `position` to use the reader's saved progress for this book — the
    same value Ask uses, so opening Graph after asking a scoped question (or
    vice versa) picks up where you left off instead of resetting to chapter 1.
    """
    store = get_graph_store()
    if not store.exists(source_id):
        raise HTTPException(
            status_code=404,
            detail=(
                f"No character graph for '{source_id}' yet. Run "
                f"`python -m backend.scripts.extract_graph {source_id}` to build one."
            ),
        )
    if position is None:
        position = get_progress_store().get(source_id) or 1
    return store.view(source_id, position)


@app.get("/api/graphs")
def graphs() -> dict:
    """Which books currently have a character graph."""
    from .config import GRAPH_DIR

    return {"graphs": sorted(p.stem for p in GRAPH_DIR.glob("*.json"))}


# --- Frontend ------------------------------------------------------------
# Mounted last so it never shadows an /api route.
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
