# UI

A Streamlit chat window that talks to the [../backend](../backend)
FastAPI service over plain HTTP. This is deliberately the "dumb" half of
the app: it renders messages and makes one `requests.post()` call per
question — no LangChain, no FAISS, no MCP code lives here at all. That's
the point of the backend/UI split: you could swap this file out for a
React app, a CLI, or a Slack bot without changing a single line in
`../backend`.

## How it works

- **Session ID** — on first load, generates a random `uuid` and stores it
  in `st.session_state`. This is sent with every request so the backend
  knows which conversation history to use (see `../backend/memory.py`).
  It survives page interactions within one browser tab (Streamlit reruns
  the whole script on every interaction, but `st.session_state` persists
  across those reruns) but resets if you reload the page — which just
  starts a fresh conversation, same as clicking "Start new conversation."
- **`st.chat_input` / `st.chat_message`** — Streamlit's built-in chat
  primitives; they render the familiar bubble UI for free, no custom CSS.
- **Sources & tools used** — an expander under each assistant reply
  showing which knowledge-base sources and/or MCP tools contributed to
  that answer, from the `sources` / `tools_called` fields the backend
  returns. This is what satisfies the assignment's "tool selection by
  intent" transparency requirement — the user can see *why* an answer
  looks the way it does.

## Run it

You need the backend running first (see the root [README.md](../../README.md)
for full setup):
```bash
# terminal 1
cd src/backend && uvicorn main:app --port 8000

# terminal 2
cd src/ui && streamlit run app.py
```
Then open the URL Streamlit prints (usually http://localhost:8501).

If your backend runs on a different host/port, set `BACKEND_URL`:
```bash
BACKEND_URL=http://localhost:9000 streamlit run app.py
```

## Files
- `app.py` — the entire UI

## What we learned building this
- **Streamlit's "magic" auto-display bit us.** A bare expression at the
  top level of a script — `st.success(...) if cond else st.error(...)` —
  isn't just "run this line," Streamlit treats any un-consumed expression
  value as something to render via `st.write()`. Since `st.success()`
  returns a `DeltaGenerator` object (not `None`), that ternary's return
  value got auto-rendered as ugly internal object/docstring dump right
  in the sidebar. The fix was a plain `if/else` statement instead of a
  ternary expression — statements don't get the magic treatment, only
  expressions. Worth remembering any time a "why is this junk text
  appearing" bug shows up in a Streamlit app: check for a bare expression
  nearby.
- We also caught (and fixed, in `../backend`) a case where the local LLM
  would hallucinate a second, fake tool call after answering a real one —
  worth reading `../backend/README.md`'s "what we learned" section if
  you're curious, since it's a backend prompt-design issue, not a UI one.
