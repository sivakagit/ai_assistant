"""
fix_registry.py  —  Patches the registry split bug at startup.

The bug:
    tools_manager.py line 40 creates a NEW local ToolRegistry(),
    overwriting the shared one. So modern_gui gets an empty registry
    and all tool lookups return None → falls through to LLM.

The fix:
    1. Copy all tools from tools_manager's local registry → shared registry.
    2. Monkey-patch tools_manager.registry to point at the shared one.
    3. Register screen reader tools onto the shared registry.

Usage — add ONE line near the top of modern_gui.py, before any registry use:
    import fix_registry  # noqa
"""

# ── Step 1: import both registries ───────────────────────────────────────────

import tools_manager          # this runs tools_manager and fills its local registry
import tool_registry          # this has the shared registry modern_gui imported

shared  = tool_registry.registry        # the one modern_gui uses
local   = tools_manager.registry       # the one with all tools registered on it

# ── Step 2: copy every tool from local → shared ───────────────────────────────

for name, func in local.tools.items():
    shared.register(name, func)

# ── Step 3: make tools_manager.registry point at shared going forward ─────────

tools_manager.registry = shared

# ── Step 4: register screen reader tools onto shared ─────────────────────────

try:
    from screen_reader import (
        read_screen,
        screenshot_to_file,
        last_screen_text
    )

    def read_screen_tool(text: str) -> str:
        text_lower = text.lower()
        REGIONS = {
            "top left":     (0,    0,    960, 540),
            "top right":    (960,  0,    960, 540),
            "bottom left":  (0,    540,  960, 540),
            "bottom right": (960,  540,  960, 540),
            "center":       (480,  270,  960, 540),
            "top half":     (0,    0,   1920, 540),
            "bottom half":  (0,    540, 1920, 540),
            "left half":    (0,    0,    960, 1080),
            "right half":   (960,  0,    960, 1080),
        }
        for label, region in REGIONS.items():
            if label in text_lower:
                result = read_screen(region=region)
                return f"[{label.title()} region]\n\n{result}"
        result = read_screen()
        return "No text detected on screen." if not result else f"[Full screen]\n\n{result}"

    def screenshot_tool(text: str) -> str:
        path = screenshot_to_file()
        if path.startswith(("Screenshot failed", "Pillow", "pytesseract")):
            return path
        return f"Screenshot saved to:\n{path}"

    def last_screen_tool(text: str) -> str:
        return last_screen_text()

    shared.register("read_screen", read_screen_tool)
    shared.register("screenshot",  screenshot_tool)
    shared.register("last_screen", last_screen_tool)

    print("[fix_registry] screen_reader tools registered OK")

except ImportError as e:
    print(f"[fix_registry] screen_reader not available: {e}")

# ── Done ──────────────────────────────────────────────────────────────────────

print(f"[fix_registry] shared registry now has {len(shared.tools)} tools:")
print(" ", list(shared.tools.keys()))
