# ─────────────────────────────────────────────────────────────────────────────
# PATCH FILE  —  apply these 3 changes to main_window.py
# ─────────────────────────────────────────────────────────────────────────────
#
# CHANGE 1 — Add imports at the top (after existing imports)
# ─────────────────────────────────────────────────────────────────────────────

from ui.command_palette import CommandPaletteMixin
from core.plugin_manager import plugin_manager

# ─────────────────────────────────────────────────────────────────────────────
# CHANGE 2 — Load plugins once at startup (add after start_scheduler() in main())
# ─────────────────────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)

    setup_dialog = OllamaSetupDialog()
    setup_dialog.exec()
    if not setup_dialog._success:
        sys.exit(1)

    start_scheduler()

    # ── Load plugins ──────────────────────────────────────────────────────────
    from tools.registry import registry as _registry
    plugin_manager._registry = _registry   # give plugins access to tool registry
    loaded = plugin_manager.load_all()
    if loaded:
        logger.info(f"[Startup] {loaded} plugin(s) loaded: "
                    + ", ".join(p.name for p in plugin_manager.list_plugins()))

    ensure_model_installed()

    window = AssistantUI()
    window.show()
    sys.exit(app.exec())

# ─────────────────────────────────────────────────────────────────────────────
# CHANGE 3 — Add CommandPaletteMixin to AssistantUI class definition
# ─────────────────────────────────────────────────────────────────────────────

# BEFORE:
#   class AssistantUI(QWidget):
#
# AFTER:
#   class AssistantUI(CommandPaletteMixin, QWidget):

# ─────────────────────────────────────────────────────────────────────────────
# CHANGE 4 — Init the palette at the END of __init__, after build_ui()
# ─────────────────────────────────────────────────────────────────────────────

# In AssistantUI.__init__, at the very bottom, add:
#
#   self._init_command_palette()   # Ctrl+Space palette
#
# So it looks like:
#
#   def __init__(self):
#       super().__init__()
#       self.setWindowTitle("Assistant")
#       self.resize(1150, 720)
#       self._tts_enabled = True
#       self._is_streaming = False
#       self._typing_cursor_pos = 0
#       self._stream_buffer = ""
#       self.apply_styles()
#       self.build_ui()
#       self.init_tray()
#       self._screen_result_signal.connect(self._on_screen_result)
#       self._tool_result_signal.connect(self._on_tool_result)
#       self._init_command_palette()   # ← ADD THIS LINE

# ─────────────────────────────────────────────────────────────────────────────
# CHANGE 5 — Route plugin intents in send_message()
# ─────────────────────────────────────────────────────────────────────────────

# In send_message(), BEFORE the final "Normal command / chat flow" block,
# add this plugin dispatch block:
#
#   # ── Plugin dispatch ───────────────────────────────────────────────────────
#   if plugin_manager.can_handle(_intent):
#       self.append_assistant("⚡ Running plugin…")
#       def _do_plugin(i=_intent, t=message):
#           result = plugin_manager.dispatch(i, t)
#           self._tool_result_signal.emit(result or "⚠️ Plugin returned no response.")
#       Thread(target=_do_plugin, daemon=True).start()
#       return
