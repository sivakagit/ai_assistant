from __future__ import annotations

"""
tools/web_search_tool.py  —  v4

Changes from v3:
- Integrates result_processor.py pipeline (clean → rank → extract → merge → confidence)
- Tavily now collects ALL results, not just the first one
- DDG fallback also feeds multiple pages into the pipeline
- process_with_llm gets structured context, not raw HTML
- Query rewriter expanded (stock, news, sports, general)
- Confidence shown in output when < 0.7
"""

import requests
import urllib.parse
import re
import html as html_module
from datetime import datetime
import time
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from cachetools import TTLCache

# --------------------------------------------------
# LOGGER SETUP
# --------------------------------------------------

try:
    from core.logger import get_logger as _get_logger
    _log = _get_logger()
except Exception:
    import logging
    _log = logging.getLogger(__name__)

# Import the new pipeline
from tools.result_processor import (
    process_results,
    detect_query_type,
    extract_best_snippet,
    ProcessedAnswer,
)


# --------------------------------------------------
# CONFIG
# --------------------------------------------------

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}

BLOCKED_DOMAINS = {
    "thehindu.com", "hindustantimes.com", "timesofindia.com",
    "economictimes.com", "livemint.com", "businessstandard.com",
    "financialexpress.com", "ndtv.com", "telegraphindia.com",
    "theprint.in", "thewire.in", "goodreturns.in", "moneycontrol.com",
    "investing.com", "tradingeconomics.com", "marketwatch.com",
    "tickertape.in", "screener.in", "duckduckgo.com", "bing.com",
    "google.com", "facebook.com", "instagram.com", "twitter.com",
    "x.com", "linkedin.com", "reddit.com",
    "espncricinfo.com", "cricbuzz.com", "foxnews.com",
    "indiatimes.com", "timesofindia.indiatimes.com",
}

REQUEST_TIMEOUT     = 8
MAX_URLS_TO_TRY     = 4          # increased from 3 — more sources = better merging
RETRY_DELAY         = 1.5


# --------------------------------------------------
# TTL CACHE
# --------------------------------------------------

_cache = TTLCache(maxsize=128, ttl=600)


# --------------------------------------------------
# OUTPUT FORMAT
# --------------------------------------------------

def format_output(query: str, answer: str, source: str = "", confidence: float = 1.0) -> str:
    timestamp = datetime.now().strftime("%H:%M")
    lines     = [f"🔍 {query}", "", answer.strip(), "", f"Updated: {timestamp}"]
    if source:
        lines.append(f"Source: {source}")
    if confidence < 0.7:
        lines.append(f"⚠️ Confidence: {int(confidence * 100)}% — verify this answer")
    return "\n".join(lines)


# --------------------------------------------------
# WEATHER — Open-Meteo (free, no API key needed)
# --------------------------------------------------

DEFAULT_LAT  = 31.326
DEFAULT_LON  = 75.576
DEFAULT_CITY = "Jalandhar"

_WMO_CODES = {
    0:  "Clear sky",          1:  "Mainly clear",        2:  "Partly cloudy",
    3:  "Overcast",           45: "Foggy",                48: "Icy fog",
    51: "Light drizzle",      53: "Moderate drizzle",     55: "Dense drizzle",
    61: "Slight rain",        63: "Moderate rain",        65: "Heavy rain",
    71: "Slight snow",        73: "Moderate snow",        75: "Heavy snow",
    80: "Slight showers",     81: "Moderate showers",     82: "Violent showers",
    95: "Thunderstorm",       96: "Thunderstorm w/ hail", 99: "Thunderstorm w/ heavy hail",
}


