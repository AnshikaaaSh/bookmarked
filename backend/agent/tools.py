"""Tool factory for the Ask agent.

Tools are built fresh per request (`build_tools`), not once at import time,
because `source_id` and `position` scope every library search for that specific
question. Both tools share one `registry` list via closure: each result gets a
citation number when it's returned, so numbering stays consistent across
however many tool calls the agent makes in one turn — including calling
search_library more than once, which is exactly what the "connect the dots"
reasoning (feature 2.3) looks like in practice.

Spoiler safety (NFR1) is enforced by construction, not instruction: when
`position` is set, `search_web` is never added to the tool list at all. The
model can't call a tool it was never given, which is a stronger guarantee than
a prompt telling it not to — see backend/rag/ask.py's older heuristic version
for the reasoning this carries forward.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from langchain_core.tools import tool

from ..config import TOP_K
from ..store import Retrieved, get_store
from ..tools import WebResult, WebSearchConfigError, WebSearchError
from ..tools import search as run_web_search


@dataclass
class CitationSource:
    kind: Literal["library", "web"]
    item: Retrieved | WebResult


def _format_library(chunk: Retrieved, number: int) -> str:
    header = f"[{number}] LIBRARY — {chunk.title}"
    if chunk.author:
        header += f" by {chunk.author}"
    if chunk.position > 0:
        header += f" — {chunk.position_label}"
    return f"{header}\n{chunk.text}"


def _format_web(result: WebResult, number: int) -> str:
    return f"[{number}] WEB — {result.title} ({result.url})\n{result.content}"


def build_tools(
    source_id: str | None, position: int | None, k: int = TOP_K
) -> tuple[list, list[CitationSource]]:
    """Return (tools, registry). `registry` fills in as tools are called during
    the agent run — read it after `agent.invoke()` to resolve citation numbers."""
    registry: list[CitationSource] = []
    store = get_store()

    @tool(response_format="content_and_artifact")
    def search_library(query: str) -> tuple[str, list[Retrieved]]:
        """Search the reader's personal library — their books, highlights, and
        saved articles — for passages relevant to `query`. Always try this
        before search_web. Call it more than once with different phrasings if
        the first search doesn't surface what you need, or to look for a
        second source that might connect to the first."""
        chunks = store.query(query, k=k, source_id=source_id, max_position=position)
        blocks = []
        for chunk in chunks:
            registry.append(CitationSource("library", chunk))
            blocks.append(_format_library(chunk, len(registry)))
        content = "\n\n---\n\n".join(blocks) if blocks else "No matching passages in the library."
        return content, chunks

    tools = [search_library]

    if position is None:
        # No reading-progress bound in play — safe to reach the live web.
        # (When `position` is set, this tool is simply never offered; see
        # the module docstring for why that's a hard constraint, not advice.)
        @tool(response_format="content_and_artifact")
        def search_web(query: str) -> tuple[str, list[WebResult]]:
            """Search the live web. Only use this when search_library doesn't
            cover the question — check the library first. Useful for current
            events, recent articles, or general-knowledge questions the
            reader's library wouldn't contain."""
            try:
                results = run_web_search(query)
            except (WebSearchConfigError, WebSearchError) as exc:
                return f"Web search unavailable: {exc}", []
            blocks = []
            for result in results:
                registry.append(CitationSource("web", result))
                blocks.append(_format_web(result, len(registry)))
            content = "\n\n---\n\n".join(blocks) if blocks else "No web results found."
            return content, results

        tools.append(search_web)

    return tools, registry
