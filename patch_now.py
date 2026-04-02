"""
patch_now.py  —  Run this ONCE in your project folder.

    python patch_now.py

It will patch modern_gui.py in-place and print what it changed.
You never need to copy files again.
"""

import os
import shutil

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
GUI_FILE    = os.path.join(PROJECT_DIR, "modern_gui.py")

# ── backup ────────────────────────────────────────────────────────────────────

shutil.copy(GUI_FILE, GUI_FILE + ".bak")
print(f"Backup saved: {GUI_FILE}.bak")

# ── read ──────────────────────────────────────────────────────────────────────

with open(GUI_FILE, encoding="utf-8") as f:
    content = f.read()

changed = []

# ── patch 1: add fix_registry import ─────────────────────────────────────────

if "import fix_registry" not in content:
    content = content.replace(
        "from tools_manager import registry",
        "from tools_manager import registry\nimport fix_registry  # noqa: patches registry split bug"
    )
    changed.append("Added: import fix_registry")
else:
    print("SKIP: fix_registry already imported")

# ── patch 2: add screen handlers in send_message ─────────────────────────────

MARKER = "        # --- Normal command / chat flow ---"

SCREEN_BLOCK = '''\
        if _intent == "read_screen":
            from screen_reader import read_screen as _rs
            result = _rs()
            self.append_assistant(result if result else "No text detected on screen.")
            return

        if _intent == "screenshot":
            from screen_reader import screenshot_to_file as _ss
            path = _ss()
            self.append_assistant(f"Screenshot saved:\\n{path}")
            return

        if _intent == "last_screen":
            from screen_reader import last_screen_text as _ls
            self.append_assistant(_ls())
            return

        # --- Normal command / chat flow ---'''

if '_intent == "read_screen"' not in content:
    if MARKER in content:
        content = content.replace(MARKER, SCREEN_BLOCK)
        changed.append("Added: screen reader handlers in send_message")
    else:
        print("ERROR: Could not find '# --- Normal command / chat flow ---' marker in modern_gui.py")
        print("      Open modern_gui.py and add these lines manually just before that comment:")
        print()
        print(SCREEN_BLOCK)
else:
    print("SKIP: screen handlers already present")

# ── write ─────────────────────────────────────────────────────────────────────

with open(GUI_FILE, "w", encoding="utf-8") as f:
    f.write(content)

# ── validate ──────────────────────────────────────────────────────────────────

import ast
try:
    ast.parse(content)
    print("Syntax: OK")
except SyntaxError as e:
    print(f"SYNTAX ERROR: {e}")
    print("Restoring backup...")
    shutil.copy(GUI_FILE + ".bak", GUI_FILE)
    print("Backup restored. No changes made.")
    raise

# ── report ────────────────────────────────────────────────────────────────────

if changed:
    print("\nPatches applied:")
    for c in changed:
        print(f"  ✓ {c}")
    print("\nDone. Restart your assistant.")
else:
    print("\nNothing to patch — already up to date.")