def _get_weather(query: str) -> str | None:
    try:
        lat, lon, city = DEFAULT_LAT, DEFAULT_LON, DEFAULT_CITY

        q_lower = query.lower()
        for skip in ["weather", "temperature", "today", "in", "at",
                     "of", "the", "current", "what", "is", "whats"]:
            q_lower = q_lower.replace(skip, " ")
        city_guess = q_lower.strip().title()

        if city_guess and len(city_guess) > 2:
            geo = requests.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={"name": city_guess, "count": 1,
                        "language": "en", "format": "json"},
                timeout=5,
            ).json()
            results = geo.get("results")
            if results:
                lat  = results[0]["latitude"]
                lon  = results[0]["longitude"]
                city = results[0].get("name", city_guess)

        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude":        lat,
                "longitude":       lon,
                "current_weather": "true",
                "hourly":          "relative_humidity_2m,apparent_temperature",
                "forecast_days":   1,
                "timezone":        "Asia/Kolkata",
            },
            timeout=6,
        ).json()

        cw   = r.get("current_weather", {})
        temp = cw.get("temperature")
        wind = cw.get("windspeed")
        code = cw.get("weathercode", 0)
        desc = _WMO_CODES.get(code, "Unknown")

        feels_like = None
        try:
            feels_like = r["hourly"]["apparent_temperature"][0]
        except Exception:
            pass

        lines = [f"📍 {city}", f"🌡️  Temperature : {temp}°C"]
        if feels_like is not None:
            lines.append(f"🤔 Feels like  : {feels_like}°C")
        lines += [
            f"💨 Wind speed  : {wind} km/h",
            f"🌤️  Condition   : {desc}",
        ]
        return "\n".join(lines)

    except Exception:
        return None


# --------------------------------------------------
# TAVILY SEARCH (primary) — now returns ALL results
# --------------------------------------------------

def _tavily_search(query: str) -> tuple[str | None, str, list[dict]]:
    """
    Returns:
        (direct_answer_or_None, source_url, list_of_raw_results)
    """
    api_key = os.environ.get("TAVILY_API_KEY", "")
    if not api_key:
        _log.warning("[WebSearch] ⚠️  TAVILY_API_KEY not set — Tavily skipped")
        return None, "", []

    _log.info(f"[WebSearch] 🌐 Tavily API request — query={query!r}")
    try:
        payload = {
            "api_key":             api_key,
            "query":               query,
            "search_depth":        "basic",
            "include_answer":      True,
            "include_raw_content": False,
            "max_results":         5,
        }
        r    = requests.post("https://api.tavily.com/search", json=payload, timeout=10)
        data = r.json()

        raw_results = [
            {"url": item.get("url", ""), "text": item.get("content", "")}
            for item in data.get("results", [])
            if item.get("content")
        ]

        direct_answer = data.get("answer", "").strip() or None
        top_source    = raw_results[0]["url"] if raw_results else ""

        _log.info(
            f"[WebSearch] ✅ Tavily returned {len(raw_results)} result(s) — "
            f"direct_answer={'yes' if direct_answer else 'no'} — "
            f"top_source={top_source!r}"
        )
        return direct_answer, top_source, raw_results

    except Exception as e:
        _log.error(f"[WebSearch] ❌ Tavily API error: {e!r}")

    return None, "", []


# --------------------------------------------------
# HTML CLEANER
# --------------------------------------------------

def clean_html(raw: str) -> str:
    for tag in ["script", "style", "nav", "footer", "header",
                "aside", "form", "noscript", "iframe", "menu"]:
        raw = re.sub(rf"<{tag}[^>]*>.*?</{tag}>", " ", raw,
                     flags=re.DOTALL | re.IGNORECASE)

    raw = re.sub(
        r'\b(var|let|const|function|window\.|document\.|localStorage'
        r'|CACHEBUSTER|Math\.|Date\.now|\.src\s*=|\.async\s*=)\b'
        r'[^<]{0,300}[;{]', " ", raw
    )

    text = re.sub(r"<[^>]+>", " ", raw)
    text = html_module.unescape(text)

    _JS_GARBAGE = re.compile(
        r'(localStorage|CACHEBUSTER|document\.|window\.|getItem|'
        r'setItem|Math\.floor|Date\.now|\bconst\b|\bvar\b|\blet\b|'
        r'=>|\bfunction\b|createElement|cfasync|oiadconfig)',
        re.IGNORECASE
    )
    sentences = re.split(r'(?<=[.!?])\s+|\n', text)
    text = " ".join(s for s in sentences if not _JS_GARBAGE.search(s))
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# --------------------------------------------------
# DUCKDUCKGO INSTANT ANSWER (fast fallback)
# --------------------------------------------------

