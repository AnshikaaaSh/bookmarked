import logging
import os
from pathlib import Path

from dotenv import load_dotenv

# Loaded here, at the package root, so every submodule sees .env regardless of
# which one happens to get imported first — os.getenv() in a leaf module (e.g.
# tools/web_search.py) previously returned nothing unless something else had
# already imported backend.config first as a side effect.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Chroma 0.5.x ships a telemetry hook that's incompatible with recent posthog
# releases: it raises on every call and logs "Failed to send telemetry event",
# which drowns real output. The setting alone doesn't stop the attempt, so also
# silence the logger. Both must happen before chromadb is imported.
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
logging.getLogger("chromadb.telemetry.product.posthog").setLevel(logging.CRITICAL)
