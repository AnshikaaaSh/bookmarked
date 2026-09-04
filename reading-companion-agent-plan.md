# Reading Companion Agent — Project Plan

*A personal agentic RAG system built around your own reading and writing habits.*

---

## 1. The Ask (Idea)

You read books and blogs regularly, and you also write Medium posts on AI/GenAI industry topics twice a week. Today, these two habits are disconnected — what you read lives in your head (or scattered notes), and what you write starts from scratch each time.

**The idea**: build an agent that has "read everything you've read," can reason across your entire personal library (not just one book at a time), helps you discover connections between ideas, recommends what to read next with real reasoning behind it, and helps you turn your reading into your writing.

This is deliberately a **capstone project** — the goal is to demonstrate the full arc of what's been learned (RAG, agentic tool use, structured extraction, evaluation, guardrails) through something genuinely personal and used, not a templated tutorial clone.

> **Note on Nugen**: separately, a fine-tuning/alignment exercise was run on the Nugen platform (nugen.in) to train a healthcare-domain model — that work is unrelated to this capstone. What *is* relevant here is Nugen's public cookbook (RAG guide, Embeddings & Search guide, Agentic Workflows guide, Framework Integrations guide), which is being used as a provider/pattern source for specific components below, not as a replacement for the whole stack.

### Why this project (recap)
- **Differentiated**: most public projects in this space are either plain recommendation engines (no agentic reasoning) or single-book RAG chatbots (no cross-source reasoning). Nothing combines personal library RAG + live web reasoning + structured knowledge extraction + a writing pipeline.
- **Dogfooded**: built to actually be used regularly, not just demoed once.
- **Multi-faceted interview story**: three distinct, defensible technical challenges (progressive/spoiler-bounded RAG, structured relationship extraction, recommendation reasoning) from one cohesive project.

---

## 2. Core Features

### 2.1 Personal Library RAG
Ask questions across everything you've read — books (notes/highlights or full text) and saved blog/articles — and get answers grounded in *your* library, with citations back to the specific source.

- Example: *"What have I read about second-order thinking?"*
- Example: *"Which book made the point about compounding I'm trying to recall?"*

### 2.2 Live Web Reasoning
Pull in current articles on a topic (via a web search tool) and have the agent compare them against what's already in your personal library — flagging whether a new piece contradicts, extends, or repeats an idea you already have on file.

### 2.3 "Connect the Dots" Agent Step
Beyond simple retrieval + answer, an explicit reasoning step that looks for **connections across sources**: *"This idea in Article X echoes something in Book Y, Chapter 3."* This is the genuinely agentic part — multi-step reasoning across retrieved chunks, not single-shot RAG.

### 2.4 Writing-Assist Mode
Given a topic, retrieve relevant material from your own library + fresh web sources, and draft a blog post outline grounded in real citations to what you've actually read — feeding your recurring Medium habit.

### 2.5 "If You Liked This, You Might Like These" (LLM + Web Search Reasoning)
Not a plain similarity lookup — the agent uses **web search plus reasoning** to recommend books and *articulate why* each recommendation fits: what specifically about the book you liked (theme, structure, tone) connects to the recommendation, sourced from real current information about candidate books rather than relying only on pretrained knowledge.

### 2.6 Spoiler-Safe Character Relationship Graph
A graph of characters and their relationships **that only reflects the story up to the reader's current position** — no character appears until they've been properly introduced, and no relationship is shown before it's actually been established in the narrative. Inspired by Amazon Prime's X-Ray, but spoiler-bounded by reading progress rather than showing the full cast upfront.

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement |
|---|---|
| FR1 | User can add books/articles to their personal library (text upload, notes, or highlights) |
| FR2 | User can query their library in natural language and receive grounded, cited answers |
| FR3 | Agent can invoke web search to bring in current articles on a topic |
| FR4 | Agent can identify and surface connections between two or more sources in the library |
| FR5 | User can request a blog post outline on a topic, grounded in library + web sources |
| FR6 | Agent can recommend books based on a liked book, with reasoning, using web search for candidate info |
| FR7 | User can track reading progress (chapter/page) for a given book |
| FR8 | Agent extracts characters and relationships incrementally, bounded by reading progress |
| FR9 | Character graph never reveals a character/relationship ahead of the reader's current position |
| FR10 | User can view the character graph visually, updating as progress advances |

