"""
tools/weather_tool.py
Weather via Open-Meteo + Nominatim geocoding — completely free, no API key needed.
"""

import requests
import re


# ── WMO weather code descriptions ────────────────────────────────────────────
WMO_CODES = {
    0:  "Clear sky ☀️",
    1:  "Mainly clear 🌤",
    2:  "Partly cloudy ⛅",
    3:  "Overcast ☁️",
    45: "Foggy 🌫",
    48: "Icy fog 🌫",
    51: "Light drizzle 🌦",
    53: "Drizzle 🌦",
    55: "Heavy drizzle 🌧",
    61: "Slight rain 🌧",
    63: "Rain 🌧",
    65: "Heavy rain 🌧",
    71: "Slight snow 🌨",
    73: "Snow 🌨",
    75: "Heavy snow ❄️",
    77: "Snow grains ❄️",
    80: "Slight showers 🌦",
    81: "Showers 🌦",
    82: "Heavy showers 🌧",
    85: "Snow showers 🌨",
    86: "Heavy snow showers ❄️",
    95: "Thunderstorm ⛈",
    96: "Thunderstorm with hail ⛈",
    99: "Thunderstorm with heavy hail ⛈",
}


def _geocode(location: str):
    """Return (lat, lon, display_name) for a location string."""
    r = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": location, "format": "json", "limit": 1},
        timeout=8,
        headers={"User-Agent": "NovaAssistant/1.0"},
    )
    results = r.json()
    if not results:
        return None, None, None
    top = results[0]
    return float(top["lat"]), float(top["lon"]), top["display_name"]


def get_weather(location: str) -> str:
    """Fetch current weather + today's forecast for a location."""
    try:
        lat, lon, display = _geocode(location)
    except Exception:
        return "⚠️ Could not reach geocoding service. Check your internet connection."

    if lat is None:
        return f"⚠️ Could not find location: '{location}'. Try a city name like 'London' or 'New York'."

    try:
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude":  lat,
                "longitude": lon,
                "current": [
                    "temperature_2m",
                    "apparent_temperature",
                    "relative_humidity_2m",
                    "wind_speed_10m",
                    "weathercode",
                ],
                "daily": [
                    "temperature_2m_max",
                    "temperature_2m_min",
                    "precipitation_sum",
                    "weathercode",
                ],
                "timezone": "auto",
                "forecast_days": 3,
            },
            timeout=8,
        )
        data = r.json()
    except Exception:
        return "⚠️ Could not reach weather service. Check your internet connection."

    cur = data.get("current", {})
    daily = data.get("daily", {})

    temp      = cur.get("temperature_2m", "?")
    feels     = cur.get("apparent_temperature", "?")
    humidity  = cur.get("relative_humidity_2m", "?")
    wind      = cur.get("wind_speed_10m", "?")
    wcode     = cur.get("weathercode", 0)
    condition = WMO_CODES.get(wcode, "Unknown")
    unit      = data.get("current_units", {}).get("temperature_2m", "°C")

    lines = [
        f"🌍 Weather for {display.split(',')[0].strip()}",
        f"",
        f"  {condition}",
        f"  🌡  {temp}{unit}  (feels like {feels}{unit})",
        f"  💧 Humidity: {humidity}%",
        f"  💨 Wind: {wind} km/h",
        f"",
        f"  📅 3-Day Forecast:",
    ]

    dates    = daily.get("time", [])
    max_t    = daily.get("temperature_2m_max", [])
    min_t    = daily.get("temperature_2m_min", [])
    precip   = daily.get("precipitation_sum", [])
    d_wcodes = daily.get("weathercode", [])

    for i in range(min(3, len(dates))):
        day_cond = WMO_CODES.get(d_wcodes[i] if i < len(d_wcodes) else 0, "")
        rain     = precip[i] if i < len(precip) else 0
        hi       = max_t[i] if i < len(max_t) else "?"
        lo       = min_t[i] if i < len(min_t) else "?"
        rain_str = f"  🌧 {rain}mm" if rain and rain > 0 else ""
        lines.append(
            f"  {dates[i]}  ↑{hi}{unit} ↓{lo}{unit}  {day_cond}{rain_str}"
        )

    return "\n".join(lines)


def extract_weather_location(text: str) -> str:
    """
    Strip all weather-related command words to get just the location.
    Handles missing apostrophes, extra spaces, punctuation variations.
    """
    # Normalize: lowercase, collapse spaces, strip punctuation at ends
    normalized = text.strip().rstrip("?!.").strip()

    # Use regex to match any variant of weather question and capture location
    patterns = [
        # "what's/whats/what is the weather in/for/at <location>"
        r"(?:what'?s|what\s+is)\s+the\s+weather\s+(?:in|for|at)\s+(.+)",
        # "how's/hows/how is the weather in <location>"
        r"(?:how'?s|how\s+is)\s+the\s+weather\s+(?:in|for|at)\s+(.+)",
        # "weather today in/for/at <location>"
        r"weather\s+today\s+(?:in|for|at)\s+(.+)",
        # "weather in/for/at <location>"
        r"weather\s+(?:in|for|at)\s+(.+)",
        # "tell me the weather in <location>"
        r"tell\s+me\s+(?:the\s+)?weather\s+(?:in|for|at)\s+(.+)",
        # "what's/whats the weather <location>" (no preposition)
        r"(?:what'?s|what\s+is)\s+the\s+weather\s+(.+)",
        # "weather <location>"
        r"weather\s+(.+)",
    ]

    lower = normalized.lower()
    for pattern in patterns:
        match = re.match(pattern, lower, re.IGNORECASE)
        if match:
            # Return the matched portion from the ORIGINAL text (preserve casing)
            start = match.start(1)
            end = match.end(1)
            return normalized[start:end].strip()

    # Fallback: return as-is (maybe user typed just a city name)
    return normalized


def weather_tool(text: str) -> str:
    location = extract_weather_location(text)
    if not location or location.lower() in ("today", "now", "outside", ""):
        return (
            "🌍 Please specify a location, e.g.:\n"
            '  "weather in London"\n'
            '  "weather in New York"\n'
            '  "weather in Tokyo"'
        )
    return get_weather(location)