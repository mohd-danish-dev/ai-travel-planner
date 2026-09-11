"""
MCP server exposing a single tool: convert_currency(amount, from_currency, to_currency).

Uses exchangerate-api.com's "pair conversion" endpoint (free tier, requires
a signup API key). Set it in the .env file at the repo root (copy
.env.example to .env and fill in your key) — never hardcode it here since
this file is tracked in git.

Run standalone (e.g. to point an MCP Inspector at it):
    python src/mcp_servers/currency_server.py
"""

import os

import httpx
from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer

load_dotenv()

mcp = MCPServer("currency")

API_KEY = os.environ.get("EXCHANGERATE_API_KEY", "")
RATES_URL = "https://v6.exchangerate-api.com/v6/{api_key}/pair/{base}/{target}"


@mcp.tool()
def convert_currency(amount: float, from_currency: str, to_currency: str) -> dict:
    """Convert an amount from one currency to another using current exchange rates.

    Args:
        amount: Amount to convert, e.g. 100.
        from_currency: 3-letter source currency code, e.g. "USD".
        to_currency: 3-letter target currency code, e.g. "SGD".
    """
    if not API_KEY:
        return {"error": "Currency service misconfigured: EXCHANGERATE_API_KEY is not set."}

    from_currency = from_currency.upper()
    to_currency = to_currency.upper()

    try:
        resp = httpx.get(
            RATES_URL.format(api_key=API_KEY, base=from_currency, target=to_currency),
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as e:
        return {"error": f"Currency service unavailable: {e}"}

    if data.get("result") != "success":
        return {"error": f"Currency service error: {data.get('error-type', 'unknown error')}"}

    rate = data.get("conversion_rate")
    if rate is None:
        return {"error": f"Unsupported currency pair: '{from_currency}' -> '{to_currency}'"}

    return {
        "amount": amount,
        "from_currency": data.get("base_code", from_currency),
        "to_currency": data.get("target_code", to_currency),
        "rate": rate,
        "converted_amount": round(amount * rate, 2),
        "rates_last_updated": data.get("time_last_update_utc"),
    }


if __name__ == "__main__":
    mcp.run()