### 3.2 Non-Functional Requirements

| ID | Requirement |
|---|---|
| NFR1 | Retrieval must be filtered by chapter/page position for spoiler safety (hard constraint, not a soft prompt instruction) |
| NFR2 | System should cache repeated queries/extractions to control cost (Phase 7 principle) |
| NFR3 | An eval set (15–20 test cases with known-correct outcomes) should exist to measure retrieval hit rate and answer faithfulness |
| NFR4 | Agent traces (thought/action/observation logs) should be inspectable for debugging |
| NFR5 | Web search results and any externally-sourced content must be treated as untrusted data, never as instructions (prompt injection guardrail) |
| NFR6 | Reasonable latency for interactive use (target: under ~10s for simple queries, async/background acceptable for character extraction batch jobs) |

---

## 4. Design

### 4.1 Key User Flows

**Flow A — Ask my library**
1. User asks a question.
2. Agent retrieves relevant chunks from the vector store (personal library).
3. If library context is insufficient, agent decides to call web search.
4. Agent synthesizes an answer with citations, and — if relevant — flags a cross-source connection.

**Flow B — Get a recommendation**
1. User names a book they liked.
2. Agent identifies the book's themes/style (from library notes if available, else reasons from general knowledge).
3. Agent calls web search for current candidate books matching those themes.
4. Agent returns 2–3 recommendations, each with an explicit reasoning trace for *why*.

**Flow C — Draft a post**
1. User gives a topic.
2. Agent retrieves related library content + fresh web articles.
3. Agent drafts an outline with inline citations back to sources.

**Flow D — Read a book with the spoiler-safe graph**
1. User uploads/adds a book and sets current reading position.
2. Background job processes content up to that position, extracting characters/relationships incrementally (merging into an existing graph, not regenerating from scratch).
3. User views the graph — only entities/edges established up to their position appear.
4. As the user advances, the graph updates incrementally.

### 4.2 Spoiler-Safety Mechanism (the core design constraint)

This is enforced at the **retrieval layer**, not just the prompt:
- Every chunk is tagged with its position (chapter/page number) at ingestion time.
- Any retrieval or extraction call for graph-building is filtered with a hard metadata constraint: `position <= reader_current_position`.
- This mirrors a context-window discipline, applied as a permanent data filter rather than a token limit.

---

## 5. Architecture

```
                     ┌─────────────────────────┐
                     │   User Interface         │
                     │ (chat + graph view)      │
                     └───────────┬─────────────┘
                                 │
                     ┌───────────▼─────────────┐
                     │   Agent Orchestrator     │
                     │   (LangGraph)            │
                     └───────────┬─────────────┘
                 ┌───────────────┼──────────────────┐
                 │               │                  │
        ┌────────▼──────┐ ┌──────▼───────┐ ┌────────▼────────┐
        │ RAG Retrieval  │ │ Web Search    │ │ Character/Graph  │
        │ Tool           │ │ Tool          │ │ Extraction Tool  │
        └────────┬──────┘ └──────┬────────┘ └────────┬────────┘
                 │                │                    │
        ┌────────▼──────┐        │           ┌─────────▼────────┐
        │ Vector DB      │        │           │ Graph Store       │
        │ (Chroma)       │        │           │ (NetworkX)        │
        └────────┬──────┘        │           └──────────────────┘
                 │                │
        ┌────────▼────────────────▼────────┐
        │  Ingestion Pipeline                │
        │  (chunking + position tagging +    │
        │   embedding)                       │
        └────────────────────────────────────┘

        ┌─────────────────────────────────────┐
        │  Evaluation & Observability layer     │
        │  (trace logging, eval harness)        │
        └───────────────────────────────────────┘
```

