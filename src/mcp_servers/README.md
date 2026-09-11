# MCP Servers

Two standalone MCP servers that give the LLM access to *live* data it
could never know from training alone: current weather and today's
exchange rates. Used by [../backend](../backend); can also be tested
standalone via [../../scripts/test_mcp_servers.py](../../scripts/test_mcp_servers.py).

## What is MCP, and why not just call a Python function?

**MCP (Model Context Protocol)** is a standard way to expose "tools" (or
data, or prompts) to an LLM-based agent over a well-defined protocol,
instead of every project inventing its own bespoke way to hand a model
external capabilities.

You *could* just write `get_weather()` as a plain Python function and
call it directly in your app — and for a single app like ours, that would
honestly work fine. The reasons MCP exists and is worth learning:

- **Decoupling** — the server (this folder) and the client (the app that
  uses it) are separate processes that talk over a standard protocol
  (here: stdio — the client launches the server as a subprocess and they
  exchange JSON-RPC messages over stdin/stdout). The client doesn't need
  to import your code or even be written in Python.
- **Discoverability** — a client can ask a running MCP server "what tools
  do you have?" (`list_tools`) and get back each tool's name, description,
  and input schema, *before* deciding to call it. This is what lets an
  LLM agent dynamically decide which tool to use based on the user's
  question, rather than the tool being hardcoded into the prompt.
- **Reuse** — the same weather server could be plugged into Claude
  Desktop, a different agent framework, or another project entirely,
  with zero code changes.

The backend acts as the **MCP client**, discovers these two tools, and
decides per-query whether to call one, both, or neither — that's the
"MCP path" / "combined path" in the architecture diagram in the
[root README](../../README.md#architecture).

## The tools

### `get_weather(city, days)` and `get_weather_by_coordinates(latitude, longitude, days)` — [weather_server.py](weather_server.py)
Uses **[Open-Meteo](https://open-meteo.com)** — chosen over the
originally-planned OpenWeatherMap because it needs **no signup, no API
key**. Two ways in, one shared path out:
- `get_weather` geocodes a city name → lat/lon, then fetches the forecast.
- `get_weather_by_coordinates` skips geocoding for when you already have
  precise coordinates (e.g. a specific attraction rather than a whole city).

Both call the same internal `fetch_forecast(lat, lon, days)` helper, so
the actual forecast-fetching and response-shaping logic lives in one
place. `days=1` returns just current conditions; `days>1` also includes a
daily min/max/conditions forecast (up to 7 days).

### `convert_currency(amount, from_currency, to_currency)` — [currency_server.py](currency_server.py)
Uses exchangerate-api.com's **pair conversion** endpoint, which needs a
free-tier signup API key. Set it in the `.env` file at the repo root
(see the root [README.md](../../README.md)) — never hardcode it in the
source, since this file is tracked in git. (We started with their no-key
`open.er-api.com` endpoint, which also works fine if you'd rather avoid
the signup — see "what we learned" below.)

**Graceful failure, both tools:** on a bad city name, unsupported
currency code, or the API being down, the tool returns
`{"error": "..."}` instead of raising — the plan's "never fabricate
weather/currency numbers" rule starts here. The backend's prompt is told
to surface that error message honestly rather than making up a number.

## Running these directly
Each server just sits there speaking the MCP protocol over stdio — it's
meant to be launched by a client (the backend, `scripts/test_mcp_servers.py`,
or an MCP Inspector), not run interactively on its own:
```bash
python src/mcp_servers/weather_server.py
python src/mcp_servers/currency_server.py
```

## Files
- `weather_server.py` — the weather MCP server
- `currency_server.py` — the currency MCP server

## What we learned building these
- The MCP Python SDK had a breaking change between v1 and v2: `FastMCP`
  was renamed to `MCPServer` (`from mcp.server.mcpserver import MCPServer`).
  If you find older tutorials referencing `FastMCP`, that's the v1 API —
  functionally almost identical, just a different import and class name.
- A tool's docstring and type hints aren't just documentation — the MCP
  SDK turns them into the JSON schema the client (and ultimately the LLM)
  sees when deciding whether and how to call the tool. Write them as if
  the LLM is the reader, because it is.
- **Spawned MCP subprocesses don't inherit your full environment.** The
  MCP SDK's `stdio_client` only forwards a safe allowlist of env vars
  (`PATH`, `HOME`, etc.) to the process it spawns — not arbitrary ones
  like `EXCHANGERATE_API_KEY`, even if the parent process (or its `.env`
  file) has it set. We hit this switching to the paid-signup
  exchangerate-api.com endpoint: the key has to be read with
  `load_dotenv()` in the parent and passed explicitly via
  `StdioServerParameters(env=...)`, in both `scripts/test_mcp_servers.py`
  and `src/backend/mcp_client.py`. Worth remembering any time an MCP
  server needs a secret — check whether your client is actually
  forwarding it.
