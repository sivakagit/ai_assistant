"""
accessibility.py  —  Keyboard navigation and screen reader engine.

Provides NVDA/JAWS-style navigation for users who cannot look at the screen:
  - Global hotkeys to announce focused element, window title, system status
  - Arrow-key navigation announcer (reads what gains focus as you Tab/arrow)
  - Real-time UI element announcer using Windows UI Automation (pywinauto)
  - Speak every new focused control automatically
  - Announce clipboard contents, window changes, dialog popups

Usage
-----
    from accessibility import AccessibilityEngine
    engine = AccessibilityEngine(speak_fn=your_tts_function)
    engine.start()   # starts background listener
    engine.stop()

Requirements (install once)
-----------
    pip install keyboard pywinauto pygetwindow

keyboard    – global hotkey registration (works even when app not focused)
pywinauto   – Windows UI Automation to read control labels/values
pygetwindow – lightweight window title detection
"""

import threading
import time
import ctypes
from typing import Callable, Optional

# ── optional deps with graceful fallback ─────────────────────────────────────

try:
    import keyboard as _keyboard
    _KEYBOARD_OK = True
except ImportError:
    _KEYBOARD_OK = False

try:
    import pygetwindow as gw
    _GW_OK = True
except ImportError:
    _GW_OK = False

try:
    from pywinauto import Desktop
    from pywinauto.controls.uia_controls import EditWrapper
    _WINAUTO_OK = True
except ImportError:
    _WINAUTO_OK = False


# ══════════════════════════════════════════════════════════════════════════════
#  FOCUSED ELEMENT READER  (Windows UI Automation)
# ══════════════════════════════════════════════════════════════════════════════

class FocusReader:
    """
    Uses Windows UI Automation via pywinauto to read what control has focus
    and describe it in natural language — like a screen reader.
    """

    def __init__(self):
        self._last_element_desc = ""

    def get_focused_element_description(self) -> str:
        """
        Return a natural-language description of the currently focused UI element.
        e.g. "Button: OK", "Edit field: Search, current text: hello"
        """
        if not _WINAUTO_OK:
            return self._fallback_focus_description()

        try:
            desktop = Desktop(backend="uia")
            focused = desktop.get_focus()
            if focused is None:
                return "No element focused"

            ctrl_type  = focused.element_info.control_type or "Control"
            name       = focused.element_info.name or ""
            class_name = focused.element_info.class_name or ""

            # Read current value for text fields
            value = ""
            try:
                value = focused.get_value()
            except Exception:
                pass

            # Build description
            parts = [ctrl_type]
            if name:
                parts.append(name)
            if value:
                parts.append(f"contains: {value}")

            desc = ", ".join(parts)
            return desc if desc.strip() else "Unknown control focused"

        except Exception:
            return self._fallback_focus_description()

    def _fallback_focus_description(self) -> str:
        """Windows API fallback when pywinauto is not available."""
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
            return f"Window: {buf.value}" if buf.value else "Unknown window"
        except Exception:
            return "Cannot determine focused element"

    def get_window_title(self) -> str:
        """Return the title of the currently active window."""
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
            return buf.value or "Unknown window"
        except Exception:
            return "Unknown window"

    def get_all_open_windows(self) -> str:
        """List all open windows (for 'what windows are open' command)."""
        if _GW_OK:
            try:
                windows = [w.title for w in gw.getAllWindows() if w.title.strip()]
                if windows:
                    return "Open windows: " + ", ".join(windows)
                return "No windows detected"
            except Exception:
                pass

        # Fallback via ctypes EnumWindows
        try:
            titles = []

            def enum_cb(hwnd, _):
                if ctypes.windll.user32.IsWindowVisible(hwnd):
                    length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buf = ctypes.create_unicode_buffer(length + 1)
                        ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
                        titles.append(buf.value)
                return True

            EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
            ctypes.windll.user32.EnumWindows(EnumWindowsProc(enum_cb), 0)
            titles = [t for t in titles if t.strip()]
            return "Open windows: " + ", ".join(titles) if titles else "No windows found"
        except Exception:
            return "Could not enumerate windows"

    def get_clipboard_text(self) -> str:
        """Return current clipboard text content."""
        try:
            import subprocess
            result = subprocess.run(
                ["powershell", "-command", "Get-Clipboard"],
                capture_output=True, text=True, timeout=3
            )
            text = result.stdout.strip()
            return f"Clipboard: {text}" if text else "Clipboard is empty"
        except Exception:
            return "Could not read clipboard"


# ══════════════════════════════════════════════════════════════════════════════
#  FOCUS CHANGE WATCHER
# ══════════════════════════════════════════════════════════════════════════════

