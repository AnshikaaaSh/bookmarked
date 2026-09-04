"""FastAPI app — serves the API and the frontend.

    uvicorn backend.main:app --reload

Route status:
  /api/ask              real — a LangGraph agent that decides for itself
                        whether to search the library, the web, or both
                        (build-order step 3)
  /api/sources          real
  /api/graph/{id}       real store + filter — extraction is real
                        (build-order step 4); run backend/scripts/extract_graph.py
                        per book you want graphed
  /api/recommend        real — library-informed, web-grounded reasoning,
                        structured output (feature 2.5, build-order step 3)
  /api/write/outline    real — library + web grounded outline drafting,
                        structured output (feature 2.4, build-order step 6)
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .agent import ask as ask_library
from .agent import draft_outline
from .agent import recommend as recommend_agent
from .config import ANSWER_MODEL, FRONTEND_DIR, LLM_PROVIDER, ensure_dirs
from .ingestion import ingest_all
from .llm import LLMUnavailableError, MissingAPIKey
from .schemas import AskRequest, OutlineRequest, RecommendRequest
from .store import get_store
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
    try:
        return ask_library(
            request.question,
            source_id=request.source_id,
            position=request.position,
        ).to_dict()
    except (MissingAPIKey, LLMUnavailableError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/recommend")
def recommend(request: RecommendRequest) -> dict:
    try:
        return recommend_agent(request.liked).to_dict()
    except (MissingAPIKey, LLMUnavailableError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/write/outline")
def outline(request: OutlineRequest) -> dict:
    try:
        return draft_outline(request.topic).to_dict()
    except (MissingAPIKey, LLMUnavailableError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/graph/{source_id}")
def graph(source_id: str, position: int = Query(1, ge=0)) -> dict:
    """The character graph as of `position`. Never returns later entities (FR9)."""
    store = get_graph_store()
    if not store.exists(source_id):
        raise HTTPException(
            status_code=404,
            detail=(
                f"No character graph for '{source_id}' yet. Run "
                f"`python -m backend.scripts.extract_graph {source_id}` to build one."
            ),
        )
    return store.view(source_id, position)


@app.get("/api/graphs")
def graphs() -> dict:
    """Which books currently have a character graph."""
    from .config import GRAPH_DIR

    return {"graphs": sorted(p.stem for p in GRAPH_DIR.glob("*.json"))}


# --- Frontend ------------------------------------------------------------
# Mounted last so it never shadows an /api route.
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
