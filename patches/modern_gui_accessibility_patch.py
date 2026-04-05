"""
modern_gui_accessibility_patch.py

This file shows the 3 small edits needed in modern_gui.py to wire up the
accessibility engine at startup.  Do NOT run this file — it is a reference
showing exactly what to add/change in modern_gui.py.

────────────────────────────────────────────────────────────────────
EDIT 1 — Add import near the top of modern_gui.py (after tts import)
────────────────────────────────────────────────────────────────────

    from services.tts_service import speak_async, stop
    from services.accessibility_service import init_engine          # ← ADD THIS LINE

────────────────────────────────────────────────────────────────────
EDIT 2 — Add screen reader intent handlers in AssistantUI.send_message()
          (already in your code at line ~2337 — ADD the new intents below
          the existing last_screen block, before the normal command flow)
────────────────────────────────────────────────────────────────────

    # ... your existing read_screen / screenshot / last_screen blocks ...

        if _intent == "explain_screen":
            self.append_assistant("Explaining screen, please wait...")

            def _do_explain():
                from tools.screen_tools import explain_screen as _es
                result = _es()
                display = result if result else "Could not explain screen."
                self._screen_result_signal.emit(display)

            Thread(target=_do_explain, daemon=True).start()
            return

        if _intent == "read_handwriting":
            # Extract file path from message using tools_manager handler
            from tools.tools_manager import read_handwriting_tool
            result = read_handwriting_tool(message)
            self.append_assistant(result)
            self._maybe_speak(result)
            return

        # nav_ intents are handled via the registry (tool_response path),
        # no special case needed here — they fall through to handle_command()

────────────────────────────────────────────────────────────────────
EDIT 3 — Start the accessibility engine in main() AFTER the window is shown
────────────────────────────────────────────────────────────────────

    def main():
        app = QApplication(sys.argv)
        setup_dialog = OllamaSetupDialog()
        setup_dialog.exec()

        if not setup_dialog._success:
            sys.exit(1)

        start_scheduler()
        ensure_model_installed()

        window = AssistantUI()
        window.show()

        # ── START ACCESSIBILITY ENGINE ─────────────────────────────────────
        from services.accessibility_service import init_engine
        from services.tts_service import speak_async, stop as stop_tts
        init_engine(speak_fn=speak_async, stop_fn=stop_tts)
        # ──────────────────────────────────────────────────────────────────

        sys.exit(app.exec())
"""

# This file is documentation only — nothing to execute.
print("This is a patch guide, not a script. Read the docstring.")