def ddg_instant(query: str) -> tuple[str | None, str]:
    _log.info(f"[WebSearch] 🦆 DDG instant answer — query={query!r}")
    try:
        r    = requests.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_redirect": "1"},
            headers=HEADERS, timeout=REQUEST_TIMEOUT,
        )
        data = r.json()
        if data.get("Answer"):
            _log.info(f"[WebSearch] ✅ DDG instant — Answer field hit")
            return data["Answer"], data.get("AbstractURL", "")
        if data.get("AbstractText"):
            _log.info(f"[WebSearch] ✅ DDG instant — AbstractText hit")
            return data["AbstractText"], data.get("AbstractURL", "")
        if data.get("Definition"):
            _log.info(f"[WebSearch] ✅ DDG instant — Definition hit")
            return data["Definition"], data.get("DefinitionURL", "")
        infobox = data.get("Infobox", {})
        if isinstance(infobox, dict):
            content = infobox.get("content", [])
            if content:
                lines = [
                    f"{i.get('label')}: {i.get('value')}"
                    for i in content[:5]
                    if i.get("label") and i.get("value")
                ]
                if lines:
                    _log.info(f"[WebSearch] ✅ DDG instant — Infobox hit")
                    return "\n".join(lines), ""
    except Exception as e:
        _log.warning(f"[WebSearch] ⚠️  DDG instant error: {e!r}")
    _log.info("[WebSearch] ℹ️  DDG instant — no answer found")
    return None, None


# --------------------------------------------------
# DDG URL SCRAPER (last-resort URL list)
# --------------------------------------------------

def ddg_urls(query: str) -> list[str]:
    _log.info(f"[WebSearch] 🔧 DDG scraping — query={query!r}")
    try:
        encoded   = urllib.parse.quote_plus(query)
        r         = requests.get(
            f"https://lite.duckduckgo.com/lite/?q={encoded}",
            timeout=REQUEST_TIMEOUT, headers=HEADERS,
        )
        raw_links = re.findall(r'uddg=([^&"\'>\s]+)', r.text)
        urls: list[str] = []
        for raw in raw_links:
            url = urllib.parse.unquote(raw)
            if not url.startswith("http"):
                continue
            if "duckduckgo.com/y.js" in url:
                continue
            if "uddg=" in url:
                inner = re.search(r'uddg=([^&]+)', url)
                if inner:
                    url = urllib.parse.unquote(inner.group(1))
            domain = urllib.parse.urlparse(url).netloc.replace("www.", "")
            if domain in BLOCKED_DOMAINS:
                continue
            if url not in urls:
                urls.append(url)
            if len(urls) >= MAX_URLS_TO_TRY:
                break
        _log.info(f"[WebSearch] ✅ DDG scraping found {len(urls)} URL(s): {urls}")
        return urls
    except Exception as e:
        _log.error(f"[WebSearch] ❌ DDG scraping error: {e!r}")
        return []


# --------------------------------------------------
# PAGE FETCHER
# --------------------------------------------------

def _fetch_page(url: str, attempt: int = 1) -> str | None:
    try:
        r = requests.get(url, timeout=REQUEST_TIMEOUT, headers=HEADERS)
        _log.info(f"[WebSearch] 📄 Fetched page — url={url!r} status={r.status_code} size={len(r.text)}")
        return r.text[:80000]
    except requests.exceptions.Timeout:
        _log.warning(f"[WebSearch] ⏱️  Page fetch timeout — url={url!r} attempt={attempt}")
        if attempt < 2:
            time.sleep(RETRY_DELAY)
            return _fetch_page(url, attempt=2)
        return None
    except Exception as e:
        _log.warning(f"[WebSearch] ⚠️  Page fetch error — url={url!r} error={e!r}")
        return None


