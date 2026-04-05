"""
tools_manager_accessibility_addon.py

INSTRUCTIONS
────────────
Do NOT replace your existing tools_manager.py.
Copy everything below the dashed line into the BOTTOM of your
tools_manager.py, after the existing registry.register() calls.

This block adds:
  • explain_screen   – LLM explains what is on screen
  • read_handwriting – OCR + LLM correction for handwritten images
  • nav_focus        – read what UI element is focused (like NVDA Insert+Tab)
  • nav_title        – read active window title
  • nav_windows      – list all open windows
  • nav_clipboard    – read clipboard contents
  • nav_auto         – toggle auto focus announcement
  • nav_next_window  – switch to next window and announce it
  • nav_prev_window  – switch to previous window and announce it
"""

# ─────────────────────────────────────────────────────────────────────────────
# PASTE EVERYTHING BELOW THIS LINE INTO THE BOTTOM OF tools_manager.py
# ─────────────────────────────────────────────────────────────────────────────

from tools.screen_tools import (
    read_screen,
    screenshot_to_file,
    last_screen_text,
    read_handwriting,       # NEW
    explain_screen,         # NEW
)

from services.accessibility_service import get_engine   # NEW


# ---------- EXISTING SCREEN READER TOOLS (keep as-is) ----------

def read_screen_tool(text: str) -> str:
    text_lower = text.lower()
    REGIONS = {
        "top left":     (0,    0,    960, 540),
        "top right":    (960,  0,    960, 540),
        "bottom left":  (0,    540,  960, 540),
        "bottom right": (960,  540,  960, 540),
        "center":       (480,  270,  960, 540),
        "top half":     (0,    0,    1920, 540),
        "bottom half":  (0,    540,  1920, 540),
        "left half":    (0,    0,    960, 1080),
        "right half":   (960,  0,    960, 1080),
    }
    for label, region in REGIONS.items():
        if label in text_lower:
            return f"[{label.title()} region]\n\n{read_screen(region=region)}"
    result = read_screen()
    return "No text detected on screen." if not result else f"[Full screen]\n\n{result}"


def screenshot_tool(text: str) -> str:
    path = screenshot_to_file()
    if path.startswith(("Screenshot failed", "Pillow", "pytesseract")):
        return path
    return f"Screenshot saved to:\n{path}"


def last_screen_tool(text: str) -> str:
    return last_screen_text()


registry.register("read_screen", read_screen_tool)
registry.register("screenshot",  screenshot_tool)
registry.register("last_screen", last_screen_tool)


# ---------- NEW: EXPLAIN SCREEN TOOL ----------

def explain_screen_tool(text: str) -> str:
    """
    Uses LLM (vision model if available, OCR+LLM fallback) to describe
    what is currently on screen in natural language.
    The user can also ask a specific question, e.g. 'what app is open?'
    """
    text_lower = text.lower()

    # Extract optional question from the user's message
    question = ""
    for trigger in ["explain", "describe", "what is", "what's", "tell me about"]:
        if trigger in text_lower:
            after = text_lower.split(trigger, 1)[1].strip()
            # Remove filler words
            for filler in ["the screen", "my screen", "on screen", "screen"]:
                after = after.replace(filler, "").strip()
            if len(after) > 3:
                question = after
            break

    REGIONS = {
        "top left":     (0,    0,    960, 540),
        "top right":    (960,  0,    960, 540),
        "bottom left":  (0,    540,  960, 540),
        "bottom right": (960,  540,  960, 540),
        "center":       (480,  270,  960, 540),
        "top half":     (0,    0,    1920, 540),
        "bottom half":  (0,    540,  1920, 540),
        "left half":    (0,    0,    960, 1080),
        "right half":   (960,  0,    960, 1080),
    }

    region = None
    for label, r in REGIONS.items():
        if label in text_lower:
            region = r
            break

    result = explain_screen(region=region, question=question)
    return result if result else "Could not explain the screen."


registry.register("explain_screen", explain_screen_tool)


# ---------- NEW: READ HANDWRITING TOOL ----------

