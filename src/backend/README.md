# Backend

The orchestrator: a FastAPI service that ties together the RAG pipeline
([../../scripts](../../scripts) + this folder's `rag.py`) and the MCP
tools ([../mcp_servers](../mcp_servers)) behind one `/chat` endpoint. The
UI ([../ui](../ui)) is a separate project that just calls this over
HTTP — this backend has no idea a UI even exists.

## How a request flows

```
POST /chat {session_id, message}
        │
        ▼
1. Load this session's conversation history (in-memory dict)
        │
        ▼
2. Router LLM call (Phi-3-mini, forced JSON output)
   "what does this message need?"
   -> {intent: RAG | MCP | COMBINED | CHITCHAT, rag_query, weather_query, currency_query}
        │
        ├── RAG / COMBINED  ──► retrieve top-4 chunks from FAISS (data/vector_store)
        │
        ├── MCP / COMBINED  ──► call weather and/or currency MCP tools (../mcp_servers)
        │
        ▼
3. Answer LLM call (Phi-3-mini): given KB facts + live data + question,
   write a reply with headings **Knowledge Base Facts / Live Data / AI
   Recommendations**
        │
        ▼
4. Save (message, answer) into session history, return the answer +
   which sources/tools were used (for the UI to display)
```

## Why two LLM calls instead of one agent call?

The original plan described "the LLM selects a tool via function-calling/
agent pattern" — the standard LangChain agent approach. We deliberately
didn't do that here: **Ollama's native tool-calling is unreliable on small
local models like Phi-3-mini** (arguments that don't match the schema,
degraded accuracy once more than a couple of tools are registered). Local,
free, and small was the whole point of this stack, so instead:

- **Call 1 (the router)** asks the model to output structured JSON
  (`format="json"` — Ollama forces valid JSON syntax) describing intent
  and parameters. This is a much easier task for a small model than
  correctly-typed function-call arguments, and if it still fails to parse,
  we fall back to a safe default (treat it as a RAG query) instead of
  crashing the request.
- **Call 2 (the answer)** just writes prose grounded in whatever
  context Python already assembled — no tool-calling needed here at all.

This is a manual, explicit version of what an "agent" does, and is more
predictable to debug than trusting a 3.8B model's function-call output.

## Session memory
A plain `dict[session_id -> list of messages]` in `memory.py`. This is a
deliberate simplification — it resets on server restart and wouldn't work
across multiple backend processes — chosen to keep a real database out of
scope for now. Swapping in Redis later wouldn't touch anything else in
this folder.

## Prerequisites
See the root [README.md](../../README.md) for full setup. In short, this
needs:
- Ollama running locally with the model pulled: `ollama pull phi3`
- The FAISS index built: `scripts/ingest.py` already run
- An exchangerate-api.com API key in the repo-root `.env` —
  `mcp_client.py` reads it via `load_dotenv()` and forwards it to the
  spawned currency server explicitly (see
  `../mcp_servers/README.md` for why that forwarding has to be explicit)

## Run it
```bash
cd src/backend
uvicorn main:app --reload
```
- `GET /health` — liveness check
- `POST /chat {"session_id": "...", "message": "..."}` — the main endpoint
- `POST /reset?session_id=...` — clears a session's memory

Quick manual test:
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "demo", "message": "What is the weather in Singapore for the next 3 days?"}'
```

## Files
- `main.py` — FastAPI app, CORS, lifespan (starts/stops the MCP client
  connections once per process instead of per-request)
- `orchestrator.py` — the request pipeline described above (router logic
  lives here too, as `classify_intent`)
- `prompts.py` — the router and answer system prompts
- `rag.py` — loads the FAISS index and exposes `retrieve(query, k)`
- `mcp_client.py` — holds persistent MCP `ClientSession`s to both servers
- `memory.py` — in-memory per-session conversation history
- `currency_codes.py` — normalizes whatever currency string the router
  produces (name, colloquial term, or code) into an ISO 4217 alpha-3 code

## What we learned building this
- A router that returns `"intent": "COMBINED"` but a `null` rag_query is
  a real failure mode with small models — they don't always fill in every
  field consistently. We initially used `dict.setdefault()` to backfill a
  missing `rag_query`, but `setdefault` only fires when the *key* is
  absent — a key present with value `null` (which is exactly what the
  model returned) silently skipped retrieval. Fixed by explicitly checking
  `not route.get("rag_query")` instead. Worth remembering any time you're
  patching gaps in LLM-generated structured output.
- CPU-only local inference with Phi-3-mini is slow enough (tens of
  seconds per request, two calls per chat message) that you'll want to
  test with `curl -m 200` or a background terminal rather than assuming
  a fast response.
- **The answer LLM hallucinated a second, fake turn.** Our first prompt
  format handed the model context shaped like `"Knowledge Base Facts:\n...
  \n\nLive Data:\n...\n\nUser question: ..."` — and asked it to reply
  using headings like `**Knowledge Base Facts**`. A real response came
  back once, immediately followed by a second, entirely fabricated
  `Live Data` block (a fake tool called `get_currency_exchange`, a made-up
  "Bank of America" exchange rate) and a fake `User question:` line — the
  small model was pattern-completing its own input template instead of
  stopping. Fixed two ways: (1) reworded the input labels away from the
  output heading names and appended a unique `=== END OF CONTEXT ===`
  marker right before the actual question, (2) passed that marker as a
  `stop` sequence to `ChatOllama.invoke(..., stop=[...])` so generation
  halts there, plus a defensive `.split(marker)[0]` truncation in case the
  stop sequence doesn't land exactly on a token boundary. General lesson:
  a small local model can echo the *shape* of whatever you feed it, so
  don't make your desired output format textually resemble your input
  format, and always give a small model an explicit stop condition rather
  than trusting it to know when to end.
