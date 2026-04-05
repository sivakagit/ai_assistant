"""
search.py  —  Search across all conversation sessions.

search_conversations(query)  →  list of match dicts
Each match:
{
    "session_id":    "session_abc123",
    "session_title": "Python help",
    "updated":       "2025-01-01 09:05",
    "role":          "user" | "assistant",
    "snippet":       "...matched text with **bold** highlight...",
    "message_index": 3
}
"""

from services.conversation_service import list_sessions, get_session_data

MAX_SNIPPET = 120       # characters around the match to show
MAX_RESULTS = 50


def _make_snippet(content: str, query: str) -> str:
    """Return a short excerpt around the first occurrence of query."""
    lower   = content.lower()
    idx     = lower.find(query.lower())
    if idx == -1:
        return content[:MAX_SNIPPET] + ("…" if len(content) > MAX_SNIPPET else "")

    start   = max(0, idx - 40)
    end     = min(len(content), idx + len(query) + 80)
    excerpt = content[start:end]

    if start > 0:
        excerpt = "…" + excerpt
    if end < len(content):
        excerpt = excerpt + "…"

    return excerpt


def search_conversations(query: str) -> list[dict]:
    """
    Case-insensitive full-text search across every message in every session.
    Returns a list of match dicts, newest session first.
    """
    if not query or not query.strip():
        return []

    q       = query.strip().lower()
    results = []

    for session_meta in list_sessions():          # already sorted newest-first
        sid  = session_meta["id"]
        data = get_session_data(sid)
        msgs = data.get("messages", [])

        for i, msg in enumerate(msgs):
            content = msg.get("content", "")
            if q in content.lower():
                results.append({
                    "session_id":    sid,
                    "session_title": session_meta["title"],
                    "updated":       session_meta["updated"],
                    "role":          msg.get("role", ""),
                    "snippet":       _make_snippet(content, query.strip()),
                    "message_index": i
                })
                if len(results) >= MAX_RESULTS:
                    return results

    return results