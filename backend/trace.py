"""Append-only JSONL trace log (NFR4).

Every agent run writes one line: what was asked, what came back from retrieval,
what the model said, how long it took. Cheap to add now, and it's what you'll
read when an answer looks wrong three weeks from now.

    tail -f logs/traces.jsonl | python3 -m json.tool
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

from .config import LOG_DIR

TRACE_FILE = LOG_DIR / "traces.jsonl"


def log_trace(kind: str, payload: dict[str, Any]) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "kind": kind,
        **payload,
    }
    with TRACE_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


class Timer:
    """`with Timer() as t: ...` then read `t.ms`."""

    def __enter__(self) -> "Timer":
        self._start = time.perf_counter()
        return self

    def __exit__(self, *exc) -> None:
        self.ms = round((time.perf_counter() - self._start) * 1000)
