"""Tavily web search — the fallback source when the library doesn't cover a
question, and the candidate-info source for recommendations (feature 2.5).

Results are untrusted external content (NFR5): callers must pass them to the
model as clearly-labeled DATA, never let their text be interpreted as
instructions. See how SYSTEM in rag/ask.py frames excerpts for the pattern.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

_ENDPOINT = "https://api.tavily.com/search"


class WebSearchConfigError(RuntimeError):
    """Missing or invalid Tavily setup — the user can fix this."""


class WebSearchError(RuntimeError):
    """The request reached Tavily but failed (rate limit, timeout, 5xx)."""


@dataclass
class WebResult:
    title: str
    url: str
    content: str
    score: float

    @property
    def citation(self) -> str:
        return self.title or self.url


def _api_key() -> str:
    key = os.getenv("TAVILY_API_KEY")
    if not key:
        raise WebSearchConfigError(
            "TAVILY_API_KEY is not set. Get a free key (1000 searches/month) at "
            "https://app.tavily.com and put it in .env"
        )
    return key


def search(query: str, max_results: int = 5) -> list[WebResult]:
    """Run one web search. Raises WebSearchConfigError / WebSearchError on failure —
    callers decide whether a failed search should degrade gracefully or surface."""
    try:
        response = httpx.post(
            _ENDPOINT,
            headers={"Authorization": f"Bearer {_api_key()}"},
            json={
                "query": query,
                "search_depth": "basic",
                "max_results": max_results,
                "include_answer": False,
            },
            timeout=15.0,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status == 401:
            raise WebSearchConfigError(
                "Tavily rejected the API key. Check TAVILY_API_KEY in .env."
            ) from exc
        if status == 432 or status == 429:
            raise WebSearchError(
                "Tavily's free-tier quota is used up for this period."
            ) from exc
        raise WebSearchError(f"Tavily returned {status}: {exc.response.text[:200]}") from exc
    except httpx.HTTPError as exc:
        raise WebSearchError(f"Couldn't reach Tavily: {exc}") from exc

    data = response.json()
    return [
        WebResult(
            title=r.get("title", ""),
            url=r.get("url", ""),
            content=r.get("content", ""),
            score=float(r.get("score", 0.0)),
        )
        for r in data.get("results", [])
    ]
