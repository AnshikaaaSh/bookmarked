"""Chroma-backed library store.

The spoiler-safety guarantee lives here (NFR1): `max_position` becomes a hard
`where` clause on the query, so out-of-range chunks are never returned to the
model in the first place. It is not a prompt instruction the model could ignore.

Embeddings use Chroma's bundled local model (ONNX all-MiniLM-L6-v2) — no API
key, no torch, good enough at personal-library scale. To swap in Nugen's
Embeddings API later, replace `_embedding_function()` with a Chroma
`EmbeddingFunction` that calls it; nothing else in the codebase changes.
"""

from __future__ import annotations

from dataclasses import dataclass

import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions

from ..config import CHROMA_DIR, COLLECTION, TOP_K
from ..ingestion.chunker import Chunk
from ..ingestion.loaders import Source


@dataclass
class Retrieved:
    """One chunk that came back from a query."""

    text: str
    source_id: str
    title: str
    author: str
    source_type: str
    position: int
    position_label: str
    position_unit: str
    url: str
    score: float

    @property
    def citation(self) -> str:
        """The short label the UI shows as a chip."""
        if self.source_type == "article":
            return self.title
        return f"{self.title} — {self.position_label}"


def _embedding_function():
    return embedding_functions.DefaultEmbeddingFunction()


class LibraryStore:
    def __init__(self, path: str | None = None, collection: str = COLLECTION):
        self._client = chromadb.PersistentClient(
            path=str(path or CHROMA_DIR),
            # Chroma 0.5.x's telemetry hook is broken and prints an error per call.
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=collection,
            embedding_function=_embedding_function(),
            metadata={"hnsw:space": "cosine"},
        )

    # --- Writing ---------------------------------------------------------

    def upsert_source(self, source: Source, chunks: list[Chunk]) -> int:
        """Replace everything stored for `source`, then add its chunks."""
        self.delete_source(source.source_id)
        if not chunks:
            return 0

        base = source.as_metadata()
        self._collection.add(
            ids=[f"{source.source_id}::{c.chunk_index}" for c in chunks],
            documents=[c.text for c in chunks],
            metadatas=[
                {
                    **base,
                    "position": c.position,
                    "position_label": c.position_label,
                    "chunk_index": c.chunk_index,
                }
                for c in chunks
            ],
        )
        return len(chunks)

    def delete_source(self, source_id: str) -> None:
        self._collection.delete(where={"source_id": source_id})

    # --- Reading ---------------------------------------------------------

    def query(
        self,
        question: str,
        k: int = TOP_K,
        source_id: str | None = None,
        max_position: int | None = None,
    ) -> list[Retrieved]:
        """Retrieve the k most similar chunks.

        `max_position` is the spoiler bound: pass the reader's current chapter
        and nothing from later in the book can come back.
        """
        where = _build_where(source_id, max_position)
        result = self._collection.query(
            query_texts=[question],
            n_results=k,
            where=where,
        )

        documents = result.get("documents") or [[]]
        metadatas = result.get("metadatas") or [[]]
        distances = result.get("distances") or [[]]
        if not documents or not documents[0]:
            return []

        retrieved = []
        for text, meta, distance in zip(documents[0], metadatas[0], distances[0]):
            retrieved.append(
                Retrieved(
                    text=text,
                    source_id=meta.get("source_id", ""),
                    title=meta.get("source_title", ""),
                    author=meta.get("author", ""),
                    source_type=meta.get("source_type", ""),
                    position=int(meta.get("position", 0)),
                    position_label=meta.get("position_label", ""),
                    position_unit=meta.get("position_unit", "chapter"),
                    url=meta.get("url", ""),
                    score=round(1.0 - float(distance), 4),  # cosine distance -> similarity
                )
            )
        return retrieved

    def get_source_span(
        self, source_id: str, min_position: int = 0, max_position: int | None = None
    ) -> list[Retrieved]:
        """All chunks for one source within a position range, in reading order.

        For character extraction, not Q&A — `query()` is a similarity search
        and doesn't guarantee order or completeness over a span; this reads
        every chunk directly via Chroma's `.get()`, which does neither ranking
        nor top-k truncation.
        """
        clauses = [{"source_id": source_id}, {"position": {"$gte": min_position}}]
        if max_position is not None:
            clauses.append({"position": {"$lte": max_position}})
        result = self._collection.get(where={"$and": clauses}, include=["documents", "metadatas"])

        rows = list(zip(result.get("ids") or [], result.get("documents") or [], result.get("metadatas") or []))
        rows.sort(key=lambda row: int(row[2].get("chunk_index", 0)))

        return [
            Retrieved(
                text=doc,
                source_id=meta.get("source_id", ""),
                title=meta.get("source_title", ""),
                author=meta.get("author", ""),
                source_type=meta.get("source_type", ""),
                position=int(meta.get("position", 0)),
                position_label=meta.get("position_label", ""),
                position_unit=meta.get("position_unit", "chapter"),
                url=meta.get("url", ""),
                score=1.0,  # not a similarity result — every matching chunk is returned
            )
            for _id, doc, meta in rows
        ]

    def list_sources(self) -> list[dict]:
        """Every source in the library, with its chunk count and chapter range."""
        result = self._collection.get(include=["metadatas"])
        sources: dict[str, dict] = {}
        for meta in result.get("metadatas") or []:
            source_id = meta.get("source_id")
            if not source_id:
                continue
            entry = sources.setdefault(
                source_id,
                {
                    "source_id": source_id,
                    "title": meta.get("source_title", ""),
                    "author": meta.get("author", ""),
                    "source_type": meta.get("source_type", ""),
                    "url": meta.get("url", ""),
                    "position_unit": meta.get("position_unit", "chapter"),
                    "chunks": 0,
                    "max_position": 0,
                },
            )
            entry["chunks"] += 1
            entry["max_position"] = max(entry["max_position"], int(meta.get("position", 0)))
        return sorted(sources.values(), key=lambda s: s["title"].lower())

    def count(self) -> int:
        return self._collection.count()


def _build_where(source_id: str | None, max_position: int | None) -> dict | None:
    clauses: list[dict] = []
    if source_id:
        clauses.append({"source_id": source_id})
    if max_position is not None:
        clauses.append({"position": {"$lte": max_position}})
    if not clauses:
        return None
    return clauses[0] if len(clauses) == 1 else {"$and": clauses}


_store: LibraryStore | None = None


def get_store() -> LibraryStore:
    """Process-wide singleton — Chroma clients are expensive to construct."""
    global _store
    if _store is None:
        _store = LibraryStore()
    return _store
