"""
patch_intent_accessibility.py  —  Run this ONCE in your project folder.

    python patch_intent_accessibility.py

Adds accessibility / screen explanation / handwriting intents to intent.py
in-place, without touching the existing screen reader intents.
"""

import os
import shutil
import ast

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
INTENT_FILE = os.path.join(PROJECT_DIR, "intent.py")

# ── backup ────────────────────────────────────────────────────────────────────

shutil.copy(INTENT_FILE, INTENT_FILE + ".bak2")
print(f"Backup saved: {INTENT_FILE}.bak2")

# ── read ──────────────────────────────────────────────────────────────────────

with open(INTENT_FILE, encoding="utf-8") as f:
    content = f.read()

# ── guard — skip if already patched ──────────────────────────────────────────

if "explain_screen" in content:
    print("SKIP: accessibility intents already present in intent.py")
    exit(0)

# ── block to insert ───────────────────────────────────────────────────────────

ACCESSIBILITY_BLOCK = '''
    # ---------- SCREEN EXPLANATION ----------

    if any(phrase in text for phrase in [
        "explain screen",
        "explain my screen",
        "describe screen",
        "describe my screen",
        "what is on my screen",
        "what's on my screen",
        "whats on my screen",
        "what do you see on screen",
        "tell me what's on screen",
        "tell me what is on screen",
        "what app is open",
        "what application is open",
        "what window is open",
        "what am i looking at",
        "describe what you see",
        "explain what you see",
    ]):
        return "explain_screen"

    # ---------- HANDWRITING READER ----------

    if any(phrase in text for phrase in [
        "read handwriting",
        "read handwritten",
        "read this handwritten",
        "ocr handwriting",
        "scan handwriting",
        "read old book",
        "read scanned book",
        "read scan",
        "read image text",
        "extract handwriting",
        "correct ocr",
        "fix ocr",
    ]):
        return "read_handwriting"

    # ---------- KEYBOARD NAVIGATION ----------

    if any(phrase in text for phrase in [
        "what is focused",
        "what has focus",
        "what control is focused",
        "read focused element",
        "what element is focused",
        "whats focused",
        "read focus",
        "current focus",
    ]):
        return "nav_focus"

    if any(phrase in text for phrase in [
        "what window is this",
        "what window am i in",
        "read window title",
        "current window",
        "active window",
        "window title",
        "what program is this",
    ]):
        return "nav_title"

    if any(phrase in text for phrase in [
        "list windows",
        "list open windows",
        "what windows are open",
        "show all windows",
        "open windows",
        "what is open",
        "what programs are open",
        "what apps are running",
    ]):
        return "nav_windows"

    if any(phrase in text for phrase in [
        "read clipboard",
        "what is in clipboard",
        "clipboard contents",
        "what did i copy",
        "paste contents",
        "show clipboard",
    ]):
        return "nav_clipboard"

    if any(phrase in text for phrase in [
        "toggle auto announce",
        "auto announce",
        "enable auto read",
        "disable auto read",
        "start reading focus",
        "stop reading focus",
        "turn on screen reader",
        "turn off screen reader",
        "enable screen reader",
        "disable screen reader",
    ]):
        return "nav_auto"

    if any(phrase in text for phrase in [
        "next window",
        "switch window",
        "alt tab",
        "go to next window",
        "switch to next window",
    ]):
        return "nav_next_window"

    if any(phrase in text for phrase in [
        "previous window",
        "go back window",
        "previous app",
        "switch to previous window",
    ]):
        return "nav_prev_window"

'''

# ── find insertion point ──────────────────────────────────────────────────────

MARKER = "    # ---------- DEFAULT ----------"

if MARKER not in content:
    MARKER = '    return "chat"'

content = content.replace(MARKER, ACCESSIBILITY_BLOCK + MARKER)

# ── write ─────────────────────────────────────────────────────────────────────

with open(INTENT_FILE, "w", encoding="utf-8") as f:
    f.write(content)

# ── validate ──────────────────────────────────────────────────────────────────

try:
    ast.parse(content)
    print("Syntax: OK")
except SyntaxError as e:
    print(f"SYNTAX ERROR: {e}")
    shutil.copy(INTENT_FILE + ".bak2", INTENT_FILE)
    print("Backup restored. No changes made.")
    raise

print("✓ Accessibility intents added to intent.py")
print("\nDone. Restart your assistant.")
