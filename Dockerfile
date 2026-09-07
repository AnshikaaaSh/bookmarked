# Portable across hosts that inject their own port (Render sets $PORT;
# render.yaml at the repo root points here) and Hugging Face Spaces' Docker
# SDK, which expects a fixed 7860 and never sets $PORT — the ${PORT:-7860}
# default in CMD covers both without two Dockerfiles.

FROM python:3.11-slim

# chromadb pulls in a couple of packages (e.g. hnswlib) that need a compiler
# to build from source on slim images — installed only for the pip install
# layer, not needed at runtime, but keeping it simple over trimming the image.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Spaces run containers as a non-root user; give that user ownership of the
# app directory so the local embedding model cache and .chroma/ (both
# written at runtime) don't hit a permissions error.
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# Cache dir for the local embedding model (see README's "Quick start" —
# normally ~/.cache/chroma) needs to resolve somewhere writable for
# whichever user HF actually runs as.
ENV HOME=/app

EXPOSE 7860
# `exec` replaces the shell process with uvicorn (same PID) so SIGTERM from
# the host reaches it directly — shell form is needed for ${PORT:-7860}
# expansion, but without `exec` the shell swallows the signal and the
# platform has to wait out its full kill timeout on every deploy/restart.
CMD exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-7860}
