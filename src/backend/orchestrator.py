"""
Per-request pipeline: classify intent -> fetch RAG/MCP context as needed ->
synthesize the final labeled answer -> update session memory.
"""

import json
import os

from langchain_ollama import ChatOllama

import memory
import rag
from dotenv import load_dotenv
from currency_codes import normalize_currency_code
from mcp_client import MCPToolClients
from prompts import ANSWER_SYSTEM_PROMPT, ROUTER_SYSTEM_PROMPT


load_dotenv()

OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "phi3")

router_llm = ChatOllama(model=OLLAMA_MODEL, format="json", temperature=0)
answer_llm = ChatOllama(model=OLLAMA_MODEL, temperature=0.3)

# Marks the end of the context block we hand the model. Small models can
# mimic the shape of their own input (see README "what we learned") and
# start hallucinating a second fake turn; a stop sequence on this exact,
# unlikely-to-occur-naturally string cuts generation off before that happens.
CONTEXT_END_MARKER = "=== END OF CONTEXT ==="

DEFAULT_ROUTE = {
    "intent": "RAG",
    "rag_query": None,
    "weather_query": None,
    "currency_query": None,
}


def _history_as_text(history: list[dict]) -> str:
    if not history:
        return "(no previous messages)"
    return "\n".join(f"{turn['role']}: {turn['content']}" for turn in history)


def classify_intent(message: str, history: list[dict]) -> dict:
    prompt = (
        f"Conversation so far:\n{_history_as_text(history)}\n\n"
        f"Latest user message: {message}"
    )
    try:
        response = router_llm.invoke(
            [{"role": "system", "content": ROUTER_SYSTEM_PROMPT}, {"role": "user", "content": prompt}]
        )
        route = json.loads(response.content)
    except Exception:
        # Router output didn't parse or the LLM call failed — fall back to a
        # plain RAG lookup on the raw message rather than blocking the reply.
        route = dict(DEFAULT_ROUTE, rag_query=message)

    if route.get("intent") in ("RAG", "COMBINED") and not route.get("rag_query"):
        route["rag_query"] = message
    return route


async def gather_live_data(route: dict, mcp_clients: MCPToolClients) -> tuple[list[dict], list[str]]:
    """Calls whichever MCP tools the router asked for. Returns (results, tool_names_called)."""
    live_data = []
    tools_called = []

    weather_query = route.get("weather_query")
    if weather_query and weather_query.get("city"):
        result = await mcp_clients.get_weather(
            city=weather_query["city"], days=weather_query.get("days", 1)
        )
        live_data.append({"tool": "get_weather", "input": weather_query, "output": result})
        tools_called.append("get_weather")

    currency_query = route.get("currency_query")
    if currency_query and currency_query.get("amount") and currency_query.get("to_currency"):
        # The router doesn't reliably follow the "use ISO 4217" prompt rule on
        # its own (small model) — normalize here rather than trust it as-is.
        # Falls back to the raw, uppercased value if normalization can't
        # resolve it, so the live API's own error handling is still the
        # final backstop rather than us silently dropping the tool call.
        raw_from = currency_query.get("from_currency", "USD")
        raw_to = currency_query["to_currency"]
        from_currency = normalize_currency_code(raw_from) or raw_from.strip().upper()
        to_currency = normalize_currency_code(raw_to) or raw_to.strip().upper()

        result = await mcp_clients.convert_currency(
            amount=currency_query["amount"],
            from_currency=from_currency,
            to_currency=to_currency,
        )
        normalized_input = {**currency_query, "from_currency": from_currency, "to_currency": to_currency}
        live_data.append({"tool": "convert_currency", "input": normalized_input, "output": result})
        tools_called.append("convert_currency")

    return live_data, tools_called


def format_kb_facts(chunks: list[dict]) -> str:
    if not chunks:
        return "(none retrieved)"
    return "\n\n".join(
        f"[Source: {c['title']} - {c['source_url']}]\n{c['text']}" for c in chunks
    )


def format_live_data(live_data: list[dict]) -> str:
    if not live_data:
        return "(none fetched)"
    return "\n\n".join(
        f"Tool: {d['tool']}\nInput: {json.dumps(d['input'])}\nOutput: {json.dumps(d['output'])}"
        for d in live_data
    )


async def handle_message(session_id: str, message: str, mcp_clients: MCPToolClients) -> dict:
    history = memory.get_history(session_id)

    route = classify_intent(message, history)
    intent = route.get("intent", "RAG")

    # Gate on the router's extracted fields directly rather than trusting the
    # top-level "intent" label to always agree with them — a small model can
    # correctly fill in e.g. currency_query while still mislabeling intent as
    # "RAG" for a mixed query. See src/backend/README.md "what we learned".
    kb_chunks: list[dict] = []
    if route.get("rag_query"):
        kb_chunks = rag.retrieve(route["rag_query"], k=4)

    live_data: list[dict] = []
    tools_called: list[str] = []
    if route.get("weather_query") or route.get("currency_query"):
        live_data, tools_called = await gather_live_data(route, mcp_clients)

    if not kb_chunks and not live_data:
        answer_context = "The user is making small talk or asking something unrelated to Singapore travel; there is no knowledge-base or live data for this."
    else:
        answer_context = (
            f"Retrieved knowledge base excerpts:\n{format_kb_facts(kb_chunks)}\n\n"
            f"Live tool results:\n{format_live_data(live_data)}"
        )

    messages = [{"role": "system", "content": ANSWER_SYSTEM_PROMPT}]
    for turn in history:
        messages.append(turn)
    messages.append(
        {
            "role": "user",
            "content": (
                f"{answer_context}\n{CONTEXT_END_MARKER}\n\n"
                f"Using only the context above, answer this question: {message}"
            ),
        }
    )

    response = answer_llm.invoke(messages, stop=[CONTEXT_END_MARKER])
    answer = response.content.split(CONTEXT_END_MARKER)[0].strip()

    memory.add_turn(session_id, message, answer)

    return {
        "answer": answer,
        "intent": intent,
        "sources": [{"title": c["title"], "url": c["source_url"]} for c in kb_chunks],
        "tools_called": tools_called,
    }
