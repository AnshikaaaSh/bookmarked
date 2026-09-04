# bookmarked

A personal reading companion: ask questions across everything you've read, get
recommendations with real reasoning, draft posts grounded in your own library, and
browse a character graph that never shows you anything past the chapter you're on.

Full project plan: [reading-companion-agent-plan.md](reading-companion-agent-plan.md)

---

## Quick start

Uses a project-local virtual environment — this project's dependencies (LangGraph
especially) move fast and will conflict with other Python projects on your machine
if installed into a shared/base environment. Always run things through `.venv`,
not your system `python3`.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

cp .env.example .env          # add your GEMINI_API_KEY (free — see Models below)

# Try it with the sample library first
cp data/samples/book-notes.sample.md data/books/thinking-in-systems.md
cp data/samples/article.sample.md    data/articles/second-order-thinking.md
cp data/samples/novel.sample.txt     data/texts/sample-novel.txt

.venv/bin/python -m backend.scripts.ingest
.venv/bin/uvicorn backend.main:app --reload
```

Or activate the venv once per shell (`source .venv/bin/activate`) and drop the
`.venv/bin/` prefix for the rest of the session.

Open http://127.0.0.1:8000 and ask *"What have I read about second-order thinking?"*

The first ingest downloads a ~80 MB local embedding model (once, cached in
`~/.cache/chroma`). No API key needed for embedding — only for answering.

---

## Adding your own library

Three folders, three formats. **The folder decides how the file is parsed**, so put
each file in the right one.

### `data/books/` — notes & highlights

The main RAG corpus. One file per book, chapters as `## Chapter N` headings.

```markdown
---
title: Thinking in Systems
author: Donella Meadows
---

## Chapter 2

- Feedback loops are where behaviour comes from.
- Second-order thinking means tracing a decision's ripple effects before acting.

## Chapter 6

- The strongest leverage point is the paradigm the system arises from.
```

Frontmatter is optional (title falls back to the filename). Chapter headings are
optional too, but without them everything lands at position 0 and you lose the
ability to scope answers by reading progress.

**15–20 highlights per book is plenty** to make the Ask flow work well.

### `data/texts/` — full narrative text

Only needed for the character graph, which requires continuous prose rather than
sparse highlights. Chapters are detected from the text itself — `## Chapter 3`,
`CHAPTER III`, `CHAPTER ONE`, or `CHAPTER V: A Title` all work.

**From a PDF**, use the importer rather than pasting text in by hand:

```bash
# Always dry-run first — check what it detected before writing
python -m backend.scripts.import_pdf ~/Downloads/*.pdf --dry-run

python -m backend.scripts.import_pdf ~/Downloads/book.pdf
python -m backend.scripts.ingest
```

It strips running headers/footers, rejoins PDF line wrapping into real paragraphs,
skips the table of contents, and assigns positions:

- **Chapter positions** when the book's body has detectable chapter headings. The
  book's own numbers are kept when they run strictly upward, so "chapter 10" in the
  UI is chapter 10 in your hands. Books that restart numbering inside each PART
  (Crime and Punishment) fall back to a running count, because a position that goes
  backwards would break the `position <= reader_position` bound.
- **Page positions** when it can't find reliable chapter markers — plenty of
  commercial ebook PDFs mark chapters with styling that leaves no textual trace.
  The plan's "chapter/page position" (NFR1) is meant literally; page bounds are
  just as spoiler-safe, and arguably easier to set from a physical book.

Force either with `--mode chapters` / `--mode pages`. Scanned PDFs are rejected
with a clear error — they'd need OCR, which this importer doesn't do.

Project Gutenberg `.txt` files also work directly, and are cleaner than any PDF
extraction — worth preferring for public-domain titles.

### `data/articles/` — saved blog posts

```markdown
---
title: Second-Order Thinking
author: Farnam Street
url: https://fs.blog/second-order-thinking/
---

Article text here…
```

Articles have no chapters, so they're always visible regardless of reading position.

### Then

```bash
python -m backend.scripts.ingest                    # everything under data/
python -m backend.scripts.ingest data/books/foo.md  # just one file
```

Re-running is safe: a source is deleted and rewritten, never duplicated. Your
library files are gitignored — the samples and folder structure are not.

---

## How the spoiler safety works

This is the design constraint the whole project is built around, so it's enforced in
the data layer, not the prompt:

1. Every chunk is tagged with its chapter at ingestion time
   ([`ingestion/loaders.py`](backend/ingestion/loaders.py)).
