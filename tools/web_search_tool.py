"""
tools/web_search_tool.py
Web search via DuckDuckGo Instant Answer API — no API key required.
"""

import requests
import urllib.parse
import re


def _clean_ddg_redirect(url: str) -> str:
    """
    DuckDuckGo wraps outbound links in a redirect URL like:
      //duckduckgo.com/l/?uddg=<encoded_real_url>&...
    This function extracts and decodes the real destination URL.
    Returns the original string if it doesn't look like a DDG redirect.
    """
    if not url:
        return url
    # Remove leading // if present
    if url.startswith("//"):
        url = "https:" + url
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query)
    if "uddg" in params:
        return urllib.parse.unquote(params["uddg"][0])
    return url


def web_search(query: str, max_results: int = 5) -> str:
    """
    Search DuckDuckGo and return a formatted string of results.
    Uses the free DuckDuckGo Instant Answer JSON API.
    Falls back to HTML scrape for more results when the instant
    answer returns nothing useful.
    """
    query = query.strip()
    if not query:
        return "Please provide a search query."

    # ── 1. Try Instant Answer API first ──────────────────────────────────────
    try:
        params = {
            "q": query,
            "format": "json",
            "no_html": "1",
            "skip_disambig": "1",
        }
        r = requests.get(
            "https://api.duckduckgo.com/",
            params=params,
            timeout=8,
            headers={"User-Agent": "NovaAssistant/1.0"},
        )
        data = r.json()

        lines = []

        # Abstract (Wikipedia-style summary)
        if data.get("AbstractText"):
            lines.append(f"📖 {data['AbstractText']}")
            if data.get("AbstractURL"):
                lines.append(f"   Source: {data['AbstractURL']}")
            lines.append("")

        # Answer (e.g. "What is 2+2")
        if data.get("Answer"):
            lines.append(f"✅ {data['Answer']}")
            lines.append("")

        # Related topics
        topics = data.get("RelatedTopics", [])
        count = 0
        for topic in topics:
            if count >= max_results:
                break
            if isinstance(topic, dict) and topic.get("Text"):
                lines.append(f"• {topic['Text']}")
                if topic.get("FirstURL"):
                    clean_url = _clean_ddg_redirect(topic["FirstURL"])
                    lines.append(f"  🔗 {clean_url}")
                count += 1
            elif isinstance(topic, dict) and topic.get("Topics"):
                for sub in topic["Topics"]:
                    if count >= max_results:
                        break
                    if sub.get("Text"):
                        lines.append(f"• {sub['Text']}")
                        if sub.get("FirstURL"):
                            clean_url = _clean_ddg_redirect(sub["FirstURL"])
                            lines.append(f"  🔗 {clean_url}")
                        count += 1

        if lines:
            return f"🔍 Web Search: {query}\n\n" + "\n".join(lines)

    except Exception:
        pass

    # ── 2. Fallback: HTML search (lite.duckduckgo.com) ───────────────────────
    try:
        encoded = urllib.parse.quote_plus(query)
        url = f"https://lite.duckduckgo.com/lite/?q={encoded}"
        r = requests.get(
            url,
            timeout=8,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 Chrome/120 Safari/537.36"
            },
        )
        html = r.text

        # Extract result snippets
        snippets = re.findall(
            r'class=["\']result-snippet["\'][^>]*>(.*?)</(?:td|span)>',
            html,
            re.DOTALL | re.IGNORECASE,
        )

        # Extract and clean redirect URLs → real URLs
        raw_links = re.findall(
            r'href=["\'](?:https?:)?//duckduckgo\.com/l/\?uddg=(.*?)[&"\']',
            html,
        )
        clean_links = [urllib.parse.unquote(lnk) for lnk in raw_links]

        results = []
        for i, snippet in enumerate(snippets[:max_results]):
            clean_text = re.sub(r"<[^>]+>", "", snippet).strip()
            if clean_text:
                results.append(f"• {clean_text}")
                if i < len(clean_links) and clean_links[i]:
                    results.append(f"  🔗 {clean_links[i]}")

        if results:
            return f"🔍 Web Search: {query}\n\n" + "\n".join(results)

    except Exception:
        pass

    return (
        f"🔍 Searched for: {query}\n\n"
        "No results found. Check your internet connection or try a different query."
    )


def extract_search_query(text: str) -> str:
    """Strip command prefixes to get the bare search query."""
    text = text.strip()
    prefixes = [
        "search the web for",
        "search web for",
        "web search for",
        "search for",
        "google",
        "look up",
        "find info on",
        "find information on",
        "search",
        "web search",
    ]
    lower = text.lower()
    for prefix in sorted(prefixes, key=len, reverse=True):  # longest first
        if lower.startswith(prefix):
            return text[len(prefix):].strip()
    return text


def web_search_tool(text: str) -> str:
    query = extract_search_query(text)
    return web_search(query)