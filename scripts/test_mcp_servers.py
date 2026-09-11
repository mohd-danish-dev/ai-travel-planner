"""
Manually exercises both MCP servers through the real MCP protocol (stdio
transport) — the same mechanism the backend uses, just without an LLM in
the loop. Useful to confirm each tool works standalone before running the
full app.

Usage:
    python scripts/test_mcp_servers.py
"""

import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()

MCP_SERVERS_DIR = Path(__file__).resolve().parent.parent / "src" / "mcp_servers"


async def call_tool(
    command: str, args: list[str], tool_name: str, tool_args: dict, env: dict[str, str] | None = None
):
    # The MCP SDK only forwards a safe allowlist of env vars (PATH, HOME,
    # etc.) to spawned subprocesses by default, so anything a server needs
    # (like currency_server.py's API key) must be passed explicitly here.
    server_params = StdioServerParameters(command=command, args=args, env=env)
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print(f"  Available tools: {[t.name for t in tools.tools]}")

            result = await session.call_tool(tool_name, tool_args)
            for block in result.content:
                if hasattr(block, "text"):
                    print(f"  Result: {block.text}")
                else:
                    print(f"  Result: {block}")


async def main():
    python = sys.executable
    weather_server = str(MCP_SERVERS_DIR / "weather_server.py")
    currency_server = str(MCP_SERVERS_DIR / "currency_server.py")

    print("Testing weather_server.py -> get_weather('Singapore', 3)")
    await call_tool(python, [weather_server], "get_weather", {"city": "Singapore", "days": 3})

    print("\nTesting weather_server.py -> get_weather_by_coordinates(1.3521, 103.8198, 2)")
    await call_tool(
        python,
        [weather_server],
        "get_weather_by_coordinates",
        {"latitude": 1.3521, "longitude": 103.8198, "days": 2},
    )

    print("\nTesting currency_server.py -> convert_currency(100, 'USD', 'SGD')")
    currency_env = {"EXCHANGERATE_API_KEY": os.environ.get("EXCHANGERATE_API_KEY", "")}
    await call_tool(
        python,
        [currency_server],
        "convert_currency",
        {"amount": 100, "from_currency": "USD", "to_currency": "SGD"},
        env=currency_env,
    )

    print("\nTesting weather_server.py -> get_weather('NotARealCityXYZ') [graceful failure check]")
    await call_tool(python, [weather_server], "get_weather", {"city": "NotARealCityXYZ"})


if __name__ == "__main__":
    asyncio.run(main())