def _fetch_pages_parallel(urls: list[str]) -> list[tuple[str, str]]:
    _log.info(f"[WebSearch] 🔀 Parallel fetch — {len(urls)} URL(s)")
    results = {}
    with ThreadPoolExecutor(max_workers=min(len(urls), 4)) as executor:
        future_to_url = {executor.submit(_fetch_page, url): url for url in urls}
        for future in as_completed(future_to_url):
            url  = future_to_url[future]
            html = future.result()
            if html:
                results[url] = html
    _log.info(f"[WebSearch] ✅ Parallel fetch complete — {len(results)}/{len(urls)} pages fetched")
    return [(url, results[url]) for url in urls if url in results]


# --------------------------------------------------
# PAYWALL DETECTOR
# --------------------------------------------------

_BLOCKED_PAGE_SIGNALS = [
    "subscribe to continue", "subscription required", "sign in to read",
    "log in to continue", "create an account", "already logged in from more than",
    "remove at least one device", "unlimited access", "digital subscription",
    "you have reached your limit", "register to read", "please log in",
]


def _is_blocked_page(html: str) -> bool:
    sample  = html[:5000].lower()
    blocked = any(signal in sample for signal in _BLOCKED_PAGE_SIGNALS)
    if blocked:
        _log.info("[WebSearch] 🚫 Page blocked by paywall/login wall — skipping")
    return blocked


# --------------------------------------------------
# QUERY REWRITER (expanded)
# --------------------------------------------------

def _rewrite_query(query: str) -> str:
    original = query
    q = query.lower()

    # Gold / silver prices
    if any(metal in q for metal in ["gold", "silver"]) and \
       any(w in q for w in ["price", "rate", "today", "cost"]):
        if "today" not in q:
            query += " today"
        if query != original:
            _log.info(f"[WebSearch] ✏️  Query rewritten: {original!r} → {query!r}")
        return query

    # Cricket / IPL scores
    if any(w in q for w in ["ipl", "cricket", "match"]) and "score" not in q:
        if any(w in q for w in ["yesterday", "today", "latest", "live"]):
            query += " scorecard result"

    # Stock prices
    if any(w in q for w in ["stock", "share", "nse", "bse"]) and "price" not in q:
        query += " price today"

    # News queries — append "latest" if missing
    if any(w in q for w in ["news", "update", "happening"]) and "latest" not in q:
        query = "latest " + query

    if query != original:
        _log.info(f"[WebSearch] ✏️  Query rewritten: {original!r} → {query!r}")
    return query


# --------------------------------------------------
# LLM FALLBACK — now receives STRUCTURED context
# --------------------------------------------------

