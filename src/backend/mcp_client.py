"""
Manages persistent MCP client connections to the weather and currency
servers in ../mcp_servers. Each server is spawned once (as a subprocess,
over stdio) when the FastAPI app starts, and reused for every request —
spawning a fresh subprocess per chat message would be wasteful.
"""

import os
import sys
from contextlib import AsyncExitStack
from pathlib import Path

from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()

MCP_SERVERS_DIR = Path(__file__).resolve().parent.parent / "mcp_servers"


class MCPToolClients:
    """Holds one live ClientSession per MCP server for the app's lifetime."""

    def __init__(self):
        self._exit_stack = AsyncExitStack()
        self.weather: ClientSession | None = None
        self.currency: ClientSession | None = None

    async def start(self):
        self.weather = await self._connect("weather_server.py")
        # The MCP SDK only forwards a safe allowlist of env vars (PATH, HOME,
        # etc.) to spawned subprocesses by default — currency_server.py needs
        # its API key explicitly passed through, or it'll silently see an
        # empty EXCHANGERATE_API_KEY no matter what's set in this process.
        currency_env = {"EXCHANGERATE_API_KEY": os.environ.get("EXCHANGERATE_API_KEY", "")}
        self.currency = await self._connect("currency_server.py", env=currency_env)

    async def _connect(self, script_name: str, env: dict[str, str] | None = None) -> ClientSession:
        params = StdioServerParameters(
            command=sys.executable,
            args=[str(MCP_SERVERS_DIR / script_name)],
            env=env,
        )
        read, write = await self._exit_stack.enter_async_context(stdio_client(params))
        session = await self._exit_stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        return session

    async def stop(self):
        await self._exit_stack.aclose()

    async def get_weather(self, city: str, days: int = 1) -> dict:
        result = await self.weather.call_tool("get_weather", {"city": city, "days": days})
        return _parse_tool_result(result)

    async def get_weather_by_coordinates(self, latitude: float, longitude: float, days: int = 1) -> dict:
        result = await self.weather.call_tool(
            "get_weather_by_coordinates",
            {"latitude": latitude, "longitude": longitude, "days": days},
        )
        return _parse_tool_result(result)

    async def convert_currency(self, amount: float, from_currency: str, to_currency: str) -> dict:
        result = await self.currency.call_tool(
            "convert_currency",
            {"amount": amount, "from_currency": from_currency, "to_currency": to_currency},
        )
        return _parse_tool_result(result)


def _parse_tool_result(result) -> dict:
    """MCP tool results come back as a list of content blocks; our tools
    return a single JSON text block, so parse and return that."""
    import json

    for block in result.content:
        if hasattr(block, "text"):
            return json.loads(block.text)
    return {"error": "Tool returned no parseable content."}
