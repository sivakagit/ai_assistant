"""
tools/web_search_tool.py
Multi-source web search with smart answer extraction.
Skips blocked/paywalled sites, tries multiple sources, returns clean answers.
No API key required.
"""

import requests
import urllib.parse
import re
import html as html_module


# ── Sites known to block scrapers ────────────────────────────────────────────

BLOCKED_DOMAINS = {
    "espncricinfo.com", "espn.com", "cricbuzz.com",
    "nytimes.com", "wsj.com", "bloomberg.com",
    "ft.com", "economist.com", "medium.com",
    "quora.com", "linkedin.com", "facebook.com",
    "instagram.com", "twitter.com", "x.com",
}

# ── Headers that mimic a real browser ────────────────────────────────────────

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


# ── HTML Cleaner ──────────────────────────────────────────────────────────────

def _clean_html(raw: str) -> str:
    for tag in ("script", "style", "nav", "header", "footer",
                "aside", "form", "noscript", "iframe", "svg",
                "figure", "figcaption", "picture"):
        raw = re.sub(
            rf"<{tag}[^>]*>.*?</{tag}>", "",
            raw, flags=re.DOTALL | re.IGNORECASE
        )
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = html_module.unescape(raw)
    raw = re.sub(r"&[a-zA-Z]{2,8};", " ", raw)
    raw = re.sub(r"&#\d+;", " ", raw)
    raw = re.sub(r"[ \t]+", " ", raw)
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    return raw.strip()


# ── Language / Quality Filters ────────────────────────────────────────────────

def _is_mostly_english(text: str, threshold: float = 0.82) -> bool:
    if not text:
        return False
    return (sum(1 for c in text if ord(c) < 128) / len(text)) >= threshold


_JUNK = re.compile(
    r"(cookie|subscribe|newsletter|sign up|log in|sign in|"
    r"privacy policy|terms of (use|service)|all rights reserved|"
    r"click here|read more|advertisement|follow us|share this|"
    r"copyright ©|©\s*\d{4}|\bads?\b|menu|navigation|"
    r"our mission|we are proud|about us|contact us)",
    re.IGNORECASE
)

_NEEDS_VERB = re.compile(
    r"\b(is|are|was|were|has|have|had|will|would|can|"
    r"says|said|shows|costs|cost|price|rate|rates|"
    r"scored|score|won|lost|beat|leads|hit|made|reached|"
    r"result|results|match|matches|goal|goals|point|points|"
    r"defeated|drew|draw|tied|leads|won|lost)\b",
    re.IGNORECASE
)


def _is_good_sentence(s: str) -> bool:
    s = s.strip()
    if len(s) < 35 or len(s) > 600:
        return False
    if not _is_mostly_english(s, 0.82):
        return False
    if _JUNK.search(s):
        return False
    special = sum(1 for c in s if c in "»«›‹|/\\→←►◄")
    if special > 2:
        return False
    if not _NEEDS_VERB.search(s):
        return False
    return True


# ── Relevance Scorer ──────────────────────────────────────────────────────────

_STOP = {
    "the","a","an","is","are","was","were","what","who","how","when",
    "where","which","for","of","in","on","at","to","and","or","do",
    "does","did","me","my","i","you","today","tell","search","find",
    "give","show","get","please","can","could","would","should"
}

def _query_words(query: str) -> set:
    return set(re.sub(r"[^\w\s]", "", query.lower()).split()) - _STOP


def _extract_best_answer(text: str, query: str, max_sent: int = 5) -> str:
    text = " ".join(
        s for s in re.split(r'(?<=[.!?])\s+', text)
        if _is_mostly_english(s, 0.82)
    )
    sentences = re.split(r'(?<=[.!?])\s+', text)
    qwords = _query_words(query)

    scored = []
    for s in sentences:
        if not _is_good_sentence(s):
            continue
        score = sum(1 for w in qwords if w in s.lower())
        if score > 0:
            scored.append((score, s))

    if not scored:
        good = [s for s in sentences if _is_good_sentence(s)]
        return " ".join(good[:max_sent])

    top_set = {s for _, s in sorted(scored, key=lambda x: -x[0])[:max_sent]}
    ordered = [s for s in sentences if s in top_set]

    seen, result = set(), []
    for s in ordered:
        k = s.lower()[:50]
        if k not in seen:
            seen.add(k)
            result.append(s)

    return " ".join(result)


# ── DDG Instant Answer ────────────────────────────────────────────────────────