2. Retrieval takes a `max_position` argument that becomes a hard `where` clause on
   the vector query ([`store/vector_store.py`](backend/store/vector_store.py)).
3. Graph nodes and edges carry `introduced_at`, and `view(position)` filters on it
   ([`store/graph_store.py`](backend/store/graph_store.py)).
4. When a reading `position` is set, the agent's `search_web` tool is never
   constructed at all ([`agent/tools.py`](backend/agent/tools.py)) — the model
   can't reach the live web for a spoiler-scoped question because the tool
   doesn't exist in that turn, not because it was told not to use it.

A later chapter is never retrieved, so the model can't leak it even if asked to.
The graph merge is incremental and keeps the *earliest* introduction for an entity —
a character met in chapter 2 doesn't get pushed to chapter 9 when they reappear.

This held up under a live test worth knowing about: with a position set, the model
still *tried* calling `search_web` once (an earlier prompt draft mentioned it
unconditionally). The framework rejected the call — "not a valid tool" — before it
ever ran, so nothing actually reached the web. The prompt is now built dynamically
per request and only mentions tools that actually exist for that call, so the model
doesn't waste a turn on a call that's guaranteed to fail.

Confirmed automatically now, not just by hand: the eval harness (below) includes
regression cases for exactly this — a chapter-scoped question that can't be
answered from what's available must not reach for the web, and a citation must
never exceed the position bound. All 15 cases pass, including these.

## Character extraction

```bash
python -m backend.scripts.extract_graph the-great-gatsby
python -m backend.scripts.extract_graph anne-of-green-gables --through 20   # partial
```

One structured-output LLM call over the book's full text
([`agent/extract_agent.py`](backend/agent/extract_agent.py)), returning every
character and relationship along with the position each is first established at.
Two things worth knowing:

- **The extraction call sees the whole book; the reader never does.** Spoiler
  safety doesn't depend on the model extracting less — it depends on
  `GraphStore.view(position)` only returning nodes/edges whose `introduced_at`
  is at or before the reader's position (same principle as Ask's retrieval
  filter). Seeing the whole book in one pass is more accurate and far cheaper
  than one call per chapter, and it's just as safe, because what the model saw
  while extracting has no bearing on what the view layer later shows.
- **A relationship graph isn't a cast list.** The first real run over Anne of
  Green Gables asked for "every named character, however minor" and got back
  86 — 58 of them one-off classmates from a school roster, connected to nothing.
  Fixed two ways: the prompt now asks specifically for characters with an
  established relationship (or the protagonist), and `extract()` drops any
  non-main character with zero edges as a structural backstop regardless of
  whether the model complies. Re-running produced 14 real, connected characters.

Safe to re-run or extend: `GraphStore.merge()` keeps each entity's *earliest*
seen position rather than overwriting, so extracting through chapter 20 after
already extracting through chapter 10 adds new characters without disturbing
ones already placed.

## Evaluation

```bash
python -m backend.scripts.eval                       # all cases
python -m backend.scripts.eval --id gatsby-narrator   # just one
```

A JSON file of test cases ([`data/eval/cases.json`](data/eval/cases.json)) plus
a scoring script ([`backend/scripts/eval.py`](backend/scripts/eval.py)) —
deliberately not RAGAS or another framework (NFR3 explicitly asks for something
lightweight and explainable, not a heavy dependency). Each case can assert:

- `expect_keywords` / `expect_no_keywords` — answer faithfulness
- `expect_web` — did the agent correctly decide to search the web or not
- `expect_max_citation_position` — the spoiler bound, checked automatically

15/15 currently pass. Two cases needed fixing during development in a way
worth knowing about if you add more: a case asserting `expect_no_keywords:
["Gilbert"]` failed when the question itself asked "what happens with Gilbert
Blythe" — the model correctly said it didn't know, but naturally echoed the
name back from the question, which isn't a real leak. Rephrasing questions to
not contain the forbidden keyword themselves makes the assertion mean what it's
supposed to mean.

---

## Layout