- **A "mixed" query could silently skip a needed tool call.** Real bug
  found by manually testing the UI: "I want to visit Gardens by the Bay,
  also how much is 50 USD in SGD?" made the router correctly extract
  `currency_query`, but label the overall `intent` as `"RAG"` (anchoring
  on the attraction as the "main" topic) instead of `"COMBINED"`. Since
  `gather_live_data()` was gated on `intent in ("MCP", "COMBINED")`,
  `convert_currency` never got called — no error, just a silently
  incomplete answer. Same root cause as the `rag_query: null` bug above:
  trusting one summary field (`intent`) to always agree with the other
  fields the same JSON response set. Fixed two ways again: (1) tightened
  `ROUTER_SYSTEM_PROMPT` with an explicit hard rule ("if you fill in
  weather_query/currency_query, intent MUST be MCP or COMBINED"), and
  (2) — the actually load-bearing fix — changed the gating logic in
  `handle_message` to check `route.get("weather_query")` /
  `route.get("currency_query")` / `route.get("rag_query")` directly,
  rather than branching on the `intent` label at all. `intent` is now
  only used for display/logging, not as a gate. General lesson: with a
  small model's structured output, don't let one field gate behavior
  that another field already tells you directly — check the field you
  actually need, and treat prompt tightening as a frequency-reducer, not
  a fix, for anything correctness-critical.
- **A prompt rule alone ("use ISO 4217 codes") didn't reliably hold either.**
  The router would sometimes emit "US Dollar", "euros", or "pounds" instead
  of "USD"/"EUR"/"GBP" despite the instruction. Rather than iterate on the
  prompt further, added `currency_codes.py`: exact ISO-code/official-name
  lookup via `pycountry` (which handles "US Dollar" and "SGD" fine, but
  not plurals/colloquialisms — `pycountry.currencies` has no fuzzy search,
  unlike its countries/languages tables), backed by a small curated alias
  table for common unambiguous colloquial terms ("euros", "pounds", "yen").
  Deliberately left genuinely ambiguous terms ("dollars", "pesos" — several
  countries use these names) unresolved rather than guessing; those fall
  back to the raw uppercased string and let the live currency API's own
  validation reject it gracefully. Same lesson a third time: validate/
  normalize small-model output in code for anything a wrong value would
  actually break, rather than trusting a prompt instruction to always hold.
  A further known gap: this only normalizes *currency* names/codes — if
  the router (or a user) hands over a *country* reference instead (e.g.
  "US" or "Singapore"), nothing here resolves that to a currency; it
  would need a separate country→currency lookup layer.
- Once the routing bug above was fixed, a new formatting quirk showed up
  on that same mixed query: the answer repeated itself across an extra
  plain "Recommendations" heading and a "Friendly Tone" heading, both
  restating what "AI Recommendations" already said. `ANSWER_SYSTEM_PROMPT`
  only forbade *fabricating facts*, not *repeating real ones under a new
  heading* — a different failure mode with the same "small model doesn't
  reliably stick to instructions" root cause as the two bugs above.
  Tightened the prompt with explicit anti-repetition and "stop after the
  last section" rules; this is a formatting/UX concern rather than a
  correctness one, so unlike the two bugs above we didn't add a code-side
  backstop — occasional minor repetition here doesn't produce a wrong or
  incomplete answer, just a longer one.
