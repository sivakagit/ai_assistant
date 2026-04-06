"""
tts.py  —  Text-to-speech for the assistant.

Uses pyttsx3 (offline, no internet needed).

Install:
    pip install pyttsx3

Public API
----------
speak(text)         — speak text aloud (blocking)
speak_async(text)   — speak in background thread (non-blocking)
stop()              — stop current speech
set_rate(rate)      — words per minute (default 175)
set_volume(vol)     — 0.0 to 1.0 (default 1.0)
is_speaking()       — True if currently speaking
"""

import threading
import re

_lock       = threading.Lock()
_speaking   = False
_tts_thread = None
_rate       = 175
_volume     = 1.0


def _clean_text(text: str) -> str:
    """Collapse newlines and extra whitespace for pyttsx3."""
    text = re.sub(r"[\r\n]+", "  ", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def _do_speak(text: str):
    """
    Creates a FRESH pyttsx3 engine each call — required for Windows SAPI5
    to speak full multi-sentence text without cutting off.
    """
    global _speaking

    if not text or not text.strip():
        return

    cleaned = _clean_text(text)
    if not cleaned:
        return

    with _lock:
        _speaking = True
        try:
            # pyttsx3 SAPI5 usually handles COM on its own
            # Main thread COM initialization from Qt should be sufficient
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty("rate",   _rate)
            engine.setProperty("volume", _volume)
            engine.say(cleaned)
            engine.runAndWait()
            engine.stop()
        except Exception as e:
            print(f"[tts] speak error: {e}")
        finally:
            _speaking = False


# ── public API ────────────────────────────────────────────────────────────────

def speak(text: str) -> None:
    """Speak text aloud. Blocks until done."""
    _do_speak(text)


def speak_async(text: str) -> None:
    """
    Speak text in a background thread so the UI stays responsive.
    If already speaking, the new request waits for the current one to finish.
    """
    global _tts_thread

    if not text or not text.strip():
        return

    # Capture reference to previous thread BEFORE creating the new one
    prev_thread = _tts_thread

    def _run():
        # Wait for the previous thread to finish (but never join self)
        if prev_thread is not None and prev_thread.is_alive():
            prev_thread.join()
        _do_speak(text)

    _tts_thread = threading.Thread(target=_run, daemon=True)
    _tts_thread.start()


def stop() -> None:
    """Stop any current speech."""
    global _speaking
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.stop()
    except Exception:
        pass
    _speaking = False


def set_rate(rate: int) -> None:
    """Set speaking rate in words per minute (default 175)."""
    global _rate
    _rate = rate


def set_volume(vol: float) -> None:
    """Set volume 0.0 to 1.0 (default 1.0)."""
    global _volume
    _volume = max(0.0, min(1.0, vol))


def is_speaking() -> bool:
    return _speaking