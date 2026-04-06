"""
tools/result_processor.py

Post-processing pipeline for web search results.
Handles: structured extraction, relevance ranking, noise cleaning,
multi-source fact merging, and confidence scoring.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# ─────────────────────────────────────────────
# DATA STRUCTURES
# ─────────────────────────────────────────────

@dataclass
class SearchResult:
    url:     str
    text:    str
    score:   float = 0.0
    facts:   dict  = field(default_factory=dict)


@dataclass
class ProcessedAnswer:
    answer:     str
    source:     str
    confidence: float          # 0.0 – 1.0
    query_type: str            # "numeric" | "factual" | "comparison" | "news" | "general"
    sources_agree: bool = True


# ─────────────────────────────────────────────
# QUERY TYPE DETECTION
# ─────────────────────────────────────────────

_NUMERIC_KW    = {"price", "rate", "cost", "gold", "silver", "dollar", "rupee",
                  "₹", "$", "usd", "inr", "exchange", "stock", "share", "score",
                  "temperature", "weather", "population", "count", "how many", "how much"}
_FACTUAL_KW    = {"who", "what is", "who is", "ceo", "founder", "president",
                  "capital", "born", "age", "when", "where", "define", "meaning"}
_COMPARISON_KW = {"vs", "versus", "compare", "difference", "better", "best",
                  "which", "pros", "cons", "advantages"}
_NEWS_KW       = {"latest", "news", "today", "recent", "now", "update",
                  "breaking", "just", "announced", "happened"}


def detect_query_type(query: str) -> str:
    q = query.lower()
    if any(k in q for k in _NUMERIC_KW):
        return "numeric"
    if any(k in q for k in _COMPARISON_KW):
        return "comparison"
    if any(k in q for k in _NEWS_KW):
        return "news"
    if any(k in q for k in _FACTUAL_KW):
        return "factual"
    return "general"


# ─────────────────────────────────────────────
# RELEVANCE SCORER
# ─────────────────────────────────────────────

def score_result(text: str, query: str) -> float:
    """Score a result 0-1 based on keyword overlap with the query."""
    if not text:
        return 0.0
    keywords = [w.lower() for w in re.split(r'\W+', query) if len(w) > 3]
    if not keywords:
        return 0.5
    text_lower = text.lower()
    hits = sum(1 for kw in keywords if kw in text_lower)
    raw  = hits / len(keywords)
    # Bonus: result mentions numbers when query is numeric-type
    if detect_query_type(query) == "numeric" and re.search(r'\d[\d,\.]+', text):
        raw = min(1.0, raw + 0.2)
    return round(raw, 3)


def rank_results(results: list[SearchResult], query: str) -> list[SearchResult]:
    """Re-rank a list of SearchResult by relevance score (descending)."""
    for r in results:
        r.score = score_result(r.text, query)
    return sorted(results, key=lambda r: r.score, reverse=True)


# ─────────────────────────────────────────────
# NOISE CLEANER
# ─────────────────────────────────────────────

_NOISE_PHRASES = re.compile(
    r"(cookie policy|accept cookies|privacy policy|terms of (use|service)|"
    r"subscribe (now|today|to)|sign (up|in)|log in|register (now|free)|"
    r"download (our )?app|follow us on|share (this|on)|"
    r"advertisement|sponsored|affiliate|all rights reserved|"
    r"©\s*\d{4}|copyright \d{4})",
    re.IGNORECASE,
)

_SHORT_LINE_RE = re.compile(r'(?m)^.{0,25}$\n?')


def clean_result(text: str) -> str:
    """Remove boilerplate noise from extracted page text."""
    # Strip noise phrases (whole sentence containing them)
    sentences = re.split(r'(?<=[.!?])\s+|\n+', text)
    cleaned   = [
        s for s in sentences
        if len(s) >= 30 and not _NOISE_PHRASES.search(s)
    ]
    result = " ".join(cleaned)
    result = re.sub(r'\s{2,}', ' ', result)
    return result.strip()


# ─────────────────────────────────────────────
# FACT EXTRACTORS  (per query type)
# ─────────────────────────────────────────────

_PRICE_RE  = re.compile(r"(₹|Rs\.?|INR|USD|\$)\s?([\d,]{2,10}(?:\.\d{1,2})?)", re.I)
_NUM_RE    = re.compile(r"\b(\d[\d,\.]*)\b")
_ENTITY_RE = re.compile(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b')
_SCORE_RE  = re.compile(r'\b(\d{1,3})/(\d{1,2})\b')
_DATE_RE   = re.compile(
    r'\b(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}|'
    r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4})\b',
    re.I,
)


def extract_facts(text: str, query_type: str) -> dict:
    """Pull structured facts from text depending on query type."""
    facts: dict = {}

    if query_type == "numeric":
        prices = _PRICE_RE.findall(text)
        if prices:
            facts["prices"] = [f"{sym}{val}" for sym, val in prices[:5]]
        numbers = _NUM_RE.findall(text)
        if numbers:
            facts["numbers"] = list(dict.fromkeys(numbers))[:8]
        scores = _SCORE_RE.findall(text)
        if scores:
            facts["scores"] = [f"{r}/{w}" for r, w in scores[:3]]

    elif query_type in ("factual", "general"):
        entities = _ENTITY_RE.findall(text)
        if entities:
            facts["entities"] = list(dict.fromkeys(entities))[:6]
        dates = _DATE_RE.findall(text)
        if dates:
            facts["dates"] = list(dict.fromkeys(dates))[:4]

    elif query_type == "news":
        dates = _DATE_RE.findall(text)
        if dates:
            facts["dates"] = list(dict.fromkeys(dates))[:4]
        entities = _ENTITY_RE.findall(text)
        if entities:
            facts["entities"] = list(dict.fromkeys(entities))[:6]

    return facts


# ─────────────────────────────────────────────
# MULTI-SOURCE MERGER
# ─────────────────────────────────────────────

def _overlap(a: str, b: str) -> float:
    """Simple token-overlap ratio between two strings."""
    ta = set(re.split(r'\W+', a.lower()))
    tb = set(re.split(r'\W+', b.lower()))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(len(ta), len(tb))


def merge_sources(results: list[SearchResult], query: str) -> tuple[str, bool]:
    """
    Merge top results into one coherent answer.

    Returns:
        (merged_text, sources_agree)
        sources_agree = True  if top results are broadly consistent
        sources_agree = False if they contradict each other
    """
    if not results:
        return "", False

    top = results[:3]

    if len(top) == 1:
        return top[0].text, True

    # Check pairwise agreement between top-2 results
    agree = _overlap(top[0].text, top[1].text) > 0.15

    # Build merged text: combine unique sentences from top sources
    seen:     set[str] = set()
    combined: list[str] = []
    for r in top:
        sentences = re.split(r'(?<=[.!?])\s+', r.text)
        for s in sentences:
            key = s.lower().strip()
            if key not in seen and len(s) > 40:
                seen.add(key)
                combined.append(s)

    # Keep it under ~600 chars
    merged = " ".join(combined)
    if len(merged) > 600:
        merged = merged[:600].rsplit(' ', 1)[0] + "…"

    return merged, agree


# ─────────────────────────────────────────────
# CONFIDENCE SCORER
# ─────────────────────────────────────────────

def compute_confidence(
    answer: str,
    results: list[SearchResult],
    sources_agree: bool,
    query_type: str,
) -> float:
    """Return a 0-1 confidence score for the final answer."""
    if not answer or not results:
        return 0.0

    score = 0.0

    # Base: top result relevance score
    score += results[0].score * 0.4

    # Multi-source agreement bonus
    if sources_agree and len(results) >= 2:
        score += 0.3
    elif len(results) >= 2:
        score += 0.1

    # Numeric answers are more verifiable
    if query_type == "numeric" and re.search(r'\d', answer):
        score += 0.2

    # Penalise very short or clearly failure answers
    if len(answer) < 30 or "not found" in answer.lower():
        score -= 0.3

    return round(max(0.0, min(1.0, score)), 2)


# ─────────────────────────────────────────────
# ANSWER FORMATTER
# ─────────────────────────────────────────────

def format_answer_block(answer: str, query_type: str, facts: dict) -> str:
    """
    Post-format the raw answer text with any structured facts injected.
    Keeps the answer clean and concise.
    """
    lines = [answer.strip()]

    if query_type == "numeric":
        if facts.get("prices"):
            lines.append("\n💰 Key figures: " + ", ".join(facts["prices"][:3]))
        if facts.get("scores"):
            lines.append("🏏 Scores: " + ", ".join(facts["scores"]))

    elif query_type == "news" and facts.get("dates"):
        lines.append("\n📅 Dates mentioned: " + ", ".join(facts["dates"][:3]))

    return "\n".join(lines)


# ─────────────────────────────────────────────
# MAIN PIPELINE ENTRY POINT
# ─────────────────────────────────────────────

def process_results(
    query:   str,
    raw_results: list[dict],          # each: {"url": str, "text": str}
) -> Optional[ProcessedAnswer]:
    """
    Full pipeline:
      1. Detect query type
      2. Clean text
      3. Score & rank
      4. Extract facts
      5. Merge sources
      6. Compute confidence
      7. Format final answer

    Returns a ProcessedAnswer, or None if nothing usable was found.
    """
    if not raw_results:
        return None

    query_type = detect_query_type(query)

    # Build SearchResult objects with cleaned text
    results: list[SearchResult] = []
    for r in raw_results:
        cleaned = clean_result(r.get("text", ""))
        if len(cleaned) >= 40:
            results.append(SearchResult(url=r.get("url", ""), text=cleaned))

    if not results:
        return None

    # Rank
    results = rank_results(results, query)

    # Extract facts from top result
    facts = extract_facts(results[0].text, query_type)

    # Merge top sources
    merged_text, sources_agree = merge_sources(results, query)

    if not merged_text:
        return None

    # Confidence
    confidence = compute_confidence(merged_text, results, sources_agree, query_type)

    # Format
    final_answer = format_answer_block(merged_text, query_type, facts)

    return ProcessedAnswer(
        answer        = final_answer,
        source        = results[0].url,
        confidence    = confidence,
        query_type    = query_type,
        sources_agree = sources_agree,
    )


# ─────────────────────────────────────────────
# SMART SNIPPET (used as last-resort fallback)
# ─────────────────────────────────────────────

def extract_best_snippet(text: str, query: str, max_chars: int = 500) -> str:
    """Return the most query-relevant sentences from text."""
    keywords  = [w.lower() for w in re.split(r'\W+', query) if len(w) > 3]
    sentences = re.split(r'(?<=[.!?])\s+', text)
    scored    = []
    for i, sentence in enumerate(sentences):
        if len(sentence) < 30:
            continue
        s_lower = sentence.lower()
        score   = sum(1 for kw in keywords if kw in s_lower)
        scored.append((score, i, sentence))
    scored.sort(key=lambda x: -x[0])
    if not scored:
        return text[:max_chars]
    top_indices = sorted([s[1] for s in scored[:4]])
    snippet     = " ".join(sentences[i] for i in top_indices)
    return snippet[:max_chars]