### Component Notes
- **Agent Orchestrator (LangGraph)**: implements the ReAct-style loop, decides when to retrieve, search, extract, or recommend; handles the multi-step "connect the dots" reasoning.
- **RAG Retrieval Tool**: standard similarity search against the vector DB, always position-filtered for any book-specific query.
- **Web Search Tool**: for current articles and candidate book information (recommendation feature).
- **Character/Graph Extraction Tool**: structured-output LLM call, extracting `{character, relationship, established_at_position}` from chunks up to the current reading position; merges incrementally into the graph store.
- **Vector DB**: stores embedded chunks of books/articles/notes, tagged with source and position metadata.
- **Graph Store**: lightweight in-memory/persisted graph (NetworkX), one graph per book, keyed by position for the "as of chapter N" view.
- **Evaluation & Observability**: trace logs for every agent run, plus a small eval set to track retrieval hit rate and answer faithfulness over time.
- **Nugen (where it plugs in)**: the Embeddings/Search Tool and Vector DB step can optionally run against Nugen's Embeddings & Search API instead of Chroma + a local embedding model; the Web Search Tool used specifically by the recommendation feature (2.5) can follow Nugen's Agentic Workflows pattern (`/api/v3/inference/chat/completions`). Everything else (orchestrator, graph extraction, evaluation) stays as planned regardless of this choice.

---

## 6. Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Agent framework | **LangGraph** | Explicit graph-based control over the loop; matches what you're learning deeply in Phase 6 |
| LLM | **Claude (via Anthropic API)** | Strong reasoning + native tool use/structured output support |
| Vector DB | **Chroma** | Simple to run locally, sufficient for a personal-scale library, no infra overhead |
| Graph store | **NetworkX** (Python) | Lightweight, in-memory, no need for a full graph database at this scale |
| Backend | **FastAPI** | Clean way to expose the agent as an API; easy to add endpoints per feature |
| Frontend | **Streamlit** (fastest) or a simple **Next.js** app if you want more portfolio polish | Streamlit gets you a working demo fastest; Next.js looks more "product-like" if you have the time |
| Web search tool | Any search API (e.g., Tavily, SerpAPI, or Anthropic's own web search tool if using it directly) | Needed for live recommendation reasoning and current-article comparison |
| Embeddings & Search | **Nugen's Embeddings & Search API** (`nugen-cookbook` guide), or Sentence-transformers/Anthropic/OpenAI embeddings as a fallback | Nugen's guide covers embeddings + retrieval directly relevant to the library RAG (2.1) and recommendation (2.5) features; keep the open-source fallback in your back pocket in case the Nugen API has rough edges mid-build |
| Recommendation reasoning pattern | **Nugen's Agentic Workflows guide** (`inference/chat/completions`, OpenAI-style) | Matches the "LLM + web search reasoning" pattern already decided for feature 2.5 — worth prototyping against this guide before writing the tool from scratch |
| Framework integration (optional) | Nugen's Framework Integrations guide (LangChain/LlamaIndex) | Only relevant if you want Nugen as the model/embeddings *provider* underneath LangGraph, rather than calling Nugen's API directly — adds integration convenience at the cost of an extra abstraction layer |
| Evaluation | Lightweight custom harness (a JSON file of test Q&A pairs + a scoring script) | No need for a heavy framework like RAGAS at this scale — a simple custom harness is easier to explain in an interview anyway |
| Observability | Structured JSON logging of agent traces (thought/action/observation per step) | Simple, inspectable, no need for a dedicated observability platform yet |

---

## 7. Suggested Build Order

1. **Ingestion pipeline** — chunking + position tagging + embedding for a single test book/article set.
2. **Basic RAG query flow** (Flow A, without web search yet) — get "ask my library" working end-to-end.
3. **Add web search tool** — extend Flow A to fall back to web search; build Flow B (recommendations) next since it reuses the same tool.
4. **Character/graph extraction** — start with a single test book, get position-filtered extraction and incremental graph merging working.
5. **Graph visualization** — simple force-directed layout, even a basic one, to demonstrate the spoiler-safety mechanism visually.
6. **Writing-assist mode** (Flow C) — reuses RAG + web search, adds the outline-drafting step.
7. **Evaluation harness + trace logging** — retrofit onto everything once the core flows work, so you have real numbers and traces to show.

---

*This document is a living plan — expect the architecture to shift slightly once you're actually building, especially around the graph extraction step, which is the most experimental part.*
