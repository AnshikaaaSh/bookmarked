"""Reading progress — one current position per book (FR7).

A single JSON file, matching the project's existing pattern for small
single-user state (graphs are one JSON file per book; this is one JSON file,
period, since progress across the whole library is small enough to hold in
memory). This is what makes position genuinely *persisted* rather than reset
every time a tab reloads — previously only the Graph tab's slider held a
position, and only for as long as the page stayed open.
"""

from __future__ import annotations

import json

from ..config import DATA_DIR

PROGRESS_FILE = DATA_DIR / "progress.json"


class ProgressStore:
    def __init__(self, path=None):
        self._path = path or PROGRESS_FILE

    def _load(self) -> dict[str, int]:
        if not self._path.exists():
            return {}
        return json.loads(self._path.read_text(encoding="utf-8"))

    def _save(self, data: dict[str, int]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    def all(self) -> dict[str, int]:
        return self._load()

    def get(self, source_id: str) -> int | None:
        return self._load().get(source_id)

    def set(self, source_id: str, position: int) -> None:
        data = self._load()
        data[source_id] = position
        self._save(data)


_store: ProgressStore | None = None


def get_progress_store() -> ProgressStore:
    global _store
    if _store is None:
        _store = ProgressStore()
    return _store
