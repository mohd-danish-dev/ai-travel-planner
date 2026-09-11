"""
MCP server exposing two tools: get_weather(city, days) and
get_weather_by_coordinates(latitude, longitude, days).

Uses Open-Meteo (https://open-meteo.com) — free, no API key required.
get_weather geocodes the city name to lat/lon first, then both tools
share the same forecast-fetching path.

Run standalone (e.g. to point an MCP Inspector at it):
    python src/mcp_servers/weather_server.py
Normally this gets launched automatically by whatever MCP client (the
backend, or an MCP inspector) is configured to spawn it.
"""

import httpx
from mcp.server.mcpserver import MCPServer

mcp = MCPServer("weather")

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# WMO weather interpretation codes -> human-readable description
# https://open-meteo.com/en/docs (see "WMO Weather interpretation codes")
WEATHER_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    71: "Slight snow",
    73: "Moderate snow",
    75: "Heavy snow",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


def describe_code(code: int | None) -> str:
    if code is None:
        return "Unknown"
    return WEATHER_CODES.get(code, f"Unrecognized weather code {code}")


def geocode_city(client: httpx.Client, city: str) -> dict | None:
    resp = client.get(GEOCODING_URL, params={"name": city, "count": 1, "language": "en"})
    resp.raise_for_status()
    results = resp.json().get("results")
    if not results:
        return None
    return results[0]


def fetch_forecast(latitude: float, longitude: float, days: int) -> dict:
    """Fetch current conditions (+ daily forecast if days > 1) for a point.

    Returns a plain dict with "current" and optionally "forecast" keys, or
    {"error": ...} on failure. Shared by both get_weather (city -> geocode
    -> here) and get_weather_by_coordinates (straight here).
    """
    days = max(1, min(days, 7))

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,weather_code,wind_speed_10m",
        "timezone": "auto",
        "forecast_days": days,
    }
    if days > 1:
        params["daily"] = "temperature_2m_max,temperature_2m_min,weather_code"

    try:
        resp = httpx.get(FORECAST_URL, params=params, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as e:
        return {"error": f"Weather service unavailable: {e}"}

    current = data.get("current", {})
    result = {
        "current": {
            "temperature_c": current.get("temperature_2m"),
            "wind_speed_kmh": current.get("wind_speed_10m"),
            "conditions": describe_code(current.get("weather_code")),
        }
    }

    if days > 1 and "daily" in data:
        daily = data["daily"]
        result["forecast"] = [
            {
                "date": daily["time"][i],
                "min_temp_c": daily["temperature_2m_min"][i],
                "max_temp_c": daily["temperature_2m_max"][i],
                "conditions": describe_code(daily["weather_code"][i]),
            }
            for i in range(len(daily["time"]))
        ]

    return result


@mcp.tool()
def get_weather(city: str, days: int = 1) -> dict:
    """Get current weather and/or a multi-day forecast for a city.

    Args:
        city: City name, e.g. "Singapore".
        days: Number of forecast days to include (1-7). 1 returns just
            current conditions; >1 also includes a daily forecast.
    """
    try:
        with httpx.Client(timeout=10.0) as client:
            place = geocode_city(client, city)
    except httpx.HTTPError as e:
        return {"error": f"Weather service unavailable: {e}"}

    if place is None:
        return {"error": f"Could not find a location matching '{city}'."}

    result = fetch_forecast(place["latitude"], place["longitude"], days)
    if "error" in result:
        return result

    return {"city": place.get("name", city), "country": place.get("country"), **result}


@mcp.tool()
def get_weather_by_coordinates(latitude: float, longitude: float, days: int = 1) -> dict:
    """Get current weather and/or a multi-day forecast for exact coordinates.

    Use this instead of get_weather when you already have a precise
    latitude/longitude (e.g. a specific attraction or address) rather than
    just a city name.

    Args:
        latitude: Latitude in decimal degrees, e.g. 1.3521.
        longitude: Longitude in decimal degrees, e.g. 103.8198.
        days: Number of forecast days to include (1-7). 1 returns just
            current conditions; >1 also includes a daily forecast.
    """
    result = fetch_forecast(latitude, longitude, days)
    if "error" in result:
        return result

    return {"latitude": latitude, "longitude": longitude, **result}


if __name__ == "__main__":
    mcp.run()
