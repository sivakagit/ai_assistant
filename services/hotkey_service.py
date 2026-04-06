"""
hotkey_service.py
─────────────────
Registers a system-wide global hotkey that toggles Nova AI's window.

Design:
  • Runs `keyboard.add_hotkey()` on a daemon thread so it never blocks Qt.
  • Communicates back to the Qt main thread via a Signal (thread-safe).
  • The hotkey string is stored in config under "global_hotkey".
  • Default: Ctrl+Shift+Space

Usage (from AssistantUI.__init__):
    from services.hotkey_service import HotkeyService
    self._hotkey_service = HotkeyService(self.toggle_window)
    self._hotkey_service.start()

To update the hotkey at runtime (e.g. from Settings save):
    self._hotkey_service.update("ctrl+alt+n")
"""

import threading
from PySide6.QtCore import QObject, Signal
from core.logger import get_logger
from core.config import get_setting, set_setting

logger = get_logger()

DEFAULT_HOTKEY = "ctrl+shift+space"


class _HotkeySignaller(QObject):
    """Lives on the main thread; receives signals from the listener thread."""
    triggered = Signal()


class HotkeyService:
    """
    Manages a global keyboard hotkey.

    Parameters
    ----------
    callback : callable
        Zero-argument function called on the Qt main thread when the hotkey fires.
    """

    def __init__(self, callback):
        self._callback   = callback
        self._signaller  = _HotkeySignaller()
        self._signaller.triggered.connect(self._callback)
        self._current_hotkey: str | None = None
        self._lock = threading.Lock()

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self):
        """Register the hotkey from config (or the default) and start listening."""
        hotkey = get_setting("global_hotkey") or DEFAULT_HOTKEY
        self._register(hotkey)

    def update(self, new_hotkey: str):
        """
        Swap to a different hotkey at runtime.
        Called when the user changes the setting and saves.
        """
        new_hotkey = new_hotkey.strip().lower() or DEFAULT_HOTKEY
        set_setting("global_hotkey", new_hotkey)
        self._register(new_hotkey)

    def stop(self):
        """Unregister the current hotkey (call on app exit)."""
        self._unregister()

    @property
    def current(self) -> str:
        return self._current_hotkey or DEFAULT_HOTKEY

    # ── Internal ──────────────────────────────────────────────────────────────

    def _register(self, hotkey: str):
        with self._lock:
            self._unregister()
            try:
                import keyboard  # imported lazily — avoids hard crash if missing
                keyboard.add_hotkey(hotkey, self._on_hotkey, suppress=False)
                self._current_hotkey = hotkey
                logger.info(f"[HotkeyService] Registered global hotkey: {hotkey}")
            except ImportError:
                logger.warning(
                    "[HotkeyService] 'keyboard' package not installed. "
                    "Run: pip install keyboard"
                )
            except Exception as e:
                logger.warning(f"[HotkeyService] Could not register '{hotkey}': {e}")

    def _unregister(self):
        if self._current_hotkey:
            try:
                import keyboard
                keyboard.remove_hotkey(self._current_hotkey)
                logger.info(f"[HotkeyService] Unregistered hotkey: {self._current_hotkey}")
            except Exception:
                pass
            self._current_hotkey = None

    def _on_hotkey(self):
        """Called by the keyboard library on its own thread — emit signal to Qt."""
        self._signaller.triggered.emit()