class FocusWatcher(threading.Thread):
    """
    Background thread that detects when the focused UI element changes
    and calls the speak function to announce the new element.

    This is the core of screen-reader navigation: whenever the user
    presses Tab, Shift+Tab, arrow keys, or clicks something, the new
    focused control is announced automatically.
    """

    POLL_INTERVAL = 0.25   # seconds between focus checks

    def __init__(self, speak_fn: Callable[[str], None]):
        super().__init__(daemon=True)
        self._speak    = speak_fn
        self._stop_evt = threading.Event()
        self._reader   = FocusReader()
        self._last_desc = ""
        self._last_window = ""
        self._enabled  = True

    def run(self):
        while not self._stop_evt.is_set():
            if self._enabled:
                try:
                    self._check_focus()
                    self._check_window()
                except Exception:
                    pass
            time.sleep(self.POLL_INTERVAL)

    def _check_focus(self):
        desc = self._reader.get_focused_element_description()
        if desc and desc != self._last_desc:
            self._last_desc = desc
            self._speak(desc)

    def _check_window(self):
        window = self._reader.get_window_title()
        if window and window != self._last_window:
            self._last_window = window
            self._speak(f"Window: {window}")

    def stop(self):
        self._stop_evt.set()

    def pause(self):
        self._enabled = False

    def resume(self):
        self._enabled = True


# ══════════════════════════════════════════════════════════════════════════════
#  GLOBAL HOTKEY MAP
# ══════════════════════════════════════════════════════════════════════════════

# Hotkeys follow NVDA/JAWS conventions where possible.
# NVDA insert key = Caps Lock key on most keyboards; here we use Right Alt
# to avoid conflicts with the assistant's own input.

HOTKEYS = {
    # Read current focus
    "right alt+tab":          "read_focus",
    # Read window title
    "right alt+t":            "read_title",
    # Read entire screen (OCR)
    "right alt+r":            "read_screen",
    # List all open windows
    "right alt+w":            "list_windows",
    # Read clipboard
    "right alt+c":            "read_clipboard",
    # Explain screen with LLM
    "right alt+e":            "explain_screen",
    # Stop speaking
    "right alt+s":            "stop_speaking",
    # Toggle auto-announce focus changes
    "right alt+a":            "toggle_auto_announce",
    # Read screen top half
    "right alt+up":           "read_top_half",
    # Read screen bottom half
    "right alt+down":         "read_bottom_half",
    # Navigate to next window (Alt+Tab simulation with announcement)
    "right alt+right":        "next_window",
    # Navigate to previous window
    "right alt+left":         "prev_window",
}


# ══════════════════════════════════════════════════════════════════════════════
#  ACCESSIBILITY ENGINE
# ══════════════════════════════════════════════════════════════════════════════

