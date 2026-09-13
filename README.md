# AI Travel Planner — Singapore

A RAG + MCP travel assistant for Singapore: a local LLM (Phi-3-mini via
Ollama) answers questions grounded in a scraped knowledge base of
official travel guides, augmented with live weather and currency data
fetched through MCP tool servers. Fully local, zero-cost stack — no
paid APIs, no cloud hosting.

## Architecture

```
                     ┌────────────┐
                     │  Streamlit │   src/ui
                     │     UI     │
                     └─────┬──────┘
                           │ HTTP (POST /chat)
                           ▼
                  ┌──────────────────┐
                  │   FastAPI        │   src/backend
                  │   Backend        │
                  └────────┬─────────┘
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
┌───────────────┐  ┌───────────────┐  ┌────────────────┐
│  Router LLM   │  │  FAISS RAG    │  │   MCP Tools     │
│ (intent +     │  │  retrieval    │  │  (stdio spawn)  │
│  params, JSON)│  │ data/vector_  │  │ src/mcp_servers │
└───────────────┘  │  store        │  │ weather/currency│
                    └───────────────┘  └────────────────┘
                           ▲
                           │ built by
                  ┌────────┴─────────┐
                  │  scripts/scrape  │
                  │  scripts/ingest  │
                  └──────────────────┘
```

The backend classifies each message's intent (knowledge-base lookup,
live-data lookup, both, or small talk) via a small local LLM call, then
explicitly retrieves from FAISS and/or calls the relevant MCP tool(s)
before a second LLM call synthesizes the final answer — labeled as
**Knowledge Base Facts**, **Live Data**, or **AI Recommendations** so
it's always clear what's grounded fact versus model-generated suggestion.

Deep dives per component, including bugs found and fixed along the way,
live in each package's own README (linked in
[Project structure](#project-structure) below).

## Prerequisites

Things `pip install` can't do for you:

- **Python 3.11+** (developed on 3.13)
- **[Ollama](https://ollama.com)** installed and running locally, with
  the model pulled:
  ```bash
  ollama pull phi3  
  ollama serve
  ```
- **A free exchangerate-api.com API key** — sign up at
  [exchangerate-api.com](https://www.exchangerate-api.com) (free tier,
  no credit card) for the currency-conversion tool.

## Setup

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Download Playwright's browser (used as a fallback by scripts/scrape.py
#    for pages that render their content client-side)
playwright install chromium

# 4. Configure your currency API key
cp .env.example .env
# then edit .env and set: EXCHANGERATE_API_KEY=your-key-here
```

## Running it

> Each new terminal starts without the virtual environment active. Before
> running any command below in a fresh terminal or after `cd`-ing into a
> different directory, activate it first:
> ```bash
> source .venv/bin/activate   # run from the repo root; adjust the path otherwise
> ```

Run these from the repo root, in order. The first two build the
knowledge base (skip them only if `data/raw/` and `data/vector_store/`
are already populated):

```bash
# 1. Scrape the knowledge-base sources -> data/raw/
python scripts/scrape.py

# 2. Chunk + embed + build the FAISS index -> data/vector_store/
python scripts/ingest.py

# 3. Start the backend (terminal 1)
source .venv/bin/activate
cd src/backend
uvicorn main:app --port 8000

# 4. Start the UI (terminal 2, from repo root)
source .venv/bin/activate
cd src/ui
streamlit run app.py
```

Then open the URL Streamlit prints (usually http://localhost:8501) and
start chatting. Try:
- *"What can I do in Singapore with kids?"* — RAG only
- *"What's the weather in Singapore for the next 3 days?"* — MCP (weather) only
- *"How much is 100 SGD in USD?"* — MCP (currency) only
- *"Plan a 2-day nature-focused itinerary and tell me the weather"* — combined

Optional sanity checks along the way:
```bash
python scripts/query.py             # test retrieval alone, no LLM
python scripts/test_mcp_servers.py  # test both MCP tools directly, no LLM
```

## Project structure

| Path | What it is |
|---|---|
| [`scripts/`](scripts/README.md) | One-off data-prep tools: scraping, chunking/embedding, and manual test harnesses |
| [`src/mcp_servers/`](src/mcp_servers/README.md) | MCP servers exposing live weather + currency-conversion tools |
| [`src/backend/`](src/backend/README.md) | FastAPI service: intent routing, RAG retrieval, MCP tool calls, answer synthesis |
| [`src/ui/`](src/ui/README.md) | Streamlit chat client — a thin HTTP client with zero app logic |
| `data/` | `raw/` (scraped docs) and `vector_store/` (FAISS index) — both generated, gitignored |

Every package folder above has its own README going deeper into *why*
it's built the way it is, including real bugs hit during development
(small-local-model quirks especially) and how they were fixed — worth
reading if you want the full story, not just the code.

## Known limitations

Phi-3-mini is a small (3.8B) local model, and several of its rough edges
required deliberate handling rather than trusting prompt instructions
alone — documented in detail in
[`src/backend/README.md`](src/backend/README.md#what-we-learned-building-this):
- Structured JSON output can have internally inconsistent fields (e.g. a
  correct `currency_query` under an incorrectly-labeled `intent`) — fixed
  by gating behavior on the specific field needed, not a summary label.
- The model can hallucinate a second, fake conversational turn if its
  input happens to resemble its expected output shape — fixed with an
  explicit stop sequence.
- Currency/country name normalization is best-effort (`src/backend/currency_codes.py`):
  handles ISO codes, official names, and common colloquial terms, but not
  country-name references (e.g. "US" meaning USD) — a known, documented gap.

## Tech stack

| Layer | Tool | Why |
|---|---|---|
| LLM | Phi-3-mini (via Ollama) | Free, local, small footprint |
| Orchestration | LangChain / LangChain-Ollama | Structured LLM calls |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` | Lightweight, free, local |
| Vector store | FAISS | Free, local, fast |
| MCP servers | Official Python MCP SDK | Weather + currency tools |
| Backend | FastAPI + Uvicorn | Async, typed, minimal |
| UI | Streamlit | Fastest path to a working chat UI |
| Weather API | Open-Meteo | Free, no signup |
| Currency API | exchangerate-api.com | Free tier, signup required |

**Total cost: $0.**
