"""Ingestion pipeline: file -> sections -> position-tagged chunks -> vector store."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config import ARTICLES_DIR, NOTES_DIR, TEXTS_DIR
from .chunker import chunk_sections
from .loaders import load_article, load_full_text, load_notes

_LOADERS = {
    NOTES_DIR: load_notes,
    TEXTS_DIR: load_full_text,
    ARTICLES_DIR: load_article,
}

_SUPPORTED_SUFFIXES = {".md", ".txt", ".markdown"}


@dataclass
class IngestReport:
    source_id: str
    title: str
    source_type: str
    chunks: int
    chapters: int
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error


def _loader_for(path: Path):
    for directory, loader in _LOADERS.items():
        if directory in path.parents:
            return loader
    raise ValueError(
        f"{path} is not under data/books, data/texts, or data/articles — "
        f"the directory determines how the file is parsed."
    )


def ingest_file(path: Path, store) -> IngestReport:
    """Ingest one file, replacing anything already stored for that source."""
    loader = _loader_for(path)
    try:
        source, sections = loader(path)
    except ValueError as exc:
        return IngestReport(path.stem, path.stem, "", 0, 0, error=str(exc))

    chunks = chunk_sections(sections)
    written = store.upsert_source(source, chunks)
    return IngestReport(
        source_id=source.source_id,
        title=source.title,
        source_type=source.source_type,
        chunks=written,
        chapters=len({c.position for c in chunks if c.position > 0}),
    )


def ingest_all(store) -> list[IngestReport]:
    """Ingest every supported file under data/."""
    reports: list[IngestReport] = []
    for directory in _LOADERS:
        if not directory.exists():
            continue
        for path in sorted(directory.iterdir()):
            if path.is_file() and path.suffix.lower() in _SUPPORTED_SUFFIXES:
                reports.append(ingest_file(path, store))
    return reports
