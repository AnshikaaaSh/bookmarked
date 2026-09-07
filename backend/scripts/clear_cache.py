"""Clear the Ask/Recommend/Write response cache (NFR2).

    python -m backend.scripts.clear_cache            # everything
    python -m backend.scripts.clear_cache ask        # just one namespace

Cached entries expire after 24h on their own, but that won't catch a change
you made deliberately — re-ingesting a book with corrected notes, or wanting
a genuinely fresh web search on a topic you already asked about today. Run
this after either.
"""

from __future__ import annotations

import sys

from .. import cache


def main(argv: list[str] | None = None) -> int:
    namespace = argv[0] if argv else None
    count = cache.clear(namespace)
    scope = f"'{namespace}'" if namespace else "all namespaces"
    print(f"Cleared {count} cached entr{'y' if count == 1 else 'ies'} ({scope}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
