"""
export.py  —  Export conversation sessions to TXT, Markdown, or JSON.

export_session(session_id, fmt, dest_path)
    fmt: "txt" | "md" | "json"
    dest_path: full path to write (caller chooses location via file dialog)
    Returns: (True, dest_path) | (False, error_message)

export_all_sessions(fmt, dest_folder)
    Writes one file per session into dest_folder.
    Returns: (True, files_written_count) | (False, error_message)
"""

import json
import os

from conversation import get_session_data, list_sessions


# ── formatters ────────────────────────────────────────────────────────────────

def _to_txt(data: dict) -> str:
    lines = []
    lines.append(f"Session : {data.get('title', 'Untitled')}")
    lines.append(f"Created : {data.get('created', '')}")
    lines.append(f"Updated : {data.get('updated', '')}")
    lines.append("=" * 60)
    lines.append("")
    for msg in data.get("messages", []):
        role    = msg.get("role", "?").capitalize()
        content = msg.get("content", "")
        lines.append(f"{role}:")
        lines.append(content)
        lines.append("")
    return "\n".join(lines)


def _to_md(data: dict) -> str:
    lines = []
    title = data.get("title", "Untitled")
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"**Created:** {data.get('created', '')}  ")
    lines.append(f"**Updated:** {data.get('updated', '')}  ")
    lines.append("")
    lines.append("---")
    lines.append("")
    for msg in data.get("messages", []):
        role    = msg.get("role", "?")
        content = msg.get("content", "")
        if role == "user":
            lines.append(f"**You:** {content}")
        else:
            lines.append(f"**Assistant:** {content}")
        lines.append("")
    return "\n".join(lines)


def _to_json(data: dict) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)


_FORMATTERS = {
    "txt":  (_to_txt,  ".txt"),
    "md":   (_to_md,   ".md"),
    "json": (_to_json, ".json"),
}


# ── safe filename ──────────────────────────────────────────────────────────────

def _safe_name(title: str) -> str:
    keep = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 _-")
    cleaned = "".join(c if c in keep else "_" for c in title).strip()
    return cleaned[:60] or "session"


# ── public API ────────────────────────────────────────────────────────────────

def export_session(session_id: str, fmt: str, dest_path: str):
    """
    Export a single session to dest_path.
    Returns (True, dest_path) or (False, error_str).
    """
    if fmt not in _FORMATTERS:
        return False, f"Unknown format '{fmt}'. Use txt, md, or json."

    data = get_session_data(session_id)
    if not data:
        return False, "Session not found."

    formatter, _ = _FORMATTERS[fmt]

    try:
        content = formatter(data)
        os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
        with open(dest_path, "w", encoding="utf-8") as f:
            f.write(content)
        return True, dest_path
    except Exception as e:
        return False, str(e)


def export_all_sessions(fmt: str, dest_folder: str):
    """
    Export every session into dest_folder (one file each).
    Returns (True, count) or (False, error_str).
    """
    if fmt not in _FORMATTERS:
        return False, f"Unknown format '{fmt}'."

    formatter, ext = _FORMATTERS[fmt]
    os.makedirs(dest_folder, exist_ok=True)

    sessions = list_sessions()
    if not sessions:
        return False, "No sessions to export."

    count = 0
    for meta in sessions:
        sid  = meta["id"]
        data = get_session_data(sid)
        if not data:
            continue
        fname    = _safe_name(meta["title"]) + f"_{sid[-6:]}{ext}"
        fpath    = os.path.join(dest_folder, fname)
        content  = formatter(data)
        try:
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(content)
            count += 1
        except Exception:
            pass

    return (True, count) if count else (False, "No files written.")