def process_with_llm(query: str, structured_context: str) -> str | None:
    """
    Call local LLM with clean, structured context instead of raw HTML.
    structured_context should already be clean text with key facts.
    """
    _log.info(f"[WebSearch] 🤖 LLM fallback triggered — query={query!r} context_len={len(structured_context)}")
    try:
        import ollama
        from core.config import get_setting
        model   = get_setting("model") or "qwen2.5:3b"
        trimmed = structured_context[:2500]

        # ── UPGRADED PROMPT ──────────────────────────────────────────────────
        query_type = detect_query_type(query)
        type_hints = {
            "numeric":    "Focus on extracting exact numbers, prices, or scores.",
            "factual":    "Focus on extracting the specific fact, name, or entity asked.",
            "comparison": "Compare the options clearly with pros/cons if possible.",
            "news":       "Summarise the key event, who is involved, and when.",
            "general":    "Give a clear, concise answer using only the provided facts.",
        }
        hint = type_hints.get(query_type, type_hints["general"])

        prompt = (
            f"You are given verified, structured facts extracted from multiple web sources.\n"
            f"User question: \"{query}\"\n\n"
            f"Facts from sources:\n---\n{trimmed}\n---\n\n"
            f"Instructions:\n"
            f"- {hint}\n"
            f"- Be concise (2-5 sentences or short bullet points).\n"
            f"- Include specific numbers, names, or dates if present.\n"
            f"- Do NOT add information not in the sources.\n"
            f"- If the answer is not in the sources, reply: Not found in available sources.\n"
            f"- No preamble. Answer directly.\n"
        )
        # ────────────────────────────────────────────────────────────────────

        response = ollama.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.1},
        )
        answer = response["message"]["content"].strip()
        if answer and "not found" not in answer.lower():
            _log.info(f"[WebSearch] ✅ Ollama answered — model={model!r} answer_len={len(answer)}")
            return answer
        _log.info("[WebSearch] ℹ️  Ollama replied 'not found' — trying llm_service fallback")

    except Exception as e:
        try:
            _log.warning(f"[WebSearch] Ollama failed: {e!r}")
        except Exception:
            pass

    try:
        from services.llm_service import ask_llm
        trimmed  = structured_context[:3000]
        prompt   = (
            f"Answer this question using ONLY the facts below.\n"
            f"Question: {query}\n\n"
            f"Facts:\n{trimmed}\n\n"
            f"Answer (concise, under 100 words):"
        )
        response = ask_llm(prompt)
        if response:
            return response.strip()
    except Exception as e:
        try:
            _log.warning(f"[WebSearch] llm_service failed: {e!r}")
        except Exception:
            pass

    return None


# --------------------------------------------------
# MAIN SEARCH  (v4 — pipeline-powered)
# --------------------------------------------------

