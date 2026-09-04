"""Ingest everything under data/ into the vector store.

    python -m backend.scripts.ingest              # everything
    python -m backend.scripts.ingest data/books/thinking-in-systems.md

Safe to re-run: a source is deleted and rewritten, never duplicated.
"""

from __future__ import annotations

import sys
from pathlib import Path

from ..config import ensure_dirs
from ..ingestion import ingest_all, ingest_file
from ..store import get_store


def main(argv: list[str]) -> int:
    ensure_dirs()
    store = get_store()

    if argv:
        reports = [ingest_file(Path(arg).resolve(), store) for arg in argv]
    else:
        reports = ingest_all(store)

    if not reports:
        print("Nothing to ingest. Add files under data/books, data/texts, or data/articles.")
        print("See README.md for the file formats.")
        return 0

    failures = 0
    for report in reports:
        if report.ok:
            chapters = f", {report.chapters} chapters" if report.chapters else ""
            print(f"  ok   {report.title}  ({report.chunks} chunks{chapters})")
        else:
            failures += 1
            print(f"  FAIL {report.title}\n       {report.error}")

    print(f"\nLibrary now holds {store.count()} chunks across {len(store.list_sources())} sources.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
