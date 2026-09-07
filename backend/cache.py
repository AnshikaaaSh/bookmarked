"""A lightweight response cache (NFR2 — "cache repeated queries... to control cost").

One file per cache entry under data/cache/<namespace>/, keyed by a hash of the
request itself. Deliberately not Redis or an in-memory LRU: this project's
established pattern for small persistent state is a JSON file (graphs,
progress), and a cache that survives a server restart is more useful for a
personal, occasionally-restarted app than one that doesn't.

TTL-based, not invalidated by library changes — the tradeoff NFR2 actually
asks for is cost control, not perfect freshness. A day is long enough to
absorb repeated identical questions (which is what actually happened
repeatedly during development and eval runs) without serving badly stale
web-grounded content for long.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from .config import DATA_DIR

CACHE_DIR = DATA_DIR / "cache"
DEFAULT_TTL_SECONDS = 24 * 60 * 60  # 1 day


def _key_path(namespace: str, key: dict[str, Any]) -> Path:
    payload = json.dumps(key, sort_keys=True, default=str)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
    return CACHE_DIR / namespace / f"{digest}.json"


def get(namespace: str, key: dict[str, Any], ttl_seconds: int = DEFAULT_TTL_SECONDS) -> dict | None:
    path = _key_path(namespace, key)
    if not path.exists():
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if time.time() - record.get("cached_at", 0) > ttl_seconds:
        return None
    return record.get("value")


def set(namespace: str, key: dict[str, Any], value: dict) -> None:
    path = _key_path(namespace, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"cached_at": time.time(), "value": value}, indent=2, default=str),
        encoding="utf-8",
    )


def clear(namespace: str | None = None) -> int:
    """Delete cached entries — everything, or just one namespace. Returns the
    count removed. Call this after re-ingesting a book whose answers you know
    changed; TTL alone won't catch that."""
    target = CACHE_DIR / namespace if namespace else CACHE_DIR
    if not target.exists():
        return 0
    count = 0
    for f in target.rglob("*.json"):
        f.unlink()
        count += 1
    return count