```
backend/
  config.py            paths, model ids, chunking knobs
  main.py              FastAPI app + routes (also serves the frontend)
  schemas.py           request models
  trace.py             JSONL agent traces -> logs/traces.jsonl
  ingestion/           loaders (chapter detection) -> chunker -> pipeline
  store/               vector_store.py (Chroma), graph_store.py (NetworkX)
  llm/                 raw single-completion path (providers.py) — used where
                        no tool-calling is needed, e.g. scripts/check_llm.py
  tools/               web_search.py — Tavily client, shared by the agents
  agent/               model.py picks the LangChain chat model per provider;
                        tools.py builds search_library/search_web per request;
                        ask_agent.py       Flow A — ReAct loop + citations
                        recommend_agent.py Flow B — structured recommendations
                        write_agent.py     Flow C — structured outline drafts
                        extract_agent.py   character/relationship extraction
  scripts/
    ingest.py           embed everything under data/
    import_pdf.py       convert a book PDF to position-marked text
    extract_graph.py    run character extraction for one book
    eval.py             run the eval harness (data/eval/cases.json)
    check_llm.py        verify the model/API-key setup
frontend/
  index.html, styles.css, js/{api,app}.js
data/
  books/ texts/ articles/    your library (gitignored)
  samples/                   format examples
  graphs/                    one JSON character graph per book
  eval/cases.json            eval harness test cases
```

## Build status

Every feature in the plan is real — nothing left stubbed.

| Feature | Endpoint | Notes |
|---|---|---|
| Ask my library, agentic (Flow A, 2.1–2.3) | `POST /api/ask` | The model decides for itself whether to search the library, the web, or both |
| Recommendations (2.5) | `POST /api/recommend` | Checks the library for notes on the liked book first, then searches the web for candidates; structured `{title, author, reason}` output |
| Writing assist (2.4) | `POST /api/write/outline` | Same pattern — library + web, structured outline + sources |
| Character graph (2.6) | `GET /api/graph/{id}` | Extraction is a separate offline step — see below — not automatic on ingest |
| Library listing | `GET /api/sources` | |

Run `python -m backend.scripts.extract_graph <source_id>` per book you want
graphed — it's one LLM call, not part of ingest, matching NFR6 ("async/background
acceptable for character extraction"). Two are extracted already as a demo set
(`the-great-gatsby`, `anne-of-green-gables`); run it on any other ingested book.

## Models & providers

Embeddings run locally and are free — the provider below only affects answer
generation, which is the only part that can cost anything.

```bash
# .env
LLM_PROVIDER=gemini        # gemini (free tier) | anthropic
GEMINI_API_KEY=...         # free key: https://aistudio.google.com/apikey
TAVILY_API_KEY=...         # free key (1000/month): https://app.tavily.com
```

Verify the setup before running the app:

```bash
python -m backend.scripts.check_llm          # sends one tiny test prompt
python -m backend.scripts.check_llm --list   # models your key can use
```

| Provider | Default answer model | Notes |
|---|---|---|
| `gemini` | `gemini-flash-lite-latest` | Free tier. `gemini-flash-latest` looks like the obvious default but currently resolves to a model with a **20-requests/day** free quota — confirmed by hitting it during development. The lite variant handled sustained testing fine; bump `ANSWER_MODEL` if you have paid quota. |
| `anthropic` | `claude-opus-5` | Paid (~$0.01/question). Best quality. |

Override either model with `ANSWER_MODEL` / `EXTRACTION_MODEL`. `EXTRACTION_MODEL`
runs in background jobs where quality matters more than latency, because
extraction errors compound into the character graph.

Two separate model-calling paths exist on purpose:
[backend/llm/providers.py](backend/llm/providers.py) is a plain single-completion
call (used by `check_llm` and anything that doesn't need tools); the Ask agent
uses LangChain chat model wrappers instead ([backend/agent/model.py](backend/agent/model.py))
because `create_agent` requires one. `LLM_PROVIDER`/`ANSWER_MODEL` in `.env` drive
both paths identically — provider selection is still one flag for the whole app.

## Traces

Every Ask, Recommend, Write, and extraction run writes one line to
`logs/traces.jsonl`: what was asked, how many times each tool was called,
what got cited, the answer, and latency.

```bash
tail -1 logs/traces.jsonl | python3 -m json.tool
```

## Next up

The build order in the plan is complete. What's left is content, not code:

- Run `extract_graph.py` on more of your ingested books — only two have a
  character graph so far.
- Add real AI/GenAI articles to `data/articles/` — Write and Recommend work
  today, but without library coverage on your actual writing topics they lean
  entirely on the web tool rather than drawing on anything you've actually read.
- Grow `data/eval/cases.json` past 15 cases as you find real questions that
  trip up an answer — that's what turns the harness from a one-time check into
  an actual regression suite.
