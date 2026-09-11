# Scripts

One-off / on-demand data-prep and dev-testing utilities. Nothing here is
imported by the running app (`src/`) — each script is invoked directly,
usually once per data refresh, or on demand while developing.

See the root [README.md](../README.md) for environment setup; these all
assume you've already created the venv and installed `requirements.txt`.

## `scrape.py` — build the knowledge base source docs
Fetches the Singapore travel knowledge-base sources and saves each as a
clean markdown file (with title/url/scraped_at frontmatter) into
`data/raw/`.
```bash
python scripts/scrape.py
```

**Why this matters:** the target sites aren't all simple static HTML.
`visitsingapore.com` renders its actual content inside Shadow DOM web
components — regular HTML parsing (even after JS execution) can't see
inside shadow roots. The script tries a fast static fetch
(`trafilatura`) first, and falls back to a headless-Chromium render
(`playwright`, using `page.inner_text()` which does pierce shadow DOM)
only when the static result comes back too thin. Landing/category pages
on that site are also thin tab-switcher shells — the real content lives
on their sub-pages, so the source list points at those directly rather
than the generic top-level pages.

## `ingest.py` — build the vector index
Turns the scraped markdown in `data/raw/` into a searchable knowledge
base: chunk → embed → store in FAISS. This is the "R" (Retrieval) half
of RAG — the backend uses this to fetch relevant facts before asking the
LLM to answer, instead of relying on the LLM's own (possibly wrong or
outdated) memory.
```bash
python scripts/ingest.py
```
Reads every `.md` file in `data/raw/`, splits it into ~500-token chunks
(50-token overlap, measured via `tiktoken` since that's what actually
fills a model's context window) embeds them with
`sentence-transformers/all-MiniLM-L6-v2`, and writes the FAISS index to
`data/vector_store/`.

**Why chunk + embed at all, instead of pasting all the docs into the
prompt?** A local model has a limited context window, and stuffing in
everything wastes tokens and buries the relevant bit in noise. Storing
embeddings lets us fetch only the few passages relevant to *this*
question — chunks about similar topics end up as nearby vectors even
without shared keywords (e.g. "kid-friendly" and "family fun" land
close together).

## `query.py` — sanity-check retrieval
Interactive retrieval tester against the FAISS index — no LLM involved,
just "does the right chunk come back for this question?" Useful before
trusting the backend's answers.
```bash
python scripts/query.py
python scripts/query.py --k 6   # retrieve more chunks per query
```
Lower score = closer match (FAISS reports L2 distance here, not
similarity).

## `test_mcp_servers.py` — sanity-check the MCP tools
Manually exercises both MCP servers (`src/mcp_servers/`) through the
real MCP protocol (stdio transport) — the same mechanism the backend
uses, just without an LLM in the loop. Includes a deliberate bad-input
case to confirm graceful failure.
```bash
python scripts/test_mcp_servers.py
```

## What we learned building these
- `visit-singapore-*` docs are short (1-3 chunks each); `wikivoyage-*` is
  long and became the large majority of total chunks — expected, since
  it's a full country guide vs. focused sub-pages.
- A vague retrieval query like "what can I do with kids" can retrieve
  mediocre matches if it doesn't share vocabulary with the docs; a more
  specific phrasing ("family friendly activities and attractions for
  children") retrieved the right chunk as the #1 hit. This matters for
  prompt design in the backend — a technique called query expansion
  (having the LLM rephrase vague queries before retrieval) would help
  here, though it's beyond this project's current scope.
- The MCP Python SDK had a breaking change between v1 and v2: `FastMCP`
  was renamed to `MCPServer` (`from mcp.server.mcpserver import
  MCPServer`). If you find older tutorials referencing `FastMCP`, that's
  the v1 API — functionally almost identical, just a different import
  and class name.
- **Spawned MCP subprocesses don't inherit your full environment.** The
  MCP SDK's `stdio_client` only forwards a safe allowlist of env vars
  (`PATH`, `HOME`, etc.) to the process it spawns — not arbitrary ones
  like `EXCHANGERATE_API_KEY`, even if the parent process (or its `.env`
  file) has it set. The key has to be read with `load_dotenv()` in the
  parent and passed explicitly via `StdioServerParameters(env=...)`.
  Worth remembering any time an MCP server needs a secret — check
  whether your client is actually forwarding it.
