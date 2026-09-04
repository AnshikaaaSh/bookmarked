"""Extract a character graph from an ingested book and merge it into the store.

    python -m backend.scripts.extract_graph the-great-gatsby
    python -m backend.scripts.extract_graph anne-of-green-gables --through 10

This is an offline background job (NFR6) — it makes one LLM call over the
book's text (or the position range given by --through), so run it once after
ingesting a book, not from a request handler. Safe to re-run: GraphStore.merge()
keeps each character's *earliest* seen introduction rather than duplicating or
overwriting (see store/graph_store.py).

`source_id` is the filename stem under data/texts/ (e.g. `the-great-gatsby.txt`
-> `the-great-gatsby`), or check `GET /api/sources` while the server's running.
"""

from __future__ import annotations

import argparse
import sys

from ..agent.extract_agent import extract
from ..llm.providers import LLMConfigError, LLMUnavailableError
from ..store.graph_store import get_graph_store


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract a character graph for one book.")
    parser.add_argument("source_id")
    parser.add_argument(
        "--through", type=int, default=None, metavar="POSITION",
        help="Only process up through this chapter/page (default: the whole book).",
    )
    parser.add_argument(
        "--from-position", type=int, default=0, metavar="POSITION",
        help="Skip everything before this position (default: 0, the start).",
    )
    args = parser.parse_args(argv)

    print(f"Extracting '{args.source_id}'"
          f"{f' through position {args.through}' if args.through else ' (whole book)'}...")
    print("This makes one LLM call over the book's text — may take a minute for a long book.")

    try:
        nodes, edges, chunks_processed = extract(args.source_id, args.from_position, args.through)
    except ValueError as exc:
        print(f"FAIL  {exc}")
        return 1
    except (LLMConfigError, LLMUnavailableError) as exc:
        print(f"FAIL  {exc}")
        return 1

    graph_store = get_graph_store()
    graph = graph_store.merge(args.source_id, nodes, edges)

    print(f"\n  processed {chunks_processed} chunks")
    print(f"  found {len(nodes)} characters, {len(edges)} relationships this run")
    print(f"  graph now holds {graph.number_of_nodes()} characters, "
          f"{graph.number_of_edges()} relationships total")
    print(f"\n  saved to data/graphs/{args.source_id}.json")
    print(f"  view it: GET /api/graph/{args.source_id}?position=<chapter>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
