"""
patch_intent.py  —  Run this ONCE in your project folder.

    python patch_intent.py

Adds screen reader intents to intent.py in-place.
"""

import os
import shutil
import ast

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
INTENT_FILE = os.path.join(PROJECT_DIR, "intent.py")

# ── backup ────────────────────────────────────────────────────────────────────

shutil.copy(INTENT_FILE, INTENT_FILE + ".bak")
print(f"Backup saved: {INTENT_FILE}.bak")

# ── read ──────────────────────────────────────────────────────────────────────

with open(INTENT_FILE, encoding="utf-8") as f:
    content = f.read()

# ── check already patched ─────────────────────────────────────────────────────

if "read_screen" in content:
    print("SKIP: screen intents already present in intent.py")
    exit(0)

# ── build the block to insert ─────────────────────────────────────────────────

SCREEN_BLOCK = '''
    # ---------- SCREEN READER ----------

    if any(phrase in text for phrase in [
        "read my screen",
        "read the screen",
        "read screen",
        "what's on my screen",
        "what is on my screen",
        "whats on my screen",
        "what's on screen",
        "scan my screen",
        "scan the screen",
        "extract text from screen",
        "get text from screen",
        "read top left",
        "read top right",
        "read bottom left",
        "read bottom right",
        "read center",
        "read top half",
        "read bottom half",
        "read left half",
        "read right half",
    ]):
        return "read_screen"

    if any(phrase in text for phrase in [
        "take a screenshot",
        "take screenshot",
        "capture screen",
        "save screenshot",
        "screenshot",
    ]):
        return "screenshot"

    if any(phrase in text for phrase in [
        "what did my screen say",
        "last screen",
        "previous screen text",
        "show last screen",
    ]):
        return "last_screen"

'''

# ── find insertion point — just before # --- DEFAULT --- ──────────────────────

MARKER = "    # ---------- DEFAULT ----------"

if MARKER not in content:
    # fallback: insert before "return "chat""
    MARKER = '    return "chat"'
    SCREEN_BLOCK = SCREEN_BLOCK + "\n"

content = content.replace(MARKER, SCREEN_BLOCK + MARKER)

# ── write ─────────────────────────────────────────────────────────────────────

with open(INTENT_FILE, "w", encoding="utf-8") as f:
    f.write(content)

# ── validate ──────────────────────────────────────────────────────────────────

try:
    ast.parse(content)
    print("Syntax: OK")
except SyntaxError as e:
    print(f"SYNTAX ERROR: {e}")
    shutil.copy(INTENT_FILE + ".bak", INTENT_FILE)
    print("Backup restored. No changes made.")
    raise

print("✓ Screen reader intents added to intent.py")
print("\nDone. Restart your assistant.")