def read_handwriting_tool(text: str) -> str:
    """
    Read handwritten text from an image file using OCR + LLM correction.
    The user should provide a file path.  The tool also accepts
    an optional context hint for better LLM reconstruction.

    Example user commands:
      "read handwriting from C:/scans/letter.jpg"
      "read handwritten book C:/books/page1.png old english diary"
    """
    import re

    text_lower = text.lower()

    # Try to extract a file path from the message
    # Matches Windows paths like C:\path\file.png or C:/path/file.jpg
    path_match = re.search(
        r'[a-zA-Z]:[\\\/][^\s"\']+\.(png|jpg|jpeg|tiff|tif|bmp|webp)',
        text,
        re.IGNORECASE
    )

    if not path_match:
        return (
            "Please provide the full path to the image file.\n"
            "Example: read handwriting from C:\\scans\\page1.jpg"
        )

    image_path = path_match.group(0)

    # Optional context hint — everything after the path
    context_hint = text[path_match.end():].strip()
    # Remove common filler
    for filler in ["as", "context:", "hint:", "it is", "it's"]:
        context_hint = context_hint.replace(filler, "").strip()

    result = read_handwriting(image_path, context_hint=context_hint)
    return f"[Handwriting from: {image_path}]\n\n{result}"


registry.register("read_handwriting", read_handwriting_tool)


# ---------- NEW: KEYBOARD NAVIGATION TOOLS ----------

def nav_focus_tool(text: str) -> str:
    """Read what UI element currently has keyboard focus."""
    engine = get_engine()
    if engine is None:
        return "Accessibility engine not started."
    return engine.read_focus()


def nav_title_tool(text: str) -> str:
    """Read the active window title."""
    engine = get_engine()
    if engine is None:
        return "Accessibility engine not started."
    return engine.read_title()


def nav_windows_tool(text: str) -> str:
    """List all open windows."""
    engine = get_engine()
    if engine is None:
        return "Accessibility engine not started."
    return engine.list_windows()


def nav_clipboard_tool(text: str) -> str:
    """Read clipboard text."""
    engine = get_engine()
    if engine is None:
        return "Accessibility engine not started."
    return engine.read_clipboard_cmd()


def nav_auto_tool(text: str) -> str:
    """Toggle automatic focus announcement (reads element on Tab/arrow key)."""
    engine = get_engine()
    if engine is None:
        return "Accessibility engine not started."
    return engine.toggle_auto_announce()


def nav_explain_tool(text: str) -> str:
    """Explain screen through accessibility engine (also speaks result)."""
    engine = get_engine()
    if engine is None:
        return explain_screen_tool(text)  # fallback without TTS

    text_lower = text.lower()
    question = ""
    for trigger in ["explain", "describe", "what is", "what's"]:
        if trigger in text_lower:
            after = text_lower.split(trigger, 1)[1].strip()
            for filler in ["the screen", "my screen", "on screen", "screen"]:
                after = after.replace(filler, "").strip()
            if len(after) > 3:
                question = after
            break

    return engine.explain_screen_cmd(question=question)


def nav_next_window_tool(text: str) -> str:
    """Switch to the next open window (Alt+Tab) and announce it."""
    engine = get_engine()
    if engine is None:
        return "Accessibility engine not started."
    engine._dispatch("next_window")
    return "Switching to next window."


def nav_prev_window_tool(text: str) -> str:
    """Switch to the previous open window (Alt+Shift+Tab) and announce it."""
    engine = get_engine()
    if engine is None:
        return "Accessibility engine not started."
    engine._dispatch("prev_window")
    return "Switching to previous window."


registry.register("nav_focus",       nav_focus_tool)
registry.register("nav_title",       nav_title_tool)
registry.register("nav_windows",     nav_windows_tool)
registry.register("nav_clipboard",   nav_clipboard_tool)
registry.register("nav_auto",        nav_auto_tool)
registry.register("explain_screen",  nav_explain_tool)   # overrides basic one
registry.register("nav_next_window", nav_next_window_tool)
registry.register("nav_prev_window", nav_prev_window_tool)