def web_search(query: str) -> str:
    query = query.strip()
    if not query:
        return "Please provide a search query."

    # 1 — TTL Cache
    cache_key = query.lower()
    if cache_key in _cache:
        _log.info(f"[WebSearch] ⚡ Cache hit — query={query!r}")
        return _cache[cache_key]

    _log.info(f"[WebSearch] 🔍 New search — query={query!r}")

    # 2 — Weather (dedicated API, skip pipeline)
    q_lower = query.lower()
    if "weather" in q_lower or "temperature" in q_lower:
        _log.info("[WebSearch] 🌦️  Weather query detected — using Open-Meteo API")
        weather = _get_weather(query)
        if weather:
            result = format_output(query, weather, "open-meteo.com")
            _cache[cache_key] = result
            return result
        _log.warning("[WebSearch] ⚠️  Open-Meteo returned nothing — falling through")

    query = _rewrite_query(query)

    # 3 — Tavily (primary): collect all results for multi-source pipeline
    tavily_direct, tavily_source, tavily_raw = _tavily_search(query)

    if tavily_raw:
        _log.info(f"[WebSearch] 🔬 Running pipeline on {len(tavily_raw)} Tavily result(s)")
        # Run through the full pipeline first
        processed: ProcessedAnswer | None = process_results(query, tavily_raw)

        if processed and processed.confidence >= 0.4:
            _log.info(
                f"[WebSearch] ✅ Pipeline success — "
                f"type={processed.query_type!r} confidence={processed.confidence} "
                f"sources_agree={processed.sources_agree} source={processed.source!r}"
            )
            result = format_output(
                query,
                processed.answer,
                processed.source or tavily_source,
                processed.confidence,
            )
            _cache[cache_key] = result
            return result

        _log.warning(
            f"[WebSearch] ⚠️  Pipeline low confidence "
            f"({processed.confidence if processed else 'N/A'}) — trying direct Tavily answer"
        )

        # Pipeline gave low confidence — try the direct Tavily answer
        if tavily_direct:
            _log.info("[WebSearch] ✅ Using Tavily direct answer as fallback")
            result = format_output(query, tavily_direct, tavily_source)
            _cache[cache_key] = result
            return result

        # Pipeline gave low confidence — ask LLM with merged context
        merged_text = " ".join(r["text"] for r in tavily_raw[:3] if r.get("text"))
        if merged_text:
            _log.info("[WebSearch] 🤖 Sending merged Tavily context to LLM")
            llm_answer = process_with_llm(query, merged_text)
            if llm_answer:
                result = format_output(query, llm_answer, tavily_source, confidence=0.6)
                _cache[cache_key] = result
                return result

    else:
        _log.info("[WebSearch] ℹ️  No Tavily results — moving to DDG instant answer")

    # 4 — DDG instant answer (fast, no scraping needed)
    instant, source = ddg_instant(query)
    if instant:
        _log.info(f"[WebSearch] ✅ DDG instant answer used — source={source!r}")
        result = format_output(query, instant, source)
        _cache[cache_key] = result
        return result

    # 5 — DDG scraping + parallel fetch + full pipeline
    _log.info("[WebSearch] 🔧 Falling back to DDG scraping")
    urls = ddg_urls(query)
    if not urls:
        _log.warning("[WebSearch] ❌ DDG scraping returned no URLs")
        return format_output(query, "No results found.")

    fetched = _fetch_pages_parallel(urls)
    raw_results: list[dict] = []

    for url, html in fetched:
        try:
            if _is_blocked_page(html):
                continue
            text = clean_html(html)
            if text and len(text) >= 100:
                raw_results.append({"url": url, "text": text})
            else:
                _log.info(f"[WebSearch] ⚠️  Skipping page — too short after cleaning: {url!r}")
        except Exception as e:
            _log.warning(f"[WebSearch] ⚠️  HTML clean error — url={url!r} error={e!r}")
            continue

    if not raw_results:
        _log.warning("[WebSearch] ❌ All scraped pages were blocked or empty")
        return format_output(query, "Found results but could not extract content.")

    # Run the pipeline on scraped results
    _log.info(f"[WebSearch] 🔬 Running pipeline on {len(raw_results)} scraped page(s)")
    processed = process_results(query, raw_results)
    if processed and processed.confidence >= 0.35:
        _log.info(
            f"[WebSearch] ✅ Scrape pipeline success — "
            f"confidence={processed.confidence} source={processed.source!r}"
        )
        result = format_output(
            query,
            processed.answer,
            processed.source,
            processed.confidence,
        )
        _cache[cache_key] = result
        return result

    # Last resort: LLM on best scraped text
    _log.info("[WebSearch] 🤖 Pipeline confidence too low — sending scraped text to LLM")
    best_text = raw_results[0]["text"]
    llm_answer = process_with_llm(query, best_text)
    if llm_answer:
        result = format_output(query, llm_answer, raw_results[0]["url"], confidence=0.5)
        _cache[cache_key] = result
        return result

    # Absolute last resort: keyword snippet
    _log.warning("[WebSearch] ⚠️  All methods failed — using raw keyword snippet")
    snippet = extract_best_snippet(best_text, query)
    result  = format_output(query, snippet, raw_results[0]["url"], confidence=0.3)
    _cache[cache_key] = result
    return result


# --------------------------------------------------
# QUERY CLEANER
# --------------------------------------------------

def extract_search_query(text: str) -> str:
    prefixes = [
        "search the web for", "search web for", "web search",
        "look up", "google", "search",
    ]
    lower = text.lower().strip()
    for prefix in prefixes:
        if lower.startswith(prefix):
            return text[len(prefix):].strip()
    return text


# --------------------------------------------------
# ENTRY POINT
# --------------------------------------------------

def web_search_tool(text: str) -> str:
    query = extract_search_query(text)
    _log.info(f"[WebSearch] 📥 Tool entry — raw={text!r} parsed_query={query!r}")
    return web_search(query)