class AccessibilityEngine:
    """
    Main accessibility engine. Registers global hotkeys, manages the focus
    watcher thread, and dispatches navigation/reading commands.

    Parameters
    ----------
    speak_fn  : callable(text: str) — TTS function to speak text aloud
    stop_fn   : callable()          — function to stop current TTS speech
    """

    def __init__(
        self,
        speak_fn:  Callable[[str], None],
        stop_fn:   Optional[Callable[[], None]] = None,
    ):
        self._speak      = speak_fn
        self._stop_tts   = stop_fn or (lambda: None)
        self._reader     = FocusReader()
        self._watcher:   Optional[FocusWatcher] = None
        self._auto_announce = False    # off by default — user turns on
        self._running    = False

    # ── start / stop ──────────────────────────────────────────────────────────

    def start(self):
        """Start the accessibility engine (hotkeys + watcher thread)."""
        if self._running:
            return

        self._running = True

        # Start focus watcher thread (paused until user enables auto-announce)
        self._watcher = FocusWatcher(self._speak)
        self._watcher.pause()   # start paused
        self._watcher.start()

        # Register global hotkeys
        if _KEYBOARD_OK:
            self._register_hotkeys()
            self._speak(
                "Accessibility engine started. "
                "Press Right Alt plus E to explain screen, "
                "Right Alt plus R to read screen, "
                "Right Alt plus A to toggle auto focus announcement."
            )
        else:
            self._speak(
                "Accessibility started. Install the 'keyboard' package "
                "to enable global hotkeys: pip install keyboard"
            )

    def stop(self):
        """Stop the accessibility engine."""
        self._running = False

        if _KEYBOARD_OK:
            try:
                keyboard.unhook_all()
            except Exception:
                pass

        if self._watcher:
            self._watcher.stop()

    # ── hotkey registration ───────────────────────────────────────────────────

    def _register_hotkeys(self):
        import keyboard
        for hotkey, action in HOTKEYS.items():
            try:
                keyboard.add_hotkey(
                    hotkey,
                    self._dispatch,
                    args=(action,),
                    suppress=False
                )
            except Exception:
                pass   # some hotkeys may fail on certain keyboards

    # ── command dispatcher ────────────────────────────────────────────────────

    def _dispatch(self, action: str):
        """Run the action in a background thread so hotkeys don't block."""
        threading.Thread(
            target=self._run_action,
            args=(action,),
            daemon=True
        ).start()

    def _run_action(self, action: str):
        try:
            if action == "read_focus":
                desc = self._reader.get_focused_element_description()
                self._speak(desc)

            elif action == "read_title":
                title = self._reader.get_window_title()
                self._speak(f"Active window: {title}")

            elif action == "read_screen":
                self._speak("Reading screen, please wait.")
                from screen_reader import read_screen
                text = read_screen()
                self._speak(text or "No text detected on screen.")

            elif action == "list_windows":
                info = self._reader.get_all_open_windows()
                self._speak(info)

            elif action == "read_clipboard":
                info = self._reader.get_clipboard_text()
                self._speak(info)

            elif action == "explain_screen":
                self._speak("Explaining screen, please wait.")
                from screen_reader import explain_screen
                explanation = explain_screen()
                self._speak(explanation)

            elif action == "stop_speaking":
                self._stop_tts()

            elif action == "toggle_auto_announce":
                self._auto_announce = not self._auto_announce
                if self._auto_announce:
                    self._watcher.resume()
                    self._speak("Auto focus announcement enabled.")
                else:
                    self._watcher.pause()
                    self._speak("Auto focus announcement disabled.")

            elif action == "read_top_half":
                self._speak("Reading top half of screen.")
                from screen_reader import read_screen_region
                text = read_screen_region(0, 0, 1920, 540)
                self._speak(text or "No text detected.")

            elif action == "read_bottom_half":
                self._speak("Reading bottom half of screen.")
                from screen_reader import read_screen_region
                text = read_screen_region(0, 540, 1920, 540)
                self._speak(text or "No text detected.")

            elif action == "next_window":
                self._switch_window(forward=True)

            elif action == "prev_window":
                self._switch_window(forward=False)

        except Exception as e:
            self._speak(f"Accessibility error: {e}")

    # ── window navigation ─────────────────────────────────────────────────────

    def _switch_window(self, forward: bool = True):
        """Simulate Alt+Tab / Alt+Shift+Tab and announce the new window."""
        try:
            import keyboard
            if forward:
                keyboard.send("alt+tab")
            else:
                keyboard.send("alt+shift+tab")
            time.sleep(0.4)   # wait for window to activate
            title = self._reader.get_window_title()
            self._speak(f"Switched to: {title}")
        except Exception as e:
            self._speak(f"Window switch failed: {e}")

    # ── public command API (called from tools_manager) ────────────────────────

    def read_focus(self) -> str:
        desc = self._reader.get_focused_element_description()
        self._speak(desc)
        return desc

    def read_title(self) -> str:
        title = self._reader.get_window_title()
        result = f"Active window: {title}"
        self._speak(result)
        return result

    def list_windows(self) -> str:
        info = self._reader.get_all_open_windows()
        self._speak(info)
        return info

    def read_clipboard_cmd(self) -> str:
        info = self._reader.get_clipboard_text()
        self._speak(info)
        return info

    def explain_screen_cmd(self, question: str = "") -> str:
        from screen_reader import explain_screen
        self._speak("Explaining screen, please wait.")
        result = explain_screen(question=question)
        self._speak(result)
        return result

    def toggle_auto_announce(self) -> str:
        self._auto_announce = not self._auto_announce
        if self._auto_announce:
            self._watcher.resume()
            msg = "Auto focus announcement enabled. I will read each element as you navigate."
        else:
            self._watcher.pause()
            msg = "Auto focus announcement disabled."
        self._speak(msg)
        return msg

    def is_auto_announce_on(self) -> bool:
        return self._auto_announce


# ══════════════════════════════════════════════════════════════════════════════
#  MODULE-LEVEL SINGLETON — shared instance used by tools_manager
# ══════════════════════════════════════════════════════════════════════════════

_engine: Optional[AccessibilityEngine] = None


def get_engine() -> Optional[AccessibilityEngine]:
    return _engine


def init_engine(speak_fn: Callable, stop_fn: Optional[Callable] = None) -> AccessibilityEngine:
    """
    Create and start the global accessibility engine.
    Call once at application startup (e.g. in modern_gui.py main()).
    """
    global _engine
    _engine = AccessibilityEngine(speak_fn=speak_fn, stop_fn=stop_fn)
    _engine.start()
    return _engine