def _ddg_instant(query: str):
    try:
        r = requests.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json",
                    "no_html": "1", "skip_disambig": "1"},
            timeout=8, headers={"User-Agent": "NovaAssistant/1.0"},
        )
        d = r.json()
        if d.get("AbstractText") and len(d["AbstractText"]) > 40:
            return d["AbstractText"], d.get("AbstractURL", "")
        if d.get("Answer"):
            return d["Answer"], ""
    except Exception:
        pass
    return None, None


# ── DDG Search → URLs ─────────────────────────────────────────────────────────

def _ddg_urls(query: str, max_urls: int = 6) -> list:
    """Return up to max_urls real URLs, skipping blocked domains."""
    try:
        encoded = urllib.parse.quote_plus(query)
        r = requests.get(
            f"https://lite.duckduckgo.com/lite/?q={encoded}",
            timeout=8, headers=HEADERS,
        )
        raw_links = re.findall(r'uddg=([^&"\'>\s]+)', r.text)
        urls = []
        for raw in raw_links:
            url = urllib.parse.unquote(raw)
            if not url.startswith("http"):
                continue
            domain = urllib.parse.urlparse(url).netloc.replace("www.", "")
            if domain in BLOCKED_DOMAINS:
                continue
            if url not in urls:
                urls.append(url)
            if len(urls) >= max_urls:
                break
        return urls
    except Exception:
        return []


# ── Page Fetcher ──────────────────────────────────────────────────────────────

def _fetch(url: str, max_chars: int = 5000) -> str:
    """Fetch a URL, return clean text or '' on failure/block."""
    try:
        r = requests.get(url, timeout=7, headers=HEADERS)
        # Detect access denied
        if r.status_code in (401, 403, 429):
            return ""
        text = _clean_html(r.text)
        # Secondary check: if page says "access denied" in first 200 chars
        if re.search(r"access denied|403 forbidden|permission denied",
                     text[:200], re.IGNORECASE):
            return ""
        return text[:max_chars]
    except Exception:
        return ""


# ── Google Cache Fallback ─────────────────────────────────────────────────────

def _try_google_cache(url: str) -> str:
    """Try Google's cached version if the original is blocked."""
    cache_url = f"https://webcache.googleusercontent.com/search?q=cache:{url}"
    try:
        r = requests.get(cache_url, timeout=7, headers=HEADERS)
        if r.status_code == 200:
            text = _clean_html(r.text)
            if len(text) > 200:
                return text[:5000]
    except Exception:
        pass
    return ""


# ── Main Search ───────────────────────────────────────────────────────────────

def web_search(query: str) -> str:
    query = query.strip()
    if not query:
        return "Please provide a search query."

    # 1. DDG instant answer
    instant, source = _ddg_instant(query)
    if instant and _is_mostly_english(instant):
        out = f"🔍 {query}\n\n{instant}"
        if source:
            out += f"\n\nSource: {source}"
        return out

    # 2. Get URLs (blocked domains already filtered)
    urls = _ddg_urls(query, max_urls=6)
    if not urls:
        if instant:
            return f"🔍 {query}\n\n{instant}"
        return f"🔍 {query}\n\nNo results found. Check your internet connection."

    # 3. Try each URL, skip if access denied, try cache as fallback
    answers = []
    for url in urls:
        page_text = _fetch(url)
        if not page_text:
            page_text = _try_google_cache(url)
        if not page_text:
            continue

        answer = _extract_best_answer(page_text, query)
        if answer and len(answer) > 60:
            answers.append(answer)

        if len(answers) >= 2:
            break

    if not answers:
        if instant:
            return f"🔍 {query}\n\n{instant}"
        return (
            f"🔍 {query}\n\n"
            "Couldn't extract a clear answer from available sources. "
            "Try rephrasing your query."
        )

    # 4. Merge, deduplicate, cap at 6 clean sentences
    combined = " ".join(answers)
    seen, final = set(), []
    for s in re.split(r'(?<=[.!?])\s+', combined):
        k = s.lower()[:50]
        if k not in seen and _is_good_sentence(s):
            seen.add(k)
            final.append(s)

    return f"🔍 {query}\n\n" + " ".join(final[:6])


# ── Query Extractor ───────────────────────────────────────────────────────────

def extract_search_query(text: str) -> str:
    text = text.strip()
    prefixes = [
        "search the web for", "search web for", "web search for",
        "find information on", "find info on", "search for",
        "look up", "google", "web search", "browse for",
        "internet search", "search",
    ]
    lower = text.lower()
    for prefix in sorted(prefixes, key=len, reverse=True):
        if lower.startswith(prefix):
            return text[len(prefix):].strip()
    return text


# ── Entry Point ───────────────────────────────────────────────────────────────

def web_search_tool(text: str) -> str:
    query = extract_search_query(text)
    return web_search(query)