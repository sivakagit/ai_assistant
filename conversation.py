"""
conversation.py  —  Multi-session conversation persistence.

Session files are stored as:
    sessions/session_<uuid>.json

Each file has the shape:
{
    "id":       "session_<uuid>",
    "title":    "Chat 1",           # auto-set from first user message
    "created":  "2025-01-01 09:00",
    "updated":  "2025-01-01 09:05",
    "messages": [
        {"role": "user",      "content": "..."},
        {"role": "assistant", "content": "..."}
    ]
}

Active session id is tracked in config.json under "active_session".
"""

import json
import os
import uuid
from datetime import datetime

from settings import resource_path, get_setting, set_setting

MAX_MESSAGES = 20

# ── folder that holds all session files ──────────────────────────────────────

def _sessions_dir() -> str:
    path = resource_path("sessions")
    os.makedirs(path, exist_ok=True)
    return path


def _session_path(session_id: str) -> str:
    return os.path.join(_sessions_dir(), f"{session_id}.json")


# ── low-level read / write ────────────────────────────────────────────────────

def _read_session(session_id: str) -> dict:
    path = _session_path(session_id)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _write_session(data: dict) -> None:
    path = _session_path(data["id"])
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ── active session helpers ────────────────────────────────────────────────────

def get_active_session_id() -> str:
    """Return current session id, creating one if none exists."""
    sid = get_setting("active_session")
    if sid and os.path.exists(_session_path(sid)):
        return sid
    return new_session()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


# ── public API ────────────────────────────────────────────────────────────────

def new_session(title: str = "") -> str:
    """Create a brand-new session, set it as active, and return its id."""
    sid = "session_" + uuid.uuid4().hex[:12]
    data = {
        "id":       sid,
        "title":    title or "New Chat",
        "created":  _now(),
        "updated":  _now(),
        "messages": []
    }
    _write_session(data)
    set_setting("active_session", sid)
    return sid


def add_message(role: str, content: str) -> None:
    """Append a message to the active session."""
    sid  = get_active_session_id()
    data = _read_session(sid)

    if not data:
        data = {
            "id":       sid,
            "title":    "New Chat",
            "created":  _now(),
            "updated":  _now(),
            "messages": []
        }

    messages = data.get("messages", [])
    messages.append({"role": role, "content": content})

    # keep within limit
    if len(messages) > MAX_MESSAGES:
        messages = messages[-MAX_MESSAGES:]

    # auto-title from first user message
    if data.get("title") in ("", "New Chat") and role == "user":
        data["title"] = content[:48].strip()

    data["messages"] = messages
    data["updated"]  = _now()
    _write_session(data)


def get_history() -> list:
    """Return message list for the active session."""
    sid  = get_active_session_id()
    data = _read_session(sid)
    return data.get("messages", [])


def clear_history() -> str:
    """Clear messages in the active session (keeps the session itself)."""
    sid  = get_active_session_id()
    data = _read_session(sid)
    if data:
        data["messages"] = []
        data["updated"]  = _now()
        _write_session(data)
    return "Conversation cleared"


# ── session list & management ─────────────────────────────────────────────────

def list_sessions() -> list[dict]:
    """
    Return all sessions sorted newest-first.
    Each item: {"id", "title", "created", "updated", "message_count"}
    """
    folder = _sessions_dir()
    result = []
    for fname in os.listdir(folder):
        if not fname.endswith(".json"):
            continue
        sid  = fname[:-5]           # strip .json
        data = _read_session(sid)
        if not data:
            continue
        result.append({
            "id":            data.get("id", sid),
            "title":         data.get("title", "Untitled"),
            "created":       data.get("created", ""),
            "updated":       data.get("updated", ""),
            "message_count": len(data.get("messages", []))
        })
    result.sort(key=lambda x: x["updated"], reverse=True)
    return result


def switch_session(session_id: str) -> bool:
    """Switch the active session. Returns True on success."""
    if os.path.exists(_session_path(session_id)):
        set_setting("active_session", session_id)
        return True
    return False


def delete_session(session_id: str) -> str:
    """Delete a session file. If it was active, create a new session."""
    path = _session_path(session_id)
    if not os.path.exists(path):
        return "Session not found"
    os.remove(path)
    if get_setting("active_session") == session_id:
        new_session()
    return "Session deleted"


def rename_session(session_id: str, new_title: str) -> str:
    """Rename a session."""
    data = _read_session(session_id)
    if not data:
        return "Session not found"
    data["title"]   = new_title.strip() or "Untitled"
    data["updated"] = _now()
    _write_session(data)
    return "Session renamed"


def get_session_data(session_id: str) -> dict:
    """Return the full session dict."""
    return _read_session(session_id)