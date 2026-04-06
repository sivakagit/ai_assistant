import sys
import os
import time
import re
from threading import Thread
from models.ollama_setup import ensure_ollama_ready
from services.health_monitor import get_health_snapshot
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QLineEdit,
    QPushButton,
    QListWidget,
    QLabel,
    QMessageBox,
    QInputDialog,
    QCheckBox,
    QComboBox,
    QListWidgetItem,
    QSystemTrayIcon,
    QDialog,
    QProgressBar,
    QFrame,
    QFileDialog,
    QSplitter,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
)

from PySide6.QtCore import (
    QTimer,
    Signal,
    QObject,
    Qt
)

import ollama

from tools.tools_manager import registry
from services.tts_service import speak_async, stop

from ui.confirmation_dialog import confirm_action

from tools.system_tools import (
    close_app,
    shutdown_pc,
    restart_pc,
    kill_process
)
from core.intent_engine import detect_intent

from services.scheduler_service import (
    start_scheduler,
    list_tasks
)

from services.memory_service import load_memory, maybe_store_memory
from services.conversation_service import (
    add_message,
    get_history,
    new_session,
    list_sessions,
    switch_session,
    delete_session,
    rename_session,
    get_active_session_id,
    get_session_data,
)

from tools.conversation_search_tools import search_conversations
from tools.export_tools import export_session, export_all_sessions

from core.config import (
    load_config,
    save_config,
    get_setting
)

from ui.tray import TrayManager

from core.startup import (
    enable_auto_start,
    disable_auto_start,
    is_auto_start_enabled
)

from models.downloader import (
    is_model_installed,
    detect_hardware,
    DownloadController
)
from core.logger import get_logger
from ui.command_palette import CommandPaletteMixin
from core.plugin_manager import plugin_manager

logger = get_logger()
# Ensure the project root (E:\Assistant) is on the path so that
# modules like ollama_setup can be found when this file is imported
# from a sub-package (ui/).
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


print("Loaded UI file:", __file__)
# ---------- SYSTEM ACTION REGISTRATIONS ----------

registry.register("close_app", close_app)

registry.register("shutdown_pc", shutdown_pc)

registry.register("restart_pc", restart_pc)

registry.register("kill_process", kill_process)


# ---------- STREAM SIGNALS ----------

class StreamSignals(QObject):

    token = Signal(str)

    finished = Signal()


# ---------- SMART MEMORY RETRIEVAL (Step 5) ----------

def retrieve_relevant_memory(user_input: str) -> dict:
    """
    Return only memory entries relevant to the user's message,
    instead of dumping everything into every prompt.
    """
    memory_data = load_memory()
    if not memory_data:
        return {}

    user_lower = user_input.lower()
    relevant   = {}

    # Flatten nested profile dict
    flat = {}
    for key, value in memory_data.items():
        if isinstance(value, dict):
            for subkey, subvalue in value.items():
                flat[subkey] = subvalue
        else:
            flat[key] = value

    # Always include name and role — they're almost always relevant
    for always_key in ("name", "role", "location"):
        if always_key in flat:
            relevant[always_key] = flat[always_key]

    # Include other keys only if they appear in the user's message
    for key, value in flat.items():
        if key in relevant:
            continue
        if key.lower() in user_lower or str(value).lower() in user_lower:
            relevant[key] = value

    return relevant


# ---------- MEMORY PROMPT ----------

def build_memory_prompt(user_input):
    """Returns the plain user message unchanged.
    Memory is injected only into the system prompt by build_system_prompt().
    """
    return user_input


# ---------- SYSTEM PROMPT (Steps 1 + 4 + 5) ----------

def build_system_prompt(user_input: str = "") -> str:
    """
    Builds a structured system prompt with:
    - Clear behavior rules  (Step 1)
    - Available tools list  (Step 4)
    - Relevant memory only  (Step 5)
    """

    # ── Step 1: Structured base prompt ───────────────────────────────────────
    base = """\
You are Nova, a smart desktop AI assistant running on the user's PC.

Behavior rules:
1. Be concise and direct — avoid unnecessary filler words
2. Use tools when they are available instead of guessing
3. Ask for clarification only if truly needed
4. Never hallucinate facts, files, or system state
5. Prefer actionable, specific answers over vague ones
6. Use memory context when it is relevant to the question
7. Format output clearly — use bullet points for lists, short paragraphs for explanations

Response style:
- Keep replies short unless detail is explicitly requested
- Use plain language, not technical jargon unless the user is technical
- Never repeat the user's question back to them
- If a tool handled the request, confirm the result briefly\
"""

    sections = [base]

    # ── Step 4: Tool list awareness ──────────────────────────────────────────
    try:
        tool_names = registry.list_tools()
        if tool_names:
            tool_lines = "\n".join(f"  - {t}" for t in sorted(tool_names))
            sections.append(
                f"Available tools (already handled automatically — do not suggest these manually):\n"
                f"{tool_lines}"
            )
    except Exception:
        pass

    # ── Step 5: Relevant memory only ─────────────────────────────────────────
    relevant = retrieve_relevant_memory(user_input)
    if relevant:
        mem_lines = "\n".join(f"  {k}: {v}" for k, v in relevant.items())
        sections.append(
            f"Known facts about the user (use only when directly relevant — do not repeat unprompted):\n"
            f"{mem_lines}"
        )

    return "\n\n".join(sections)


# ---------- COMMAND ROUTER ----------

def handle_command(user_input):

    add_message("user", user_input)

    maybe_store_memory(user_input)

    intent = detect_intent(
        user_input.lower()
    )

    tool = registry.get(intent)

    if tool:

        return tool(user_input)

    return None


# ---------- STREAM WORKER ----------

class StreamWorker:

    def __init__(self, prompt):

        self.prompt = prompt

        self.signals = StreamSignals()

    def run(self):

        try:

            memory_prompt = build_memory_prompt(
                self.prompt
            )

            history = get_history()

            # Step 3: RAG — retrieve relevant past conversation snippets
            rag_context = ""
            try:
                from tools.conversation_search_tools import search_conversations
                results = search_conversations(self.prompt)
                if results:
                    snippets = []
                    for r in results[:3]:  # top 3 matches
                        snippet = r.get("snippet", "").strip()
                        if snippet and snippet not in self.prompt:
                            snippets.append(f"- {snippet}")
                    if snippets:
                        rag_context = "Relevant past context:\n" + "\n".join(snippets)
            except Exception:
                pass

            sys_messages = [
                {
                    "role": "system",
                    "content": build_system_prompt(self.prompt)
                }
            ]

            # Inject RAG context as a separate system message if found
            if rag_context:
                sys_messages.append({
                    "role": "system",
                    "content": rag_context
                })

            messages = sys_messages + history + [
                {
                    "role": "user",
                    "content": memory_prompt
                }
            ]

            # Step 2: Tuned generation parameters for a factual desktop assistant
            stream = ollama.chat(
                model=get_setting("model"),
                messages=messages,
                stream=True,
                options={
                    "temperature":    0.4,   # focused, factual responses
                    "top_p":          0.9,   # nucleus sampling
                    "num_predict":    512,   # max tokens per response
                    "repeat_penalty": 1.1,   # reduce repetition
                    "stop": ["User:", "Assistant:", "<|user|>", "<|assistant|>"]
                }
            )

            full_text = ""

            for chunk in stream:

                token = chunk["message"]["content"]

                full_text += token

                self.signals.token.emit(token)

            add_message("assistant", full_text)

            self.signals.finished.emit()

        except Exception as e:

            self.signals.token.emit(f"\nError: {e}\n")

            self.signals.finished.emit()


# ---------- OLLAMA SETUP DIALOG ----------

class OllamaSetupDialog(QDialog):

    _setup_done = Signal(bool)

    def __init__(self):

        super().__init__()

        self.setWindowTitle("Starting Assistant")

        self.setFixedSize(420, 180)

        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowCloseButtonHint
        )

        self._success = False

        self._setup_done.connect(self._on_done)

        self.setStyleSheet("""
        QDialog {
            background-color: #1e1e1e;
        }
        QWidget {
            background-color: #1e1e1e;
            color: #ffffff;
            font-family: Segoe UI;
            font-size: 13px;
        }
        QProgressBar {
            background-color: #2d2d30;
            border: none;
            border-radius: 3px;
            height: 6px;
        }
        QProgressBar::chunk {
            background-color: #378ADD;
            border-radius: 3px;
        }
        QPushButton {
            background-color: #c42b1c;
            color: #ffffff;
            border: none;
            border-radius: 6px;
            padding: 8px 20px;
            font-size: 13px;
        }
        QPushButton:hover {
            background-color: #e03a28;
        }
        """)

        outer = QVBoxLayout(self)

        outer.setContentsMargins(28, 24, 28, 24)

        outer.setSpacing(14)

        title = QLabel("Preparing AI engine...")

        title.setStyleSheet(
            "font-size: 15px; font-weight: bold; color: #ffffff;"
        )

        outer.addWidget(title)

        self.status_label = QLabel("Starting Ollama service...")

        self.status_label.setStyleSheet("color: #aaaaaa; font-size: 12px;")

        outer.addWidget(self.status_label)

        self.progress_bar = QProgressBar()

        self.progress_bar.setRange(0, 0)

        self.progress_bar.setTextVisible(False)

        self.progress_bar.setFixedHeight(6)

        outer.addWidget(self.progress_bar)

        self.quit_btn = QPushButton("Cancel and Quit")

        self.quit_btn.clicked.connect(QApplication.quit)

        outer.addWidget(self.quit_btn)

        QTimer.singleShot(100, self.run_setup)

    def run_setup(self):

        try:

            model = get_setting("model")

        except Exception:

            model = "qwen2.5:3b"

        Thread(
            target=self._do_setup,
            args=(model,),
            daemon=True
        ).start()

    def _do_setup(self, model):

        try:

            ready = ensure_ollama_ready(model)

        except Exception:

            ready = False

        self._setup_done.emit(ready)

    def _on_done(self, ready):

        if ready:

            self._success = True

            self.accept()

        else:

            self.status_label.setText(
                "Failed to start Ollama. Is it installed?"
            )

            self.progress_bar.setRange(0, 100)

            self.progress_bar.setValue(0)

            self.quit_btn.setText("Quit")


# ---------- MODEL DOWNLOAD DIALOG ----------

class ModelDownloadDialog(QDialog):

    _progress_signal = Signal(int, float, float, str, str, str)
    _complete_signal = Signal()
    _error_signal = Signal(str)

    def __init__(self, preselect_model=None, lock_model=False):

        super().__init__()

        self.setWindowTitle("Download AI Model")

        self.setFixedSize(480, 340)

        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowCloseButtonHint
        )

        self._cancelled = False

        self._start_time = None

        self._preselect_model = preselect_model

        self._lock_model = lock_model

        self._controller = None

        self._progress_signal.connect(self._update_ui)
        self._complete_signal.connect(self._download_complete)
        self._error_signal.connect(self._on_error)

        self.model_sizes = {
            "qwen2.5:3b": 1.9,
            "phi3:mini":  2.3,
            "mistral:7b": 4.1,
            "llama3:8b":  4.7,
        }

        self.setStyleSheet("""
        QDialog {
            background-color: #1e1e1e;
        }
        QWidget {
            background-color: #1e1e1e;
            color: #ffffff;
            font-family: Segoe UI;
            font-size: 13px;
        }
        QComboBox {
            background-color: #2d2d30;
            color: #ffffff;
            border: 1px solid #3f3f3f;
            border-radius: 6px;
            padding: 8px 12px;
            font-size: 14px;
        }
        QComboBox::drop-down {
            border: none;
            width: 24px;
        }
        QComboBox QAbstractItemView {
            background-color: #2d2d30;
            color: #ffffff;
            selection-background-color: #0078d4;
        }
        QPushButton {
            background-color: #2d2d30;
            color: #ffffff;
            border: 1px solid #3f3f3f;
            border-radius: 8px;
            padding: 10px 20px;
            font-size: 13px;
        }
        QPushButton:hover {
            background-color: #3a3a3a;
        }
        QPushButton:disabled {
            color: #666666;
            background-color: #252525;
        }
        QProgressBar {
            background-color: #2d2d30;
            border: none;
            border-radius: 3px;
            height: 6px;
        }
        QProgressBar::chunk {
            background-color: #378ADD;
            border-radius: 3px;
        }
        QFrame#statsFrame {
            background-color: #252526;
            border-radius: 8px;
        }
        """)

        outer = QVBoxLayout(self)

        outer.setContentsMargins(24, 20, 24, 20)

        outer.setSpacing(16)

        title = QLabel("Download AI model")

        title.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #ffffff;"
        )

        outer.addWidget(title)

        subtitle = QLabel("Select a model to install on this device.")

        subtitle.setStyleSheet("color: #aaaaaa; font-size: 12px;")

        outer.addWidget(subtitle)

        model_label = QLabel("Model")

        model_label.setStyleSheet("color: #aaaaaa; font-size: 12px;")

        outer.addWidget(model_label)

        self.model_dropdown = QComboBox()

        self.model_dropdown.addItems([
            "qwen2.5:3b  \u2014  1.9 GB",
            "phi3:mini   \u2014  2.3 GB",
            "mistral:7b  \u2014  4.1 GB",
            "llama3:8b   \u2014  4.7 GB",
        ])

        if self._preselect_model:

            for i in range(self.model_dropdown.count()):

                if self._preselect_model in self.model_dropdown.itemText(i):

                    self.model_dropdown.setCurrentIndex(i)

                    break

        if self._lock_model:

            self.model_dropdown.setEnabled(False)

        outer.addWidget(self.model_dropdown)

        stats_frame = QFrame()

        stats_frame.setObjectName("statsFrame")

        stats_layout = QVBoxLayout(stats_frame)

        stats_layout.setContentsMargins(14, 12, 14, 12)

        stats_layout.setSpacing(10)

        status_row = QHBoxLayout()

        self.status_label = QLabel("Ready to download.")

        self.status_label.setStyleSheet("color: #cccccc; font-size: 13px;")

        self.pct_label = QLabel("")

        self.pct_label.setStyleSheet(
            "color: #ffffff; font-size: 13px; font-weight: bold;"
        )

        status_row.addWidget(self.status_label)

        status_row.addStretch()

        status_row.addWidget(self.pct_label)

        stats_layout.addLayout(status_row)

        self.progress_bar = QProgressBar()

        self.progress_bar.setRange(0, 100)

        self.progress_bar.setValue(0)

        self.progress_bar.setTextVisible(False)

        self.progress_bar.setFixedHeight(6)

        stats_layout.addWidget(self.progress_bar)

        cards_row = QHBoxLayout()

        cards_row.setSpacing(8)

        self.downloaded_label, d_card = self._make_card("Downloaded", "\u2014")

        self.speed_label, s_card = self._make_card("Speed", "\u2014")

        self.eta_label, e_card = self._make_card("ETA", "\u2014")

        cards_row.addWidget(d_card)

        cards_row.addWidget(s_card)

        cards_row.addWidget(e_card)

        stats_layout.addLayout(cards_row)

        outer.addWidget(stats_frame)

        btn_row = QHBoxLayout()

        btn_row.setSpacing(10)

        self.download_btn = QPushButton("Download")

        self.pause_btn = QPushButton("Pause")

        self.cancel_btn = QPushButton("Cancel")

        self.pause_btn.setEnabled(False)

        self.download_btn.clicked.connect(self.start_download)

        self.pause_btn.clicked.connect(self.toggle_pause)

        self.cancel_btn.clicked.connect(self.cancel_download)

        btn_row.addWidget(self.download_btn)

        btn_row.addWidget(self.pause_btn)

        btn_row.addWidget(self.cancel_btn)

        outer.addLayout(btn_row)

    def _make_card(self, title_text, value_text):

        card = QFrame()

        card.setStyleSheet("""
            QFrame {
                background-color: #1e1e1e;
                border-radius: 6px;
                border: 1px solid #3f3f3f;
            }
        """)

        layout = QVBoxLayout(card)

        layout.setContentsMargins(10, 8, 10, 8)

        layout.setSpacing(2)

        title = QLabel(title_text)

        title.setStyleSheet("color: #888888; font-size: 11px; border: none;")

        value = QLabel(value_text)

        value.setStyleSheet(
            "color: #ffffff; font-size: 15px; font-weight: bold; border: none;"
        )

        layout.addWidget(title)

        layout.addWidget(value)

        return value, card

    def get_model_name(self):

        return self.model_dropdown.currentText().split("\u2014")[0].strip()

    def start_download(self):

        self._start_time = time.time()

        self.download_btn.setEnabled(False)

        self.pause_btn.setEnabled(True)

        self.pause_btn.setText("Pause")

        self.model_dropdown.setEnabled(False)

        self.pct_label.setText("0%")

        model = self.get_model_name()

        self.status_label.setText(f"Downloading {model}...")

        self._controller = DownloadController()

        Thread(
            target=self.run_download,
            args=(model,),
            daemon=True
        ).start()

    def toggle_pause(self):

        if self._controller is None:
            return

        if self._controller.is_paused:

            self._controller.resume()

            self.pause_btn.setText("Pause")

            model = self.get_model_name()

            self.status_label.setText(f"Downloading {model}...")

        else:

            self._controller.pause()

            self.pause_btn.setText("Resume")

            self.status_label.setText("Paused — click Resume to continue")

    def run_download(self, model):

        def on_progress(percent, completed, total, speed_str, eta_str, status):

            if status == "done":

                self._complete_signal.emit()

                return

            if status in ("cancelled", "paused"):

                return

            if status.startswith("error:"):

                self._error_signal.emit(status[6:].strip())

                return

            if status == "retrying":

                self._progress_signal.emit(
                    self._controller.last_percent,
                    float(self._controller.last_completed),
                    float(self._controller.last_total),
                    "—",
                    "—",
                    "retrying"
                )

                return

            # Normal progress — emit all 6 args including live speed/eta
            if percent is not None:

                self._progress_signal.emit(
                    percent,
                    float(completed),
                    float(total),
                    speed_str,
                    eta_str,
                    "downloading"
                )

        self._controller.download(model, callback=on_progress)

    def _update_ui(self, pct, completed, total, speed_str, eta_str, status):

        self.progress_bar.setValue(pct)

        self.pct_label.setText(f"{pct}%")

        # FIX: only update downloaded label once real bytes are flowing
        if completed > 0:
            dl_gb = completed / (1024 * 1024 * 1024)
            self.downloaded_label.setText(f"{dl_gb:.2f} GB")

        if status == "retrying":

            self.status_label.setText(
                "Network lost — reconnecting automatically..."
            )

            self.speed_label.setText("—")

            self.eta_label.setText("—")

        else:

            if "reconnecting" in self.status_label.text().lower():

                model = self.get_model_name()

                self.status_label.setText(f"Downloading {model}...")

            self.speed_label.setText(speed_str)

            self.eta_label.setText(eta_str)

    def _on_error(self, message):

        self.status_label.setText(f"Error: {message}")

        self.download_btn.setEnabled(True)

        self.pause_btn.setEnabled(False)

        self.pause_btn.setText("Pause")

        if not self._lock_model:

            self.model_dropdown.setEnabled(True)

    def _download_complete(self):

        self.progress_bar.setValue(100)

        self.pct_label.setText("100%")

        self.status_label.setText("Download complete!")

        self.downloaded_label.setText("Done")

        self.speed_label.setText("\u2014")

        self.eta_label.setText("Done")

        self.pause_btn.setEnabled(False)

        self.pause_btn.setText("Pause")

        chosen = self.get_model_name()

        try:

            config = load_config()

            config["model"] = chosen

            save_config(config)

        except Exception as e:
            logger.exception("Failed to save config")

        QTimer.singleShot(1500, self.accept)

    def cancel_download(self):

        if self._controller is not None:

            self._controller.cancel()

            self._controller = None

        self.progress_bar.setValue(0)

        self.pct_label.setText("")

        self.status_label.setText("Cancelled.")

        self.downloaded_label.setText("\u2014")

        self.speed_label.setText("\u2014")

        self.eta_label.setText("\u2014")

        self.download_btn.setEnabled(True)

        self.pause_btn.setEnabled(False)

        self.pause_btn.setText("Pause")

        if not self._lock_model:

            self.model_dropdown.setEnabled(True)

    @staticmethod

    def _format_eta(seconds):

        m = int(seconds // 60)

        s = int(seconds % 60)

        return f"{m}:{s:02d}"


# ---------- SESSIONS DIALOG ----------

class SessionsDialog(QDialog):
    """Browse, switch, rename, delete, and export past sessions."""

    session_switched = Signal(str)   # emits session_id

    def __init__(self, parent=None):

        super().__init__(parent)

        self.setWindowTitle("Chat Sessions")

        self.setMinimumSize(620, 460)

        self.setStyleSheet("""
        QDialog, QWidget {
            background-color: #1e1e1e;
            color: #ffffff;
            font-family: Segoe UI;
            font-size: 13px;
        }
        QListWidget {
            background-color: #252526;
            border: 1px solid #3f3f3f;
            border-radius: 6px;
        }
        QListWidget::item { padding: 10px; border-bottom: 1px solid #2d2d30; }
        QListWidget::item:selected { background-color: #0078d4; }
        QPushButton {
            background-color: #0078d4;
            color: white;
            border: none;
            padding: 7px 16px;
            border-radius: 6px;
        }
        QPushButton:hover { background-color: #2893ff; }
        QPushButton#danger {
            background-color: #c42b1c;
        }
        QPushButton#danger:hover { background-color: #e03a28; }
        QPushButton#neutral {
            background-color: #2d2d30;
            border: 1px solid #3f3f3f;
        }
        QPushButton#neutral:hover { background-color: #3a3a3a; }
        QLineEdit {
            background-color: #2d2d30;
            color: #ffffff;
            border: 1px solid #3f3f3f;
            border-radius: 6px;
            padding: 7px 10px;
        }
        QLabel#meta { color: #888888; font-size: 11px; }
        """)

        self._build_ui()

        self.refresh_list()

    def _build_ui(self):

        outer = QVBoxLayout(self)

        outer.setContentsMargins(16, 16, 16, 16)

        outer.setSpacing(10)

        # ── title ──

        title = QLabel("Chat Sessions")

        title.setStyleSheet("font-size: 16px; font-weight: bold;")

        outer.addWidget(title)

        # ── session list ──

        self.list_widget = QListWidget()

        self.list_widget.itemDoubleClicked.connect(self._on_switch)

        outer.addWidget(self.list_widget)

        # ── meta label ──

        self.meta_label = QLabel("")

        self.meta_label.setObjectName("meta")

        outer.addWidget(self.meta_label)

        # ── button row ──

        btn_row = QHBoxLayout()

        btn_row.setSpacing(8)

        self.switch_btn = QPushButton("Open")

        self.switch_btn.clicked.connect(self._on_switch)

        self.rename_btn = QPushButton("Rename")

        self.rename_btn.setObjectName("neutral")

        self.rename_btn.clicked.connect(self._on_rename)

        self.delete_btn = QPushButton("Delete")

        self.delete_btn.setObjectName("danger")

        self.delete_btn.clicked.connect(self._on_delete)

        self.export_btn = QPushButton("Export…")

        self.export_btn.setObjectName("neutral")

        self.export_btn.clicked.connect(self._on_export)

        self.export_all_btn = QPushButton("Export All…")

        self.export_all_btn.setObjectName("neutral")

        self.export_all_btn.clicked.connect(self._on_export_all)

        close_btn = QPushButton("Close")

        close_btn.setObjectName("neutral")

        close_btn.clicked.connect(self.reject)

        btn_row.addWidget(self.switch_btn)

        btn_row.addWidget(self.rename_btn)

        btn_row.addWidget(self.delete_btn)

        btn_row.addStretch()

        btn_row.addWidget(self.export_btn)

        btn_row.addWidget(self.export_all_btn)

        btn_row.addWidget(close_btn)

        outer.addLayout(btn_row)

        self.list_widget.currentItemChanged.connect(self._update_meta)

    def refresh_list(self):

        self.list_widget.clear()

        active = get_active_session_id()

        self._sessions = list_sessions()

        for s in self._sessions:

            indicator = " ●" if s["id"] == active else ""

            label = f"{s['title']}{indicator}   [{s['message_count']} msgs · {s['updated']}]"

            item = QListWidgetItem(label)

            item.setData(Qt.UserRole, s["id"])

            self.list_widget.addItem(item)

        if self.list_widget.count():

            self.list_widget.setCurrentRow(0)

    def _current_id(self):

        item = self.list_widget.currentItem()

        return item.data(Qt.UserRole) if item else None

    def _update_meta(self, current, _previous):

        if not current:

            self.meta_label.setText("")

            return

        sid = current.data(Qt.UserRole)

        for s in self._sessions:

            if s["id"] == sid:

                self.meta_label.setText(

                    f"Created: {s['created']}   ·   Messages: {s['message_count']}"

                )

                break

    def _on_switch(self):

        sid = self._current_id()

        if not sid:

            return

        switch_session(sid)

        self.session_switched.emit(sid)

        self.accept()

    def _on_rename(self):

        sid = self._current_id()

        if not sid:

            return

        new_title, ok = QInputDialog.getText(

            self, "Rename Session", "New title:"

        )

        if ok and new_title.strip():

            rename_session(sid, new_title.strip())

            self.refresh_list()

    def _on_delete(self):

        sid = self._current_id()

        if not sid:

            return

        reply = QMessageBox.question(

            self,

            "Delete Session",

            "Delete this session? This cannot be undone.",

            QMessageBox.Yes | QMessageBox.No,

            QMessageBox.No

        )

        if reply == QMessageBox.Yes:

            msg = delete_session(sid)

            QMessageBox.information(self, "Deleted", msg)

            self.refresh_list()

    def _on_export(self):

        sid = self._current_id()

        if not sid:

            return

        fmt, ok = QInputDialog.getItem(

            self,

            "Export Format",

            "Select format:",

            ["txt", "md", "json"],

            0,

            False

        )

        if not ok:

            return

        dest, _ = QFileDialog.getSaveFileName(

            self,

            "Save session as",

            f"session.{fmt}",

            f"Files (*.{fmt})"

        )

        if not dest:

            return

        success, result = export_session(sid, fmt, dest)

        if success:

            QMessageBox.information(self, "Exported", f"Saved to:\n{result}")

        else:

            QMessageBox.warning(self, "Export Failed", result)

    def _on_export_all(self):

        fmt, ok = QInputDialog.getItem(

            self,

            "Export Format",

            "Select format:",

            ["txt", "md", "json"],

            0,

            False

        )

        if not ok:

            return

        folder = QFileDialog.getExistingDirectory(

            self,

            "Select destination folder"

        )

        if not folder:

            return

        success, result = export_all_sessions(fmt, folder)

        if success:

            QMessageBox.information(

                self,

                "Export Complete",

                f"Exported {result} session(s) to:\n{folder}"

            )

        else:

            QMessageBox.warning(self, "Export Failed", str(result))


# ---------- SEARCH DIALOG ----------

class SearchDialog(QDialog):
    """Search messages across all sessions."""

    session_switched = Signal(str)

    def __init__(self, parent=None):

        super().__init__(parent)

        self.setWindowTitle("Search Conversations")

        self.setMinimumSize(680, 480)

        self.setStyleSheet("""
        QDialog, QWidget {
            background-color: #1e1e1e;
            color: #ffffff;
            font-family: Segoe UI;
            font-size: 13px;
        }
        QLineEdit {
            background-color: #2d2d30;
            color: #ffffff;
            border: 1px solid #3f3f3f;
            border-radius: 6px;
            padding: 8px 12px;
        }
        QListWidget {
            background-color: #252526;
            border: 1px solid #3f3f3f;
            border-radius: 6px;
        }
        QListWidget::item { padding: 10px; border-bottom: 1px solid #2d2d30; }
        QListWidget::item:selected { background-color: #0078d4; }
        QPushButton {
            background-color: #0078d4;
            color: white;
            border: none;
            padding: 7px 16px;
            border-radius: 6px;
        }
        QPushButton:hover { background-color: #2893ff; }
        QPushButton#neutral {
            background-color: #2d2d30;
            border: 1px solid #3f3f3f;
        }
        QPushButton#neutral:hover { background-color: #3a3a3a; }
        QLabel#hint { color: #888888; font-size: 11px; }
        """)

        self._results = []

        self._build_ui()

    def _build_ui(self):

        outer = QVBoxLayout(self)

        outer.setContentsMargins(16, 16, 16, 16)

        outer.setSpacing(10)

        title = QLabel("Search Conversations")

        title.setStyleSheet("font-size: 16px; font-weight: bold;")

        outer.addWidget(title)

        # ── search bar ──

        search_row = QHBoxLayout()

        self.search_input = QLineEdit()

        self.search_input.setPlaceholderText("Type to search all messages…")

        self.search_input.returnPressed.connect(self._do_search)

        search_btn = QPushButton("Search")

        search_btn.clicked.connect(self._do_search)

        search_row.addWidget(self.search_input)

        search_row.addWidget(search_btn)

        outer.addLayout(search_row)

        # ── results count ──

        self.count_label = QLabel("")

        self.count_label.setObjectName("hint")

        outer.addWidget(self.count_label)

        # ── results list ──

        self.results_list = QListWidget()

        self.results_list.itemDoubleClicked.connect(self._open_session)

        outer.addWidget(self.results_list)

        # ── snippet preview ──

        self.preview = QTextEdit()

        self.preview.setReadOnly(True)

        self.preview.setFixedHeight(90)

        self.preview.setStyleSheet("""
            QTextEdit {
                background-color: #252526;
                color: #cccccc;
                border: 1px solid #3f3f3f;
                border-radius: 6px;
                padding: 8px;
                font-size: 12px;
            }
        """)

        outer.addWidget(self.preview)

        self.results_list.currentItemChanged.connect(self._show_preview)

        # ── buttons ──

        btn_row = QHBoxLayout()

        open_btn = QPushButton("Open Session")

        open_btn.clicked.connect(self._open_session)

        close_btn = QPushButton("Close")

        close_btn.setObjectName("neutral")

        close_btn.clicked.connect(self.reject)

        btn_row.addWidget(open_btn)

        btn_row.addStretch()

        btn_row.addWidget(close_btn)

        outer.addLayout(btn_row)

    def _do_search(self):

        query = self.search_input.text().strip()

        if not query:

            return

        self._results = search_conversations(query)

        self.results_list.clear()

        self.preview.clear()

        if not self._results:

            self.count_label.setText("No results found.")

            return

        self.count_label.setText(f"{len(self._results)} result(s) found.")

        for r in self._results:

            role_icon = "👤" if r["role"] == "user" else "🤖"

            label = f"{role_icon}  {r['session_title']}   [{r['updated']}]"

            item = QListWidgetItem(label)

            item.setData(Qt.UserRole, self._results.index(r))

            self.results_list.addItem(item)

        self.results_list.setCurrentRow(0)

    def _show_preview(self, current, _prev):

        if not current:

            self.preview.clear()

            return

        idx = current.data(Qt.UserRole)

        r   = self._results[idx]

        self.preview.setPlainText(r["snippet"])

    def _open_session(self):

        item = self.results_list.currentItem()

        if not item:

            return

        idx = item.data(Qt.UserRole)

        r   = self._results[idx]

        switch_session(r["session_id"])

        self.session_switched.emit(r["session_id"])

        self.accept()


# ---------- MAIN UI ----------

class AssistantUI(CommandPaletteMixin, QWidget):

    _screen_result_signal = Signal(str)
    _tool_result_signal   = Signal(str)   # for threaded tool responses

    def __init__(self):

        super().__init__()

        self.setWindowTitle("Assistant")

        self.resize(1150, 720)

        # TTS toggle state — False means muted, True means speaking enabled
        self._tts_enabled = True
        self._is_streaming = False
        self._typing_cursor_pos = 0
        self._stream_buffer = ""

        self.apply_styles()

        self.build_ui()

        self.init_tray()

        self._screen_result_signal.connect(self._on_screen_result)
        self._tool_result_signal.connect(self._on_tool_result)

        # ── Command palette (Ctrl+Space) ──────────────────────────────────────
        self._init_command_palette()

        # ── Load plugins from plugins/ directory ──────────────────────────────
        try:
            loaded = plugin_manager.load_all()
            if loaded:
                logger.info(f"[Startup] {loaded} plugin(s) loaded")
        except Exception as e:
            logger.warning(f"[Startup] Plugin load failed: {e}")

    def _on_screen_result(self, display: str):

        self.append_assistant(display)

        self._maybe_speak(display)

    def _on_tool_result(self, display: str):
        """Called on the UI thread after a background tool finishes."""
        self.append_assistant(display)
        self._maybe_speak(display)

    def _maybe_speak(self, text: str):
        if self._tts_enabled:
        # pyttsx3 on Windows stops at newlines — replace with a pause (space)
            clean = text.replace("\n", " ").replace("\r", " ").strip()
            speak_async(clean)
            
    def build_health_page(self):

        from PySide6.QtWidgets import QGridLayout

        container = QWidget()
        container.setStyleSheet("background-color: #0d1117;")

        outer_layout = QVBoxLayout(container)
        outer_layout.setContentsMargins(32, 28, 32, 24)
        outer_layout.setSpacing(20)

        # Title
        title = QLabel("System Health")
        title.setStyleSheet("font-size: 22px; font-weight: 700; color: #e6edf3; letter-spacing: -0.4px;")
        outer_layout.addWidget(title)

        subtitle = QLabel("Monitor your AI assistant's performance and status")
        subtitle.setStyleSheet("color: #484f58; font-size: 12px; margin-top: -12px;")
        outer_layout.addWidget(subtitle)

        # ── Stat card helper ─────────────────────────────────────────────────
        def _make_card(icon_char, card_title):
            card = QFrame()
            card.setStyleSheet("""
                QFrame {
                    background-color: #161b22;
                    border: 1px solid #21262d;
                    border-radius: 12px;
                }
            """)
            card.setMinimumHeight(116)
            cl = QVBoxLayout(card)
            cl.setContentsMargins(20, 16, 20, 16)
            cl.setSpacing(4)
            top = QHBoxLayout()
            lbl = QLabel(card_title)
            lbl.setStyleSheet("color: #8b949e; font-size: 12px; font-weight: 500; background: transparent;")
            icon_l = QLabel(icon_char)
            icon_l.setStyleSheet("color: #7c3aed; font-size: 18px; background: transparent;")
            top.addWidget(lbl)
            top.addStretch()
            top.addWidget(icon_l)
            cl.addLayout(top)
            val = QLabel("—")
            val.setStyleSheet("color: #e6edf3; font-size: 26px; font-weight: 700; background: transparent;")
            cl.addWidget(val)
            sub = QLabel("")
            sub.setStyleSheet("color: #484f58; font-size: 11px; background: transparent;")
            cl.addWidget(sub)
            return card, val, sub

        # Row 0
        grid = QGridLayout()
        grid.setSpacing(12)
        self._cpu_card,  self._cpu_val,  self._cpu_sub  = _make_card("⬛", "CPU Usage")
        self._mem_card,  self._mem_val,  self._mem_sub  = _make_card("🖴",  "Memory Usage")
        self._thr_card,  self._thr_val,  self._thr_sub  = _make_card("≡",  "Thread Count")
        self._upt_card,  self._upt_val,  self._upt_sub  = _make_card("⏱", "Uptime")
        self._oll_card,  self._oll_val,  self._oll_sub  = _make_card("🖥", "Ollama Status")
        self._sch_card,  self._sch_val,  self._sch_sub  = _make_card("📅", "Scheduler")
        grid.addWidget(self._cpu_card, 0, 0)
        grid.addWidget(self._mem_card, 0, 1)
        grid.addWidget(self._thr_card, 0, 2)
        grid.addWidget(self._upt_card, 1, 0)
        grid.addWidget(self._oll_card, 1, 1)
        grid.addWidget(self._sch_card, 1, 2)
        outer_layout.addLayout(grid)

        # ── Memory trend ─────────────────────────────────────────────────────
        chart_frame = QFrame()
        chart_frame.setStyleSheet("""
            QFrame { background-color: #161b22; border: 1px solid #21262d; border-radius: 12px; }
        """)
        chart_frame.setMinimumHeight(100)
        chart_v = QVBoxLayout(chart_frame)
        chart_v.setContentsMargins(20, 14, 20, 14)
        chart_v.setSpacing(8)
        chart_hdr = QLabel("Memory Usage (24h)")
        chart_hdr.setStyleSheet("color: #e6edf3; font-size: 13px; font-weight: 600; background: transparent;")
        chart_v.addWidget(chart_hdr)
        self.memory_chart_display = QLabel("Collecting data…")
        self.memory_chart_display.setStyleSheet("color: #484f58; font-size: 12px; background: transparent;")
        self.memory_chart_display.setAlignment(Qt.AlignCenter)
        chart_v.addWidget(self.memory_chart_display)
        outer_layout.addWidget(chart_frame)

        # ── Log viewer ───────────────────────────────────────────────────────
        log_lbl = QLabel("Recent Logs")
        log_lbl.setStyleSheet("font-size: 13px; font-weight: 600; color: #e6edf3;")
        outer_layout.addWidget(log_lbl)

        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setMaximumHeight(110)
        self.log_display.setStyleSheet("""
            QTextEdit {
                background-color: #0d1117;
                color: #3fb950;
                border: 1px solid #21262d;
                border-radius: 10px;
                padding: 12px 14px;
                font-size: 11px;
                font-family: "Consolas", monospace;
            }
        """)
        outer_layout.addWidget(self.log_display)

        self.start_health_timer()

        return container

    def start_health_timer(self):

        self.health_timer = QTimer()

        self.health_timer.timeout.connect(
        self.refresh_health
    )

        self.health_timer.start(3000)
        
    def refresh_health(self):

        data = get_health_snapshot()

        if not data:
            return

        # Update stat cards
        self._cpu_val.setText(f"{data['cpu']:.0f}%")
        self._cpu_sub.setText("processor load")

        self._mem_val.setText(f"{data['memory']:.0f}")
        self._mem_sub.setText("MB in use")

        self._thr_val.setText(str(data["threads"]))
        self._thr_sub.setText("active threads")

        self._upt_val.setText(data["uptime"])
        self._upt_sub.setText("since last start")

        ollama_running = data["ollama"] == "Running"
        self._oll_val.setText(data["ollama"])
        self._oll_val.setStyleSheet(
            f"color: {'#3fb950' if ollama_running else '#f85149'}; "
            f"font-size: 18px; font-weight: 700; background: transparent;"
        )
        self._oll_sub.setText(f"model: {data['model']}")

        sched_running = data["scheduler"]
        self._sch_val.setText("Running" if sched_running else "Stopped")
        self._sch_val.setStyleSheet(
            f"color: {'#3fb950' if sched_running else '#f85149'}; "
            f"font-size: 18px; font-weight: 700; background: transparent;"
        )
        self._sch_sub.setText(f"{data['errors']} error(s) logged")

        # Update memory trend bar
        trend = data.get("memory_trend", [])
        if trend:
            peak = max(trend) or 1
            bar_width = 28
            bars = ""
            step = max(1, len(trend) // bar_width)
            samples = trend[::step][-bar_width:]
            for v in samples:
                h = max(2, int((v / peak) * 16))
                bars += f'<span style="display:inline-block;width:6px;height:{h}px;background:#7c3aed;border-radius:2px;margin:1px;vertical-align:bottom;"></span>'
            self.memory_chart_display.setText(
                f'<span style="font-family:monospace;font-size:11px;">{bars}</span>'
                f'  <span style="color:#484f58;font-size:11px;">peak {peak:.0f} MB</span>'
            )
            self.memory_chart_display.setTextFormat(Qt.RichText)

        # Update logs
        try:
            from services.log_reader import read_recent_logs
            logs = read_recent_logs(50)
            self.log_display.setText(logs)
        except Exception:
            pass

    def _toggle_tts(self):
        """Toggle TTS on/off and update the button appearance."""
        self._tts_enabled = not self._tts_enabled
        if self._tts_enabled:
            self.tts_toggle_btn.setText("🔊  Voice On")
            self.tts_toggle_btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #a78bfa;
                    border: 1px solid #6d28d9;
                    padding: 5px 12px;
                    border-radius: 7px;
                    font-size: 11px;
                }
                QPushButton:hover { background-color: #1c1c2e; }
            """)
        else:
            stop()
            self.tts_toggle_btn.setText("🔇  Voice Off")
            self.tts_toggle_btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #8b949e;
                    border: 1px solid #30363d;
                    padding: 5px 12px;
                    border-radius: 7px;
                    font-size: 11px;
                }
                QPushButton:hover { background-color: #21262d; color: #e6edf3; }
            """)

    def init_tray(self):

        try:

            if not QSystemTrayIcon.isSystemTrayAvailable():

                print("System tray not available")

                return

            self.tray = TrayManager(self)

            logger.info("Tray initialized")


        except Exception as e:

            logger.exception("Tray initialization failed:", e)

    def apply_styles(self):

        self.setStyleSheet("""
        QWidget {
            background-color: #0d1117;
            color: #c9d1d9;
            font-family: "Segoe UI", sans-serif;
            font-size: 13px;
        }
        QScrollBar:vertical {
            background: transparent;
            width: 0px;
            margin: 0;
        }
        QScrollBar::handle:vertical { background: transparent; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        QScrollBar:horizontal { background: transparent; height: 0px; }
        QScrollBar::handle:horizontal { background: transparent; }
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
        QListWidget {
            background-color: #161b22;
            border: none;
            border-right: 1px solid #21262d;
            outline: none;
        }
        QListWidget::item {
            padding: 10px 14px;
            border-radius: 8px;
            margin: 2px 8px;
            color: #8b949e;
            font-size: 13px;
        }
        QListWidget::item:selected {
            background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #6e40c9,stop:1 #8b5cf6);
            color: #ffffff;
            font-weight: 600;
        }
        QListWidget::item:hover:!selected {
            background-color: #21262d;
            color: #e6edf3;
        }
        QPushButton {
            background-color: #7c3aed;
            color: #ffffff;
            border: none;
            padding: 7px 16px;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 500;
        }
        QPushButton:hover { background-color: #8b5cf6; }
        QPushButton:pressed { background-color: #6d28d9; }
        QLineEdit {
            background-color: #161b22;
            color: #c9d1d9;
            border: 1px solid #30363d;
            border-radius: 8px;
            padding: 9px 14px;
            font-size: 13px;
        }
        QLineEdit:focus {
            border-color: #7c3aed;
            background-color: #1c2128;
        }
        QTextEdit {
            background-color: #161b22;
            color: #c9d1d9;
            border: 1px solid #30363d;
            border-radius: 8px;
            padding: 10px;
        }
        QComboBox {
            background-color: #161b22;
            color: #c9d1d9;
            border: 1px solid #30363d;
            border-radius: 8px;
            padding: 7px 12px;
        }
        QComboBox:hover { border-color: #7c3aed; }
        QComboBox::drop-down { border: none; width: 24px; }
        QComboBox QAbstractItemView {
            background-color: #161b22;
            border: 1px solid #30363d;
            selection-background-color: #7c3aed;
            selection-color: #ffffff;
            outline: none;
        }
        QCheckBox { color: #8b949e; spacing: 8px; }
        QCheckBox::indicator {
            width: 16px; height: 16px;
            border: 1px solid #30363d;
            border-radius: 4px;
            background: #161b22;
        }
        QCheckBox::indicator:checked {
            background-color: #7c3aed;
            border-color: #7c3aed;
        }
        QProgressBar {
            background-color: #21262d;
            border: none;
            border-radius: 4px;
            height: 6px;
        }
        QProgressBar::chunk { background-color: #7c3aed; border-radius: 4px; }
        QLabel { color: #c9d1d9; background: transparent; }
        """)

    def closeEvent(self, event):

        try:

            minimize = get_setting(
                "window_minimize_to_tray"
            )

        except Exception:

            minimize = True

        if minimize:

            event.ignore()

            self.hide()

            self.status_bar.setText(
                "Running in system tray"
            )

        else:

            event.accept()

            from core.shutdown_manager import shutdown

            shutdown()

    def build_ui(self):

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Top header bar ──────────────────────────────────────────────────
        header_bar = QFrame()
        header_bar.setFixedHeight(56)
        header_bar.setStyleSheet("""
            QFrame {
                background-color: #0d1117;
                border-bottom: 1px solid #21262d;
            }
        """)
        header_layout = QHBoxLayout(header_bar)
        header_layout.setContentsMargins(16, 0, 16, 0)
        header_layout.setSpacing(0)

        # Logo block
        logo_frame = QFrame()
        logo_frame.setStyleSheet("background: transparent; border: none;")
        logo_h = QHBoxLayout(logo_frame)
        logo_h.setContentsMargins(0, 0, 16, 0)
        logo_h.setSpacing(8)
        app_icon = QLabel("⚡")
        app_icon.setStyleSheet("font-size: 18px; color: #f97316; background: transparent;")
        app_name = QLabel("Nova AI")
        app_name.setStyleSheet("font-size: 15px; font-weight: 700; color: #e6edf3; background: transparent; letter-spacing: -0.2px;")
        logo_h.addWidget(app_icon)
        logo_h.addWidget(app_name)

        # Divider
        div_line = QFrame()
        div_line.setFrameShape(QFrame.VLine)
        div_line.setFixedWidth(1)
        div_line.setFixedHeight(28)
        div_line.setStyleSheet("background: #30363d; border: none;")

        # Model + Ollama status
        status_frame = QFrame()
        status_frame.setStyleSheet("background: transparent; border: none;")
        status_h = QHBoxLayout(status_frame)
        status_h.setContentsMargins(16, 0, 0, 0)
        status_h.setSpacing(6)
        model_dot = QLabel("●")
        model_dot.setStyleSheet("color: #a78bfa; font-size: 8px; background: transparent;")
        try:
            _model_name = get_setting("model") or "llama2:latest"
        except Exception:
            _model_name = "llama2:latest"
        model_lbl = QLabel(_model_name)
        model_lbl.setStyleSheet("color: #8b949e; font-size: 12px; background: transparent;")
        ollama_dot = QLabel("●")
        ollama_dot.setStyleSheet("color: #3fb950; font-size: 8px; background: transparent; margin-left: 14px;")
        ollama_lbl = QLabel("Ollama Connected")
        ollama_lbl.setStyleSheet("color: #8b949e; font-size: 12px; background: transparent;")
        status_h.addWidget(model_dot)
        status_h.addWidget(model_lbl)
        status_h.addWidget(ollama_dot)
        status_h.addWidget(ollama_lbl)

        header_layout.addWidget(logo_frame)
        header_layout.addWidget(div_line)
        header_layout.addWidget(status_frame)
        header_layout.addStretch()

        # Search bar
        search_wrap = QFrame()
        search_wrap.setStyleSheet("""
            QFrame { background: transparent; border: none; }
        """)
        search_h = QHBoxLayout(search_wrap)
        search_h.setContentsMargins(0, 0, 0, 0)
        search_h.setSpacing(6)
        search_icon_lbl = QLabel("🔍")
        search_icon_lbl.setStyleSheet("font-size: 13px; background: transparent; color: #8b949e;")
        self.header_search = QLineEdit()
        self.header_search.setPlaceholderText("Search conversations,")
        self.header_search.setFixedWidth(200)
        self.header_search.setFixedHeight(34)
        self.header_search.setStyleSheet("""
            QLineEdit {
                background-color: #161b22;
                color: #c9d1d9;
                border: 1px solid #7c3aed;
                border-radius: 8px;
                padding: 6px 12px;
                font-size: 12px;
            }
            QLineEdit:focus { border-color: #a78bfa; }
        """)
        search_h.addWidget(search_icon_lbl)
        search_h.addWidget(self.header_search)
        header_layout.addWidget(search_wrap)
        header_layout.addSpacing(12)

        # Model Loaded pill
        model_pill = QLabel("● Model Loaded")
        model_pill.setFixedHeight(34)
        model_pill.setStyleSheet("""
            QLabel {
                background-color: #1c1c2e;
                color: #a78bfa;
                border: 1px solid #6d28d9;
                border-radius: 8px;
                padding: 0px 14px;
                font-size: 12px;
                font-weight: 500;
            }
        """)
        header_layout.addWidget(model_pill)
        header_layout.addSpacing(8)

        # Scheduler Active pill
        sched_pill = QLabel("● Scheduler Active")
        sched_pill.setFixedHeight(34)
        sched_pill.setStyleSheet("""
            QLabel {
                background-color: #0d1f1a;
                color: #3fb950;
                border: 1px solid #238636;
                border-radius: 8px;
                padding: 0px 14px;
                font-size: 12px;
                font-weight: 500;
            }
        """)
        header_layout.addWidget(sched_pill)
        header_layout.addSpacing(10)

        # Bell
        bell_btn = QPushButton("🔔")
        bell_btn.setFixedSize(34, 34)
        bell_btn.setStyleSheet("""
            QPushButton { background: transparent; border: none; font-size: 15px; border-radius: 6px; color: #8b949e; }
            QPushButton:hover { background: #21262d; }
        """)
        header_layout.addWidget(bell_btn)

        # Gear
        gear_btn = QPushButton("⚙")
        gear_btn.setFixedSize(34, 34)
        gear_btn.setStyleSheet("""
            QPushButton { background: transparent; border: none; font-size: 16px; border-radius: 6px; color: #8b949e; }
            QPushButton:hover { background: #21262d; }
        """)
        header_layout.addWidget(gear_btn)

        main_layout.addWidget(header_bar)

        # ── Body: sidebar + pages ───────────────────────────────────────────
        body_widget = QWidget()
        body_layout = QHBoxLayout(body_widget)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # Sidebar
        sidebar_container = QWidget()
        sidebar_container.setFixedWidth(220)
        sidebar_container.setStyleSheet("background-color: #161b22; border-right: 1px solid #21262d;")
        sidebar_v = QVBoxLayout(sidebar_container)
        sidebar_v.setContentsMargins(0, 16, 0, 16)
        sidebar_v.setSpacing(0)

        self.sidebar = QListWidget()
        self.sidebar.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.sidebar.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.sidebar.setStyleSheet("""
            QListWidget {
                background: transparent;
                border: none;
                outline: none;
            }
            QListWidget::item {
                padding: 11px 14px;
                border-radius: 8px;
                margin: 2px 10px;
                color: #8b949e;
                font-size: 13px;
                font-weight: 500;
            }
            QListWidget::item:selected {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #6e40c9,stop:1 #8b5cf6);
                color: #ffffff;
                font-weight: 600;
            }
            QListWidget::item:hover:!selected {
                background-color: #21262d;
                color: #e6edf3;
            }
        """)
        self.add_sidebar_item("💬", "Chat")
        self.add_sidebar_item("≡", "Sessions")
        self.add_sidebar_item("☑", "Tasks")
        self.add_sidebar_item("❓", "Help")
        self.add_sidebar_item("🧠", "Memory")
        self.add_sidebar_item("〜", "Health")
        self.add_sidebar_item("⚙", "Settings")
        self.sidebar.currentRowChanged.connect(self.switch_page)
        # setSizePolicy + setFixedHeight ensures sidebar items never shift
        self.sidebar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        sidebar_v.addWidget(self.sidebar)
        # No addStretch() — stretching was causing the sidebar to compress

        body_layout.addWidget(sidebar_container)

        # Pages — QStackedWidget keeps all pages rendered at full size.
        # Only the current index is visible; the sidebar never shifts.
        self.pages = QStackedWidget()
        self.pages.setStyleSheet("background-color: #0d1117;")

        self.chat_page     = self.build_chat_page()
        self.sessions_page = self.build_sessions_page()
        self.tasks_page    = self.build_tasks_page()
        self.tools_page    = self.build_tools_page()
        self.memory_page   = self.build_memory_page()
        self.health_page   = self.build_health_page()
        self.settings_page = self.build_settings_page()

        self.pages.addWidget(self.chat_page)      # 0
        self.pages.addWidget(self.sessions_page)  # 1
        self.pages.addWidget(self.tasks_page)     # 2
        self.pages.addWidget(self.tools_page)     # 3
        self.pages.addWidget(self.memory_page)    # 4
        self.pages.addWidget(self.health_page)    # 5
        self.pages.addWidget(self.settings_page)  # 6

        body_layout.addWidget(self.pages)
        main_layout.addWidget(body_widget)

        self.sidebar.setCurrentRow(0)

        # ── Status bar ──────────────────────────────────────────────────────
        status_frame = QFrame()
        status_frame.setFixedHeight(26)
        status_frame.setStyleSheet("""
            QFrame {
                background-color: #161b22;
                border-top: 1px solid #21262d;
            }
        """)
        status_h = QHBoxLayout(status_frame)
        status_h.setContentsMargins(16, 0, 16, 0)

        dot = QLabel("●")
        dot.setStyleSheet("color: #3fb950; font-size: 8px; background: transparent;")
        status_h.addWidget(dot)
        status_h.addSpacing(6)

        self.status_bar = QLabel("Running")
        self.status_bar.setStyleSheet("color: #484f58; font-size: 11px; background: transparent;")
        status_h.addWidget(self.status_bar)
        status_h.addStretch()

        main_layout.addWidget(status_frame)

    def add_sidebar_item(self, icon, label):

        item = QListWidgetItem(f"{icon}  {label}")

        self.sidebar.addItem(item)

    def switch_page(self, index):
        self.pages.setCurrentIndex(index)
        if index == 1:
            self._reload_sessions_page()
        if index == 4:   # Memory page
            self._reload_memory_page()

    def build_chat_page(self):

        container = QWidget()
        container.setStyleSheet("background-color: #0d1117;")

        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── chat toolbar ─────────────────────────────────────────────────────
        toolbar_frame = QFrame()
        toolbar_frame.setFixedHeight(52)
        toolbar_frame.setStyleSheet("""
            QFrame {
                background-color: #0d1117;
                border-bottom: 1px solid #21262d;
            }
        """)
        toolbar = QHBoxLayout(toolbar_frame)
        toolbar.setContentsMargins(20, 0, 16, 0)
        toolbar.setSpacing(10)

        self.session_title_label = QLabel("New Chat")
        self.session_title_label.setStyleSheet(
            "font-size: 14px; font-weight: 600; color: #e6edf3; background: transparent;"
        )

        def _outline_btn(text, icon=""):
            b = QPushButton(f"{icon}  {text}" if icon else text)
            b.setStyleSheet("""
                QPushButton {
                    background-color: #161b22;
                    color: #8b949e;
                    border: 1px solid #30363d;
                    padding: 6px 14px;
                    border-radius: 8px;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background-color: #21262d;
                    color: #e6edf3;
                    border-color: #484f58;
                }
            """)
            return b

        new_chat_btn = QPushButton("+ New chat")
        new_chat_btn.setStyleSheet("""
            QPushButton {
                background-color: #7c3aed;
                color: white;
                border: none;
                padding: 6px 16px;
                border-radius: 8px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover { background-color: #8b5cf6; }
        """)
        new_chat_btn.clicked.connect(self.start_new_chat)

        sessions_btn = _outline_btn("Sessions", "🗂")
        sessions_btn.clicked.connect(self.open_sessions_dialog)

        search_btn = _outline_btn("Search", "🔍")
        search_btn.clicked.connect(self.open_search_dialog)

        toolbar.addWidget(self.session_title_label)
        toolbar.addStretch()
        toolbar.addWidget(new_chat_btn)
        toolbar.addWidget(sessions_btn)
        toolbar.addWidget(search_btn)

        layout.addWidget(toolbar_frame)

        # ── chat display ─────────────────────────────────────────────────────
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.chat_display.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.chat_display.setStyleSheet("""
            QTextEdit {
                background-color: #0d1117;
                color: #c9d1d9;
                font-family: "Segoe UI", sans-serif;
                font-size: 13.5px;
                border: none;
                padding: 24px 48px;
                line-height: 1.7;
            }
        """)
        layout.addWidget(self.chat_display)

        # ── input area ───────────────────────────────────────────────────────
        input_frame = QFrame()
        input_frame.setStyleSheet("""
            QFrame {
                background-color: #0d1117;
                border-top: 1px solid #21262d;
            }
        """)
        input_outer = QVBoxLayout(input_frame)
        input_outer.setContentsMargins(32, 10, 32, 14)
        input_outer.setSpacing(6)

        # ── Autocomplete commands ─────────────────────────────────────────────
        self._autocomplete_commands = [
            "open chrome", "open notepad", "open calculator",
            "open spotify", "open discord", "close chrome",
            "shutdown pc", "restart pc", "take screenshot",
            "read my screen", "system info", "what time is it",
            "what\'s today\'s date", "show tasks", "search file",
        ]

        # Compact autocomplete popup
        self._autocomplete_popup = QListWidget(container)
        self._autocomplete_popup.setVisible(False)
        self._autocomplete_popup.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._autocomplete_popup.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._autocomplete_popup.setFocusPolicy(Qt.NoFocus)
        self._autocomplete_popup.setStyleSheet("""
            QListWidget {
                background-color: #13181f;
                border: 1px solid #7c3aed88;
                border-radius: 10px;
                outline: none;
                padding: 4px;
            }
            QListWidget::item {
                color: #c9d1d9;
                padding: 6px 14px;
                border-radius: 6px;
                font-size: 12px;
            }
            QListWidget::item:hover {
                background-color: #1c1029;
                color: #e6edf3;
            }
            QListWidget::item:selected {
                background-color: #2d1f5e;
                color: #ffffff;
            }
        """)

        # ── Clean input box (no attach/mic clutter) ───────────────────────────
        input_box_frame = QFrame()
        input_box_frame.setFixedHeight(52)
        input_box_frame.setStyleSheet("""
            QFrame {
                background-color: #161b22;
                border: 1.5px solid #30363d;
                border-radius: 14px;
            }
        """)
        input_row = QHBoxLayout(input_box_frame)
        input_row.setContentsMargins(16, 0, 6, 0)
        input_row.setSpacing(8)

        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("Message Assistant…")
        self.input_box.setStyleSheet("""
            QLineEdit {
                background-color: transparent;
                color: #e6edf3;
                border: none;
                padding: 0;
                font-size: 13.5px;
                font-family: "Segoe UI", sans-serif;
            }
        """)
        self.input_box.returnPressed.connect(self.send_message)
        self.input_box.textChanged.connect(self._on_input_changed)

        send_button = QPushButton("➤")
        send_button.setFixedSize(38, 38)
        send_button.setCursor(Qt.PointingHandCursor)
        send_button.setStyleSheet("""
            QPushButton {
                background-color: #7c3aed;
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 15px;
                padding: 0;
            }
            QPushButton:hover  { background-color: #8b5cf6; }
            QPushButton:pressed { background-color: #6d28d9; }
        """)
        send_button.clicked.connect(self.send_message)

        input_row.addWidget(self.input_box)
        input_row.addWidget(send_button)
        input_outer.addWidget(input_box_frame)

        self._input_box_frame = input_box_frame
        self._autocomplete_popup.itemClicked.connect(self._on_autocomplete_select)
        self._autocomplete_popup.raise_()

        # ── Bottom bar: Voice | hint | Exit ──────────────────────────────────
        action_row = QHBoxLayout()
        action_row.setSpacing(0)
        action_row.setContentsMargins(2, 0, 2, 0)

        self.tts_toggle_btn = QPushButton("🔊  Voice On")
        self.tts_toggle_btn.setFixedHeight(26)
        self.tts_toggle_btn.setCursor(Qt.PointingHandCursor)
        self.tts_toggle_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #484f58;
                border: 1px solid #21262d;
                padding: 0 12px;
                border-radius: 6px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #161b22;
                color: #8b949e;
                border-color: #30363d;
            }
        """)
        self.tts_toggle_btn.setToolTip("Toggle voice on/off")
        self.tts_toggle_btn.clicked.connect(self._toggle_tts)

        hint_lbl = QLabel("Enter to send  ·  type for suggestions")
        hint_lbl.setStyleSheet(
            "color: #21262d; font-size: 10px; background: transparent;"
        )
        hint_lbl.setAlignment(Qt.AlignCenter)

        from core.shutdown_manager import shutdown
        exit_button = QPushButton("Exit")
        exit_button.setFixedHeight(26)
        exit_button.setCursor(Qt.PointingHandCursor)
        exit_button.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #484f58;
                border: 1px solid #21262d;
                padding: 0 14px;
                border-radius: 6px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #2a1515;
                color: #f85149;
                border-color: #6e2a2a;
            }
        """)
        exit_button.clicked.connect(shutdown)

        action_row.addWidget(self.tts_toggle_btn)
        action_row.addStretch()
        action_row.addWidget(hint_lbl)
        action_row.addStretch()
        action_row.addWidget(exit_button)
        input_outer.addLayout(action_row)

        layout.addWidget(input_frame)

        self._refresh_session_title()

        return container

    def _refresh_session_title(self):

        sid  = get_active_session_id()

        data = get_session_data(sid)

        title = data.get("title", "New Chat") if data else "New Chat"

        self.session_title_label.setText(title)

    def start_new_chat(self):

        new_session()

        self.chat_display.clear()

        self._refresh_session_title()

        self.status_bar.setText("New chat started")

    def open_sessions_dialog(self):

        dlg = SessionsDialog(self)

        dlg.session_switched.connect(self._on_session_switched)

        dlg.exec()

    def open_search_dialog(self):

        dlg = SearchDialog(self)

        dlg.session_switched.connect(self._on_session_switched)

        dlg.exec()

    def _on_session_switched(self, session_id):

        """Reload the chat display for the newly active session."""

        self.chat_display.clear()

        data = get_session_data(session_id)

        if not data:

            return

        self._refresh_session_title()

        for msg in data.get("messages", []):

            role    = msg.get("role", "")

            content = msg.get("content", "")

            if role == "user":

                self.append_user(content)

            elif role == "assistant":

                self.append_assistant(content)

        self.status_bar.setText(f"Switched to: {data.get('title', 'Session')}")

        # go back to Chat tab

        self.sidebar.setCurrentRow(0)

    def build_sessions_page(self):

        container = QWidget()
        container.setStyleSheet("background-color: #0d1117;")

        layout = QVBoxLayout(container)
        layout.setContentsMargins(32, 28, 32, 24)
        layout.setSpacing(12)

        title = QLabel("Sessions")
        title.setStyleSheet("font-size: 22px; font-weight: 700; color: #e6edf3; letter-spacing: -0.4px;")
        layout.addWidget(title)

        subtitle = QLabel("Double-click a session to open it")
        subtitle.setStyleSheet("color: #484f58; font-size: 12px; margin-bottom: 4px;")
        layout.addWidget(subtitle)

        # ── search bar ──

        self.sessions_search = QLineEdit()
        self.sessions_search.setPlaceholderText("🔍  Filter sessions…")
        self.sessions_search.setStyleSheet("""
            QLineEdit {
                background-color: #161b22;
                color: #c9d1d9;
                border: 1px solid #30363d;
                border-radius: 8px;
                padding: 9px 14px;
                font-size: 13px;
            }
            QLineEdit:focus { border-color: #7c3aed; background: #1c2128; }
        """)

        self.sessions_search.textChanged.connect(self._filter_sessions_page)

        layout.addWidget(self.sessions_search)

        # ── list ──

        self.sessions_list_page = QListWidget()
        self.sessions_list_page.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.sessions_list_page.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.sessions_list_page.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.sessions_list_page.setStyleSheet("""
            QListWidget {
                background-color: #161b22;
                border: 1px solid #21262d;
                border-radius: 10px;
                outline: none;
            }
            QListWidget::item {
                padding: 13px 16px;
                border-bottom: 1px solid #21262d;
                color: #c9d1d9;
                font-size: 13px;
            }
            QListWidget::item:selected {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #2a1a4e,stop:1 #3b2070);
                color: #e6edf3;
                border-left: 3px solid #8b5cf6;
            }
            QListWidget::item:hover:!selected { background-color: #1c2128; }
        """)

        self.sessions_list_page.itemDoubleClicked.connect(

            lambda item: self._on_session_switched(item.data(Qt.UserRole))

        )

        layout.addWidget(self.sessions_list_page)

        # ── buttons ──

        btn_row = QHBoxLayout()

        btn_row.setSpacing(8)

        new_btn = QPushButton("＋ New Chat")

        new_btn.clicked.connect(lambda: (self.start_new_chat(), self.sidebar.setCurrentRow(0)))

        def _dark_btn(text, danger=False):
            b = QPushButton(text)
            if danger:
                b.setStyleSheet("""
                    QPushButton { background-color: #2a1515; color: #f85149; border: 1px solid #6e2a2a;
                        padding: 7px 14px; border-radius: 8px; font-size: 12px; }
                    QPushButton:hover { background-color: #3a1a1a; border-color: #f85149; }
                """)
            else:
                b.setStyleSheet("""
                    QPushButton { background-color: #161b22; color: #8b949e; border: 1px solid #30363d;
                        padding: 7px 14px; border-radius: 8px; font-size: 12px; }
                    QPushButton:hover { background-color: #21262d; color: #e6edf3; }
                """)
            return b

        open_btn = _dark_btn("Open")
        open_btn.clicked.connect(lambda: self._open_selected_session_page())

        rename_btn = _dark_btn("Rename")
        rename_btn.clicked.connect(self._rename_selected_session_page)

        delete_btn = _dark_btn("Delete", danger=True)
        delete_btn.clicked.connect(self._delete_selected_session_page)

        export_btn = _dark_btn("Export…")
        export_btn.clicked.connect(self._export_selected_session_page)

        btn_row.addWidget(new_btn)
        btn_row.addWidget(open_btn)
        btn_row.addWidget(rename_btn)
        btn_row.addWidget(delete_btn)
        btn_row.addStretch()
        btn_row.addWidget(export_btn)

        layout.addLayout(btn_row)

        self._reload_sessions_page()

        return container

    def _reload_sessions_page(self):

        self.sessions_list_page.clear()

        active = get_active_session_id()

        self._all_sessions_cache = list_sessions()

        for s in self._all_sessions_cache:

            indicator = " ●" if s["id"] == active else ""

            label = (

                f"{s['title']}{indicator}\n"

                f"  {s['message_count']} messages · {s['updated']}"

            )

            item = QListWidgetItem(label)

            item.setData(Qt.UserRole, s["id"])

            self.sessions_list_page.addItem(item)

    def _filter_sessions_page(self, query):

        q = query.strip().lower()

        for i in range(self.sessions_list_page.count()):

            item = self.sessions_list_page.item(i)

            item.setHidden(q not in item.text().lower())

    def _open_selected_session_page(self):

        item = self.sessions_list_page.currentItem()

        if item:

            self._on_session_switched(item.data(Qt.UserRole))

    def _rename_selected_session_page(self):

        item = self.sessions_list_page.currentItem()

        if not item:

            return

        sid = item.data(Qt.UserRole)

        new_title, ok = QInputDialog.getText(self, "Rename", "New title:")

        if ok and new_title.strip():

            rename_session(sid, new_title.strip())

            self._reload_sessions_page()

            self._refresh_session_title()

    def _delete_selected_session_page(self):

        item = self.sessions_list_page.currentItem()

        if not item:

            return

        sid = item.data(Qt.UserRole)

        reply = QMessageBox.question(

            self,

            "Delete Session",

            "Delete this session? This cannot be undone.",

            QMessageBox.Yes | QMessageBox.No,

            QMessageBox.No

        )

        if reply == QMessageBox.Yes:

            delete_session(sid)

            self._reload_sessions_page()

            self._refresh_session_title()

    def _export_selected_session_page(self):

        item = self.sessions_list_page.currentItem()

        if not item:

            return

        sid = item.data(Qt.UserRole)

        fmt, ok = QInputDialog.getItem(

            self,

            "Export Format",

            "Select format:",

            ["txt", "md", "json"],

            0,

            False

        )

        if not ok:

            return

        dest, _ = QFileDialog.getSaveFileName(

            self,

            "Save session",

            f"session.{fmt}",

            f"Files (*.{fmt})"

        )

        if not dest:

            return

        success, result = export_session(sid, fmt, dest)

        if success:

            QMessageBox.information(self, "Exported", f"Saved to:\n{result}")

        else:

            QMessageBox.warning(self, "Export Failed", result)

    def _on_input_changed(self, text):
        """Show/hide autocomplete popup based on what the user is typing."""
        text = text.strip().lower()
        self._autocomplete_popup.clear()

        if len(text) < 2:
            self._autocomplete_popup.setVisible(False)
            return

        matches = [
            cmd for cmd in self._autocomplete_commands
            if text in cmd.lower()
        ]

        if not matches:
            self._autocomplete_popup.setVisible(False)
            return

        for cmd in matches[:5]:
            item = QListWidgetItem(f"  {cmd}")
            self._autocomplete_popup.addItem(item)

        row_h   = 30
        n       = min(len(matches), 5)
        popup_h = n * row_h + 12
        popup_w = min(self._input_box_frame.width(), 320)

        parent_widget = self._autocomplete_popup.parent()
        frame_pos = self._input_box_frame.mapTo(parent_widget, self._input_box_frame.rect().topLeft())
        popup_x = frame_pos.x()
        popup_y = frame_pos.y() - popup_h - 8

        self._autocomplete_popup.setGeometry(popup_x, popup_y, popup_w, popup_h)
        self._autocomplete_popup.setVisible(True)
        self._autocomplete_popup.raise_()

    def _on_autocomplete_select(self, item):
        """Complete the input box with the selected suggestion."""
        cmd = item.text().strip()
        self.input_box.setText(cmd)
        self.input_box.setCursorPosition(len(cmd))
        self._autocomplete_popup.setVisible(False)
        self.input_box.setFocus()

    def _send_suggestion(self, text):
        self.input_box.setText(text)
        self.send_message()

    def send_message(self):

        message = self.input_box.text().strip()

        if not message:

            return

        self._autocomplete_popup.setVisible(False)

        self.input_box.clear()

        self.append_user(message)

        msg_lower = message.lower().strip()

        # ── Direct keyword routing (runs BEFORE detect_intent) ────────────────
        # Catch "open X", "launch X", "start X", "run X" patterns
        _open_keywords = ("open ", "launch ", "start ", "run ")
        _is_open_cmd = any(msg_lower.startswith(kw) for kw in _open_keywords)

        # Exclude system-level open intents that have their own handlers
        _system_open = ("open app", "open the app", "launch app")
        _skip_direct = any(msg_lower.startswith(s) for s in _system_open)

        if _is_open_cmd and not _skip_direct:
            from tools.system_tools import open_app as _open_app
            response = _open_app(message)
            self.append_assistant(response)
            return

        # ── Intent engine routing ─────────────────────────────────────────────
        from core.intent_engine import detect_intent as _detect

        _intent = _detect(msg_lower)

        if _intent == "close_app":

            if confirm_action(
                self,
                "Are you sure you want to close the assistant?"
            ):

                close_app()

            return

        if _intent == "shutdown_pc":

            if confirm_action(
                self,
                "Are you sure you want to shut down the computer?"
            ):

                shutdown_pc()

            return

        if _intent == "restart_pc":

            if confirm_action(
                self,
                "Are you sure you want to restart the computer?"
            ):

                restart_pc()

            return

        if _intent == "kill_process":

            process_name = message.lower().replace("kill", "").strip()

            if confirm_action(
                self,
                f"Kill process '{process_name}'?"
            ):

                kill_process(process_name)

            return

        if _intent == "open_app":

            from tools.system_tools import open_app as _open_app

            response = _open_app(message)

            self.append_assistant(response)

            return

        if _intent == "close_external_app":

            from tools.system_tools import close_external_app as _close_external_app

            response = _close_external_app(message)

            self.append_assistant(response)

            return

        if _intent == "read_screen":
            self.append_assistant("Reading screen, please wait...")

            def _do_read_screen():
                from tools.screen_tools import read_screen as _rs
                result = _rs()
                display = result if result else "No text detected on screen."
                self._screen_result_signal.emit(display)

            Thread(target=_do_read_screen, daemon=True).start()
            return

        if _intent == "screenshot":
            self.append_assistant("Taking screenshot...")

            def _do_screenshot():
                from tools.screen_tools import screenshot_to_file as _ss
                path = _ss()
                self._screen_result_signal.emit(f"Screenshot saved:\n{path}")

            Thread(target=_do_screenshot, daemon=True).start()
            return

        if _intent == "last_screen":
            from tools.screen_tools import last_screen_text as _ls
            result = _ls()
            self.append_assistant(result)
            self._maybe_speak(result)
            return

        # ── Web search ────────────────────────────────────────────────────────
        if _intent == "web_search":
            self.append_assistant("🔍 Searching the web…")

            def _do_web_search():
                from tools.web_search_tool import web_search_tool as _wst
                result = _wst(message)
                self._tool_result_signal.emit(result)

            Thread(target=_do_web_search, daemon=True).start()
            return

        # ── Weather ───────────────────────────────────────────────────────────
        if _intent == "weather":
            self.append_assistant("🌍 Fetching weather…")

            def _do_weather():
                from tools.weather_tool import weather_tool as _wt
                result = _wt(message)
                self._tool_result_signal.emit(result)

            Thread(target=_do_weather, daemon=True).start()
            return

        # ── Plugin dispatch ───────────────────────────────────────────────────
        # Runs BEFORE handle_command/LLM so plugins get first pick of intents.
        if plugin_manager.can_handle(_intent):
            self.append_assistant("⚡ Running plugin…")

            def _do_plugin(i=_intent, t=message):
                result = plugin_manager.dispatch(i, t)
                self._tool_result_signal.emit(
                    result or "⚠️ Plugin returned no response."
                )

            Thread(target=_do_plugin, daemon=True).start()
            return

        # --- Normal command / chat flow ---
        # Run handle_command in a background thread so slow tools
        # (e.g. file search) never freeze the UI.

        def _run_tool():
            tool_response = handle_command(message)
            if tool_response is not None:
                self._tool_result_signal.emit(tool_response)
            else:
                # No tool matched — fall back to LLM stream on the UI thread
                # We must call start_stream via the signal so it runs safely.
                self._tool_result_signal.emit("")  # sentinel: empty = use LLM

        def _on_tool_done(response):
            if response == "":
                self.start_stream(message)
            # non-empty responses are already handled by _on_tool_result

        # Temporarily reroute the signal for this call
        # (simpler: just use a wrapper thread + QTimer for the LLM fallback)
        _intent_check = detect_intent(message.lower())
        _is_tool_intent = _intent_check != "chat"

        if _is_tool_intent:
            self.append_assistant("Working on it...")

            def _bg():
                tool_response = handle_command(message)
                if tool_response is not None:
                    self._tool_result_signal.emit(tool_response)
                else:
                    self._tool_result_signal.emit("\u26a0\ufe0f No response from tool.")

            Thread(target=_bg, daemon=True).start()
        else:
            self.start_stream(message)

    def append_user(self, message):
        from PySide6.QtGui import QTextCursor, QTextBlockFormat
        import html as _html

        safe = _html.escape(message)

        cursor = self.chat_display.textCursor()
        cursor.movePosition(QTextCursor.End)

        # Spacing block
        cursor.insertBlock()
        gap = QTextBlockFormat()
        gap.setTopMargin(10)
        gap.setAlignment(Qt.AlignRight)
        cursor.setBlockFormat(gap)

        # The HTML align="right" on the table itself is the most reliable way
        # Qt's rich text engine honours the table's own align attribute
        cursor.insertHtml(
            f'<table align="right" cellpadding="10" cellspacing="0" width="auto" style="'
            f'background-color:#7c3aed; border-radius:14px;">'
            f'<tr><td style="color:#ffffff; font-size:14px; font-family:Segoe UI; '
            f'white-space:pre-wrap; word-wrap:break-word; max-width:500px;">{safe}</td></tr></table>'
        )

        # Reset block
        cursor.insertBlock()
        reset = QTextBlockFormat()
        reset.setAlignment(Qt.AlignLeft)
        reset.setBottomMargin(4)
        cursor.setBlockFormat(reset)
        cursor.insertText("")

        self.chat_display.setTextCursor(cursor)
        self.chat_display.verticalScrollBar().setValue(
            self.chat_display.verticalScrollBar().maximum()
        )

    # ── Tool output rich formatter ────────────────────────────────────────────
    def _format_tool_output(self, message: str) -> str:
        """
        Convert plain-text tool output into styled HTML for the chat bubble.
        Handles: weather output, web search results, and plain text fallback.
        """
        import html as _html
        import re

        msg = message.strip()

        # ── Weather card ──────────────────────────────────────────────────────
        if msg.startswith("🌍 Weather for") or msg.startswith("\u26a0\ufe0f Could not"):
            return self._format_weather_html(msg)

        # ── Web search results ────────────────────────────────────────────────
        if msg.startswith("🔍 Web Search:") or msg.startswith("🔍 Searched for:"):
            return self._format_search_html(msg)

        # ── Generic fallback: smart plain-text formatting ─────────────────────
        return self._format_plain_html(msg)

    def _format_weather_html(self, msg: str) -> str:
        """Render weather output as a styled card."""
        import html as _html
        lines = msg.split("\n")
        html_parts = []
        html_parts.append(
            '<div style="font-family:Segoe UI,sans-serif; font-size:13.5px; color:#e6edf3; line-height:1.7;">'
        )
        for line in lines:
            s = line.strip()
            if not s:
                html_parts.append('<div style="height:6px;"></div>')
                continue
            safe = _html.escape(s)
            # Title line
            if s.startswith("🌍"):
                html_parts.append(
                    f'<div style="font-size:16px; font-weight:700; color:#e6edf3; '
                    f'margin-bottom:4px;">{safe}</div>'
                )
            # Section headers (📅 3-Day Forecast:)
            elif s.startswith("📅"):
                html_parts.append(
                    f'<div style="font-size:12px; font-weight:600; color:#8b949e; '
                    f'text-transform:uppercase; letter-spacing:0.8px; margin-top:10px; '
                    f'margin-bottom:4px; border-top:1px solid #30363d; padding-top:8px;">{safe}</div>'
                )
            # Forecast day rows (start with date like 2026-)
            elif re.match(r'\d{4}-\d{2}-\d{2}', s):
                parts = s.split(None, 1)
                date_str = parts[0] if parts else s
                rest = _html.escape(parts[1]) if len(parts) > 1 else ""
                html_parts.append(
                    f'<div style="display:flex; background:#161b22; border-radius:8px; '
                    f'padding:5px 10px; margin:2px 0; font-size:13px;">'
                    f'<span style="color:#8b949e; min-width:90px;">{_html.escape(date_str)}</span>'
                    f'<span style="color:#c9d1d9;">{rest}</span></div>'
                )
            # Warning lines
            elif s.startswith("⚠️"):
                html_parts.append(
                    f'<div style="color:#f85149; background:#2a1515; border-radius:8px; '
                    f'padding:8px 12px; margin:4px 0; font-size:13px;">{safe}</div>'
                )
            # Stat lines (🌡 💧 💨 and condition)
            else:
                html_parts.append(f'<div style="font-size:13.5px; color:#c9d1d9;">{safe}</div>')

        html_parts.append('</div>')
        return "".join(html_parts)

    def _format_search_html(self, msg: str) -> str:
        """Render web search results with header and clickable links."""
        import html as _html
        import re
        lines = msg.split("\n")
        html_parts = []
        html_parts.append(
            '<div style="font-family:Segoe UI,sans-serif; font-size:13.5px; color:#e6edf3; line-height:1.7;">'
        )
        for i, line in enumerate(lines):
            s = line.strip()
            if not s:
                if i > 0:
                    html_parts.append('<div style="height:4px;"></div>')
                continue
            safe = _html.escape(s)
            # Header line "🔍 Web Search: query"
            if s.startswith("🔍"):
                query_part = safe.split(":", 1)[-1].strip() if ":" in safe else safe
                html_parts.append(
                    f'<div style="font-size:13px; font-weight:600; color:#8b949e; '
                    f'border-bottom:1px solid #30363d; padding-bottom:8px; margin-bottom:8px;">'
                    f'🔍 &nbsp;<span style="color:#a78bfa;">{query_part}</span></div>'
                )
            # Abstract summary (📖)
            elif s.startswith("📖"):
                text = safe[3:].strip()
                html_parts.append(
                    f'<div style="background:#161b22; border-left:3px solid #7c3aed; '
                    f'border-radius:0 8px 8px 0; padding:8px 12px; margin:4px 0; '
                    f'font-size:13px; color:#c9d1d9;">{text}</div>'
                )
            # Answer line (✅)
            elif s.startswith("✅"):
                text = safe[2:].strip()
                html_parts.append(
                    f'<div style="background:#0d2a1a; border:1px solid #238636; '
                    f'border-radius:8px; padding:8px 12px; margin:4px 0; '
                    f'font-size:13px; color:#3fb950; font-weight:600;">{text}</div>'
                )
            # Source / link lines (🔗 or "Source:")
            elif s.startswith("🔗") or s.startswith("Source:"):
                raw_url = re.sub(r'^(🔗|Source:)\s*', '', s).strip()
                safe_url = _html.escape(raw_url)
                display = raw_url[:60] + "…" if len(raw_url) > 60 else raw_url
                safe_display = _html.escape(display)
                html_parts.append(
                    f'<div style="margin:-2px 0 4px 0;">'
                    f'<a href="{safe_url}" style="color:#58a6ff; font-size:11.5px; '
                    f'text-decoration:none;">{safe_display}</a></div>'
                )
            # Bullet result items (•)
            elif s.startswith("•"):
                text = safe[1:].strip()
                html_parts.append(
                    f'<div style="padding:6px 0 2px 0; font-size:13px; color:#c9d1d9; '
                    f'border-top:1px solid #21262d; margin-top:4px;">{text}</div>'
                )
            # Warning
            elif s.startswith("⚠️") or s.startswith("No results"):
                html_parts.append(
                    f'<div style="color:#f85149; font-size:13px; margin:6px 0;">{safe}</div>'
                )
            else:
                html_parts.append(f'<div style="font-size:13px; color:#8b949e;">{safe}</div>')

        html_parts.append('</div>')
        return "".join(html_parts)

    def _format_plain_html(self, msg: str) -> str:
        """Smart plain-text → HTML: handles headers, bullets, code blocks, links."""
        import html as _html
        import re
        lines = msg.split("\n")
        html_parts = []
        html_parts.append(
            '<div style="font-family:Segoe UI,sans-serif; font-size:13.5px; '
            f'color:#e6edf3; line-height:1.7;">'
        )
        in_code = False
        for line in lines:
            s = line.rstrip()
            if s.strip() == "" and not in_code:
                html_parts.append('<div style="height:5px;"></div>')
                continue
            safe = _html.escape(s)
            # Code fence
            if s.startswith("```"):
                if not in_code:
                    in_code = True
                    html_parts.append(
                        '<div style="background:#161b22; border:1px solid #30363d; '
                        'border-radius:8px; padding:10px 14px; margin:6px 0; '
                        'font-family:Consolas,monospace; font-size:12px; color:#e6edf3;">'
                    )
                else:
                    in_code = False
                    html_parts.append('</div>')
                continue
            if in_code:
                html_parts.append(f'<div style="white-space:pre;">{safe}</div>')
                continue
            # Emoji-prefixed "headers" (lines that start with emoji and are short)
            if re.match(r'^[\U00010000-\U0010ffff\u2600-\u27BF]\S* .{1,60}$', s) and len(s) < 65 and s.endswith(":"):
                html_parts.append(
                    f'<div style="font-size:13px; font-weight:600; color:#8b949e; '
                    f'margin-top:10px; letter-spacing:0.5px;">{safe}</div>'
                )
            # Warning / error lines
            elif "⚠" in s or "error" in s.lower() and s.startswith("⚠"):
                html_parts.append(
                    f'<div style="color:#f85149; font-size:13px; margin:2px 0;">{safe}</div>'
                )
            # Success lines
            elif s.startswith("✅") or s.startswith("✓"):
                html_parts.append(
                    f'<div style="color:#3fb950; font-size:13px; margin:2px 0;">{safe}</div>'
                )
            # Bullet points
            elif s.startswith("•") or s.startswith("- ") or s.startswith("* "):
                text = safe[1:].strip() if safe.startswith("•") else safe[2:].strip()
                html_parts.append(
                    f'<div style="padding:1px 0 1px 14px; color:#c9d1d9; font-size:13px; '
                    f'text-indent:-10px;">• {text}</div>'
                )
            # Numbered list
            elif re.match(r'^\d+[.)]', s):
                html_parts.append(
                    f'<div style="padding:1px 0 1px 14px; color:#c9d1d9; font-size:13px;">{safe}</div>'
                )
            else:
                html_parts.append(f'<div style="font-size:13.5px; color:#c9d1d9; margin:1px 0;">{safe}</div>')

        if in_code:
            html_parts.append('</div>')
        html_parts.append('</div>')
        return "".join(html_parts)

    def append_assistant(self, message):
        from PySide6.QtGui import QTextCursor, QTextBlockFormat
        import html as _html

        # ── skip the empty "Working on it..." replacement sentinel ────────────
        if message == "":
            return

        rich_html = self._format_tool_output(message)

        cursor = self.chat_display.textCursor()
        cursor.movePosition(QTextCursor.End)

        # Spacing
        cursor.insertBlock()
        gap = QTextBlockFormat()
        gap.setTopMargin(4)
        gap.setAlignment(Qt.AlignLeft)
        cursor.setBlockFormat(gap)

        cursor.insertHtml(
            f'<table align="left" cellpadding="12" cellspacing="0" width="auto" style="'
            f'background-color:#1e2533; border-radius:4px 14px 14px 14px;">'
            f'<tr><td style="color:#e6edf3; font-size:14px; font-family:Segoe UI; '
            f'line-height:1.65; white-space:normal; word-wrap:break-word; max-width:620px;">{rich_html}</td></tr></table>'
        )

        # ── Copy button — floating overlay ────────────────────────────────────
        self._add_copy_button(message)

        # Reset block
        cursor.insertBlock()
        reset = QTextBlockFormat()
        reset.setAlignment(Qt.AlignLeft)
        reset.setBottomMargin(10)
        cursor.setBlockFormat(reset)
        cursor.insertText("")

        self.chat_display.setTextCursor(cursor)
        self.chat_display.verticalScrollBar().setValue(
            self.chat_display.verticalScrollBar().maximum()
        )

    def _add_copy_button(self, message: str):
        """Add a small floating copy button that appears over the last assistant bubble."""
        from PySide6.QtWidgets import QApplication as _QApp

        btn = QPushButton("⎘ Copy", self.chat_display)
        btn.setFixedSize(64, 24)
        btn.setStyleSheet("""
            QPushButton {
                background-color: #21262d;
                color: #8b949e;
                border: 1px solid #30363d;
                border-radius: 5px;
                font-size: 10px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #7c3aed;
                color: #ffffff;
                border-color: #7c3aed;
            }
        """)

        _msg = message   # capture for closure

        def _copy():
            _QApp.clipboard().setText(_msg)
            btn.setText("✓ Copied")
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #0d3321;
                    color: #3fb950;
                    border: 1px solid #238636;
                    border-radius: 5px;
                    font-size: 10px;
                    font-weight: 500;
                }
            """)
            QTimer.singleShot(1500, lambda: (
                btn.setText("⎘ Copy"),
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #21262d;
                        color: #8b949e;
                        border: 1px solid #30363d;
                        border-radius: 5px;
                        font-size: 10px;
                        font-weight: 500;
                    }
                    QPushButton:hover {
                        background-color: #7c3aed;
                        color: #ffffff;
                        border-color: #7c3aed;
                    }
                """)
            ))

        btn.clicked.connect(_copy)

        # Position: top-right of the chat_display viewport, just below top edge
        vp = self.chat_display.viewport()
        x = vp.width() - btn.width() - 12
        y = vp.height() - btn.height() - 12
        btn.move(x, y)
        btn.raise_()
        btn.show()

        # Store reference so old buttons can be repositioned on resize
        if not hasattr(self, "_copy_buttons"):
            self._copy_buttons = []
        # Keep only last 20
        self._copy_buttons.append(btn)
        if len(self._copy_buttons) > 20:
            old = self._copy_buttons.pop(0)
            old.deleteLater()

        # Auto-hide after 4 seconds
        QTimer.singleShot(4000, lambda: btn.hide() if btn else None)

    def start_stream(self, prompt):

        self._stream_buffer = ""
        self._is_streaming = True

        from PySide6.QtGui import QTextCursor, QTextBlockFormat

        cursor = self.chat_display.textCursor()
        cursor.movePosition(QTextCursor.End)

        cursor.insertBlock()
        gap = QTextBlockFormat()
        gap.setTopMargin(4)
        cursor.setBlockFormat(gap)

        cursor.insertBlock()
        blk = QTextBlockFormat()
        blk.setAlignment(Qt.AlignLeft)
        cursor.setBlockFormat(blk)

        cursor.insertHtml(
            '<table align="left" cellpadding="10" cellspacing="0" style="background-color:#1c2128;">'
            '<tr><td style="color:#555e6d; font-size:13px; font-family:Segoe UI; '
            'font-style:italic;">Nova is typing\u2026</td></tr></table>'
        )

        # Save position so we can delete the indicator later
        self._typing_cursor_pos = self.chat_display.document().characterCount()

        self.chat_display.setTextCursor(cursor)
        self.chat_display.verticalScrollBar().setValue(
            self.chat_display.verticalScrollBar().maximum()
        )

        self.worker = StreamWorker(prompt)
        self.worker.signals.token.connect(self.buffer_token)
        self.worker.signals.finished.connect(self.stream_finished)
        Thread(target=self.worker.run, daemon=True).start()

    def buffer_token(self, token):

        self._stream_buffer += token

    def stream_finished(self):

        self._is_streaming = False

        from PySide6.QtGui import QTextCursor
        doc = self.chat_display.document()
        cursor = QTextCursor(doc)

        # Select from just before typing indicator to end, delete it
        pos = max(0, self._typing_cursor_pos - 1)
        cursor.setPosition(pos)
        cursor.movePosition(QTextCursor.End, QTextCursor.KeepAnchor)
        cursor.removeSelectedText()

        self.append_assistant(self._stream_buffer)
        self._maybe_speak(self._stream_buffer)
        self._stream_buffer = ""

    # ---------- /HELP PAGE ----------

    def build_tools_page(self):
        """Help page — explains every tool with usage examples."""

        TOOL_HELP = [
            {
                "icon": "▶",
                "name": "Open App",
                "category": "System",
                "desc": "Launch any application installed on your computer.",
                "examples": ["open notepad", "open chrome", "launch calculator", "start vlc"],
            },
            {
                "icon": "✕",
                "name": "Close App",
                "category": "System",
                "desc": "Close the assistant application.",
                "examples": ["close app", "exit assistant", "quit"],
            },
            {
                "icon": "⚡",
                "name": "Kill Process",
                "category": "System",
                "desc": "Force-terminate a running process by name.",
                "examples": ["kill notepad", "kill chrome", "kill process explorer"],
            },
            {
                "icon": "⏻",
                "name": "Shutdown PC",
                "category": "System",
                "desc": "Shut down your computer. Requires confirmation.",
                "examples": ["shutdown pc", "shut down computer", "power off"],
            },
            {
                "icon": "↺",
                "name": "Restart PC",
                "category": "System",
                "desc": "Restart your computer. Requires confirmation.",
                "examples": ["restart pc", "reboot computer", "restart my machine"],
            },
            {
                "icon": "📸",
                "name": "Screenshot",
                "category": "Screen",
                "desc": "Take a screenshot and save it to disk.",
                "examples": ["take screenshot", "capture screen", "screenshot now"],
            },
            {
                "icon": "👁",
                "name": "Read Screen",
                "category": "Screen",
                "desc": "Extract and read all visible text on your screen using OCR.",
                "examples": ["read my screen", "read screen", "what's on my screen"],
            },
            {
                "icon": "📋",
                "name": "Last Screen Text",
                "category": "Screen",
                "desc": "Recall the text extracted during the previous screen read.",
                "examples": ["show last screen text", "what did you read last"],
            },
            {
                "icon": "🖥",
                "name": "System Info",
                "category": "Info",
                "desc": "Display CPU, RAM, OS, and hardware information.",
                "examples": ["system info", "show system info", "what are my specs"],
            },
            {
                "icon": "⏱",
                "name": "Get Time",
                "category": "Info",
                "desc": "Tell you the current local time.",
                "examples": ["what time is it", "current time", "what's the time"],
            },
            {
                "icon": "📆",
                "name": "Get Date",
                "category": "Info",
                "desc": "Tell you today's date.",
                "examples": ["what's today's date", "what day is it", "today's date"],
            },
            {
                "icon": "📅",
                "name": "Schedule Task",
                "category": "Scheduler",
                "desc": "Schedule a reminder or command to run at a specific time.",
                "examples": [
                    "remind me to drink water in 30 minutes",
                    "schedule a task at 5pm",
                    "set a reminder for tomorrow 9am",
                ],
            },
            {
                "icon": "📋",
                "name": "List Tasks",
                "category": "Scheduler",
                "desc": "Show all currently scheduled tasks and their status.",
                "examples": ["show tasks", "list tasks", "what tasks are scheduled"],
            },
            {
                "icon": "🔍",
                "name": "Search File",
                "category": "Files",
                "desc": "Search for a file by name across your drives.",
                "examples": ["search file report.pdf", "find file budget.xlsx"],
            },
            {
                "icon": "💬",
                "name": "AI Chat",
                "category": "Chat",
                "desc": "Ask anything — if no tool matches, your question goes to the AI model.",
                "examples": [
                    "explain quantum computing",
                    "write a poem about rain",
                    "what is the capital of France",
                ],
            },
            {
                "icon": "🔍",
                "name": "Web Search",
                "category": "Web",
                "desc": "Search the web via DuckDuckGo — no API key needed.",
                "examples": [
                    "search for python tutorials",
                    "web search latest AI news",
                    "look up best laptops 2025",
                    "google what is quantum computing",
                ],
            },
            {
                "icon": "🌤",
                "name": "Weather",
                "category": "Web",
                "desc": "Get current weather and 3-day forecast for any city worldwide.",
                "examples": [
                    "weather in London",
                    "what's the weather in Tokyo",
                    "weather for New York",
                    "temperature in Mumbai",
                ],
            },
        ]

        CATEGORY_COLORS = {
            "System":    ("#7c3aed", "#1c1029"),
            "Screen":    ("#0ea5e9", "#071a26"),
            "Info":      ("#10b981", "#071a16"),
            "Scheduler": ("#f59e0b", "#1f1508"),
            "Files":     ("#f97316", "#1f1108"),
            "Chat":      ("#ec4899", "#1f0a14"),
            "Web":       ("#06b6d4", "#051a1f"),
        }

        container = QWidget()
        container.setStyleSheet("background-color: #0d1117;")

        outer = QVBoxLayout(container)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Top bar ───────────────────────────────────────────────────────────
        top_bar = QFrame()
        top_bar.setFixedHeight(62)
        top_bar.setStyleSheet("background-color: #0d1117; border-bottom: 1px solid #21262d;")
        top_h = QHBoxLayout(top_bar)
        top_h.setContentsMargins(32, 0, 32, 0)
        top_h.setSpacing(12)

        title_lbl = QLabel("/help  —  Command Reference")
        title_lbl.setStyleSheet(
            "font-size: 16px; font-weight: 700; color: #e6edf3; font-family: 'Consolas', monospace;"
        )
        top_h.addWidget(title_lbl)
        top_h.addStretch()

        count_pill = QLabel(f"  {len(TOOL_HELP)} tools  ")
        count_pill.setFixedHeight(26)
        count_pill.setStyleSheet("""
            QLabel {
                background-color: #161b22;
                color: #8b949e;
                border: 1px solid #30363d;
                border-radius: 6px;
                padding: 0 10px;
                font-size: 11px;
            }
        """)
        top_h.addWidget(count_pill)

        # Search filter
        self._help_search = QLineEdit()
        self._help_search.setPlaceholderText("🔍  Filter commands…")
        self._help_search.setFixedWidth(200)
        self._help_search.setFixedHeight(32)
        self._help_search.setStyleSheet("""
            QLineEdit {
                background-color: #161b22;
                color: #c9d1d9;
                border: 1px solid #30363d;
                border-radius: 7px;
                padding: 4px 12px;
                font-size: 12px;
            }
            QLineEdit:focus { border-color: #7c3aed; }
        """)
        self._help_search.textChanged.connect(self._filter_help_cards)
        top_h.addWidget(self._help_search)

        outer.addWidget(top_bar)

        # ── Scrollable card grid ──────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        scroll_content = QWidget()
        scroll_content.setStyleSheet("background-color: #0d1117;")

        self._help_grid = QVBoxLayout(scroll_content)
        self._help_grid.setContentsMargins(32, 24, 32, 32)
        self._help_grid.setSpacing(10)

        # Store card widgets for filtering
        self._help_cards = []

        for tool in TOOL_HELP:
            cat = tool["category"]
            accent, bg = CATEGORY_COLORS.get(cat, ("#7c3aed", "#1c1029"))

            card = QFrame()
            card.setObjectName("helpCard")
            card.setStyleSheet(f"""
                QFrame#helpCard {{
                    background-color: #161b22;
                    border: 1px solid #21262d;
                    border-radius: 12px;
                }}
                QFrame#helpCard:hover {{
                    border-color: {accent};
                    background-color: #1c2128;
                }}
            """)

            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(18, 14, 18, 14)
            card_layout.setSpacing(6)

            # Row 1: icon + name + category badge
            row1 = QHBoxLayout()
            row1.setSpacing(10)

            icon_lbl = QLabel(tool["icon"])
            icon_lbl.setFixedSize(32, 32)
            icon_lbl.setAlignment(Qt.AlignCenter)
            icon_lbl.setStyleSheet(f"""
                QLabel {{
                    background-color: {bg};
                    border: 1px solid {accent}44;
                    border-radius: 8px;
                    font-size: 14px;
                }}
            """)

            name_lbl = QLabel(tool["name"])
            name_lbl.setStyleSheet(
                "color: #e6edf3; font-size: 14px; font-weight: 700; background: transparent;"
            )

            cat_badge = QLabel(f"  {cat}  ")
            cat_badge.setFixedHeight(20)
            cat_badge.setStyleSheet(f"""
                QLabel {{
                    background-color: {bg};
                    color: {accent};
                    border: 1px solid {accent}55;
                    border-radius: 5px;
                    font-size: 10px;
                    font-weight: 600;
                    padding: 0 6px;
                }}
            """)

            row1.addWidget(icon_lbl)
            row1.addWidget(name_lbl)
            row1.addStretch()
            row1.addWidget(cat_badge)
            card_layout.addLayout(row1)

            # Row 2: description
            desc_lbl = QLabel(tool["desc"])
            desc_lbl.setWordWrap(True)
            desc_lbl.setStyleSheet("color: #8b949e; font-size: 12px; background: transparent;")
            card_layout.addWidget(desc_lbl)

            # Row 3: examples as inline chips
            examples_row = QHBoxLayout()
            examples_row.setSpacing(6)
            examples_row.setAlignment(Qt.AlignLeft)

            eg_intro = QLabel("Try:")
            eg_intro.setStyleSheet("color: #484f58; font-size: 11px; background: transparent;")
            examples_row.addWidget(eg_intro)

            for ex in tool["examples"]:
                chip = QLabel(f'"{ex}"')
                chip.setStyleSheet(f"""
                    QLabel {{
                        background-color: #0d1117;
                        color: {accent};
                        border: 1px solid #30363d;
                        border-radius: 5px;
                        padding: 2px 8px;
                        font-size: 11px;
                        font-family: 'Consolas', monospace;
                    }}
                """)
                examples_row.addWidget(chip)

            examples_row.addStretch()
            card_layout.addLayout(examples_row)

            self._help_grid.addWidget(card)
            self._help_cards.append((tool, card))

        self._help_grid.addStretch()
        scroll.setWidget(scroll_content)
        outer.addWidget(scroll)

        return container

    def _filter_help_cards(self, query):
        """Show/hide help cards based on search query."""
        q = query.strip().lower()
        for tool, card in self._help_cards:
            if not q:
                card.setVisible(True)
            else:
                haystack = (
                    tool["name"] + tool["desc"] + tool["category"] +
                    " ".join(tool["examples"])
                ).lower()
                card.setVisible(q in haystack)

    # ---------- MEMORY PAGE ----------

    def build_memory_page(self):
        """View and edit stored memory entries."""
        from services.memory_service import load_memory, save_memory
        import json as _json

        container = QWidget()
        container.setStyleSheet("background-color: #0d1117;")

        outer = QVBoxLayout(container)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Top bar ───────────────────────────────────────────────────────────
        top_bar = QFrame()
        top_bar.setFixedHeight(62)
        top_bar.setStyleSheet("background-color: #0d1117; border-bottom: 1px solid #21262d;")
        top_h = QHBoxLayout(top_bar)
        top_h.setContentsMargins(32, 0, 32, 0)
        top_h.setSpacing(10)

        title_lbl = QLabel("🧠  Memory")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: 700; color: #e6edf3;")
        top_h.addWidget(title_lbl)
        top_h.addStretch()

        self._mem_count_pill = QLabel("  0 entries  ")
        self._mem_count_pill.setFixedHeight(26)
        self._mem_count_pill.setStyleSheet("""
            QLabel {
                background-color: #161b22;
                color: #8b949e;
                border: 1px solid #30363d;
                border-radius: 6px;
                padding: 0 10px;
                font-size: 11px;
            }
        """)
        top_h.addWidget(self._mem_count_pill)

        add_btn = QPushButton("＋ Add entry")
        add_btn.setFixedHeight(32)
        add_btn.setStyleSheet("""
            QPushButton {
                background-color: #7c3aed;
                color: #ffffff;
                border: none;
                border-radius: 7px;
                padding: 0 14px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover { background-color: #8b5cf6; }
        """)
        add_btn.clicked.connect(self._memory_add_entry)
        top_h.addWidget(add_btn)

        outer.addWidget(top_bar)

        # ── Subtitle ──────────────────────────────────────────────────────────
        sub_bar = QFrame()
        sub_bar.setFixedHeight(38)
        sub_bar.setStyleSheet("background-color: #0d1117; border: none;")
        sub_h = QHBoxLayout(sub_bar)
        sub_h.setContentsMargins(32, 0, 32, 0)
        sub_lbl = QLabel("Facts Nova remembers about you — click any row to edit or delete it.")
        sub_lbl.setStyleSheet("color: #484f58; font-size: 12px;")
        sub_h.addWidget(sub_lbl)
        outer.addWidget(sub_bar)

        # ── Scrollable list of memory rows ────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self._mem_scroll_content = QWidget()
        self._mem_scroll_content.setStyleSheet("background-color: #0d1117;")
        self._mem_rows_layout = QVBoxLayout(self._mem_scroll_content)
        self._mem_rows_layout.setContentsMargins(32, 16, 32, 32)
        self._mem_rows_layout.setSpacing(8)
        self._mem_rows_layout.addStretch()

        scroll.setWidget(self._mem_scroll_content)
        outer.addWidget(scroll)

        # ── Bottom action bar ─────────────────────────────────────────────────
        action_bar = QFrame()
        action_bar.setFixedHeight(52)
        action_bar.setStyleSheet("background-color: #161b22; border-top: 1px solid #21262d;")
        action_h = QHBoxLayout(action_bar)
        action_h.setContentsMargins(32, 0, 32, 0)
        action_h.setSpacing(10)

        clear_btn = QPushButton("🗑  Clear All Memory")
        clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a1515;
                color: #f85149;
                border: 1px solid #6e2a2a;
                border-radius: 7px;
                padding: 6px 16px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #3a1a1a; border-color: #f85149; }
        """)
        clear_btn.clicked.connect(self._memory_clear_all)

        refresh_btn = QPushButton("↻  Refresh")
        refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #161b22;
                color: #8b949e;
                border: 1px solid #30363d;
                border-radius: 7px;
                padding: 6px 16px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #21262d; color: #e6edf3; }
        """)
        refresh_btn.clicked.connect(self._reload_memory_page)

        action_h.addWidget(clear_btn)
        action_h.addStretch()
        action_h.addWidget(refresh_btn)
        outer.addWidget(action_bar)

        return container

    def _reload_memory_page(self):
        """Refresh the memory page rows from disk."""
        from services.memory_service import load_memory

        layout = self._mem_rows_layout

        # Remove all rows except the trailing stretch
        while layout.count() > 1:
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        memory = load_memory()

        # Flatten nested profile dict
        flat = {}
        for k, v in memory.items():
            if isinstance(v, dict):
                for sk, sv in v.items():
                    flat[sk] = sv
            else:
                flat[k] = v

        self._mem_count_pill.setText(f"  {len(flat)} entr{'y' if len(flat)==1 else 'ies'}  ")

        if not flat:
            empty = QLabel("No memories stored yet.\nChat with Nova and it will remember things you tell it.")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet("color: #484f58; font-size: 13px;")
            layout.insertWidget(0, empty)
            return

        for i, (key, value) in enumerate(flat.items()):
            row = self._make_memory_row(key, str(value))
            layout.insertWidget(i, row)

    def _make_memory_row(self, key: str, value: str) -> QFrame:
        """Build one editable memory row card."""
        row = QFrame()
        row.setObjectName("memRow")
        row.setStyleSheet("""
            QFrame#memRow {
                background-color: #161b22;
                border: 1px solid #21262d;
                border-radius: 10px;
            }
            QFrame#memRow:hover { border-color: #7c3aed; }
        """)
        row.setFixedHeight(60)

        h = QHBoxLayout(row)
        h.setContentsMargins(16, 0, 12, 0)
        h.setSpacing(12)

        key_lbl = QLabel(key)
        key_lbl.setFixedWidth(160)
        key_lbl.setStyleSheet("color: #a78bfa; font-size: 12px; font-weight: 600; background: transparent;")

        val_lbl = QLabel(value)
        val_lbl.setStyleSheet("color: #c9d1d9; font-size: 13px; background: transparent;")
        val_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        edit_btn = QPushButton("✏")
        edit_btn.setFixedSize(30, 30)
        edit_btn.setStyleSheet("""
            QPushButton { background: transparent; border: 1px solid #30363d; border-radius: 6px;
                color: #8b949e; font-size: 13px; }
            QPushButton:hover { background: #21262d; color: #e6edf3; }
        """)
        edit_btn.setToolTip(f"Edit '{key}'")
        edit_btn.clicked.connect(lambda _, k=key, v=value: self._memory_edit_entry(k, v))

        del_btn = QPushButton("✕")
        del_btn.setFixedSize(30, 30)
        del_btn.setStyleSheet("""
            QPushButton { background: transparent; border: 1px solid #30363d; border-radius: 6px;
                color: #f85149; font-size: 13px; }
            QPushButton:hover { background: #2a1515; border-color: #f85149; }
        """)
        del_btn.setToolTip(f"Delete '{key}'")
        del_btn.clicked.connect(lambda _, k=key: self._memory_delete_entry(k))

        h.addWidget(key_lbl)
        h.addWidget(val_lbl)
        h.addWidget(edit_btn)
        h.addWidget(del_btn)

        return row

    def _memory_add_entry(self):
        from services.memory_service import save_memory
        key, ok = QInputDialog.getText(self, "Add Memory", "Key (e.g. 'hobby'):")
        if not ok or not key.strip():
            return
        value, ok2 = QInputDialog.getText(self, "Add Memory", f"Value for '{key.strip()}':")
        if not ok2:
            return
        save_memory(key.strip(), value.strip())
        self._reload_memory_page()

    def _memory_edit_entry(self, key: str, current_value: str):
        from services.memory_service import save_memory
        new_val, ok = QInputDialog.getText(
            self, "Edit Memory", f"New value for '{key}':", text=current_value
        )
        if ok:
            save_memory(key, new_val.strip())
            self._reload_memory_page()

    def _memory_delete_entry(self, key: str):
        import json, os
        from core.config import resource_path
        MEMORY_FILE = resource_path("memory.json")
        try:
            with open(MEMORY_FILE, "r") as f:
                data = json.load(f)
            # Try flat key first, then nested profile
            if key in data:
                del data[key]
            elif "profile" in data and key in data["profile"]:
                del data["profile"][key]
            with open(MEMORY_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass
        self._reload_memory_page()

    def _memory_clear_all(self):
        import json, os
        from core.config import resource_path
        reply = QMessageBox.question(
            self, "Clear Memory",
            "Delete ALL stored memories? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            MEMORY_FILE = resource_path("memory.json")
            try:
                with open(MEMORY_FILE, "w") as f:
                    json.dump({}, f)
            except Exception:
                pass
            self._reload_memory_page()

    def build_tasks_page(self):

        container = QWidget()
        container.setStyleSheet("background-color: #0d1117;")

        layout = QVBoxLayout(container)
        layout.setContentsMargins(32, 28, 32, 24)
        layout.setSpacing(16)

        title = QLabel("Scheduled Tasks")
        title.setStyleSheet("font-size: 22px; font-weight: 700; color: #e6edf3; letter-spacing: -0.4px;")
        layout.addWidget(title)

        subtitle = QLabel("Manage your reminders and automated scripts")
        subtitle.setStyleSheet("color: #484f58; font-size: 12px;")
        layout.addWidget(subtitle)

        self.task_display = QTextEdit()
        self.task_display.setReadOnly(True)
        self.task_display.setStyleSheet("""
            QTextEdit {
                background-color: #161b22;
                color: #c9d1d9;
                border: 1px solid #21262d;
                border-radius: 10px;
                padding: 16px;
                font-size: 13px;
                font-family: "Consolas", monospace;
                line-height: 1.6;
            }
        """)
        layout.addWidget(self.task_display)

        def _btn(text, danger=False):
            b = QPushButton(text)
            if danger:
                b.setStyleSheet("""
                    QPushButton { background-color: #2a1515; color: #f85149; border: 1px solid #6e2a2a;
                        padding: 7px 16px; border-radius: 8px; font-size: 12px; }
                    QPushButton:hover { background-color: #3a1a1a; border-color: #f85149; }
                """)
            else:
                b.setStyleSheet("""
                    QPushButton { background-color: #161b22; color: #8b949e; border: 1px solid #30363d;
                        padding: 7px 16px; border-radius: 8px; font-size: 12px; }
                    QPushButton:hover { background-color: #21262d; color: #e6edf3; }
                """)
            return b

        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)

        pause_btn   = _btn("⏸  Pause")
        resume_btn  = _btn("▶  Resume")
        cancel_btn  = _btn("✕  Cancel")
        remove_btn  = _btn("🗑  Remove All", danger=True)

        pause_btn.clicked.connect(self.pause_task)
        resume_btn.clicked.connect(self.resume_task)
        cancel_btn.clicked.connect(self.cancel_task)
        remove_btn.clicked.connect(self.remove_all_tasks)

        button_layout.addWidget(pause_btn)
        button_layout.addWidget(resume_btn)
        button_layout.addWidget(cancel_btn)
        button_layout.addStretch()
        button_layout.addWidget(remove_btn)

        layout.addLayout(button_layout)

        self.start_task_timer()

        return container

    def start_task_timer(self):

        self.timer = QTimer()

        self.timer.timeout.connect(self.refresh_tasks)

        self.timer.start(2000)

    def refresh_tasks(self):

        tasks = list_tasks()

        self.task_display.setText(tasks)

    def ask_number(self, title):

        number, ok = QInputDialog.getInt(
            self, title, "Enter task number:"
        )

        return number, ok

    def pause_task(self):

        number, ok = self.ask_number("Pause Task")

        if ok:

            response = handle_command(f"pause task {number}")

            QMessageBox.information(self, "Result", response)

    def resume_task(self):

        number, ok = self.ask_number("Resume Task")

        if ok:

            response = handle_command(f"resume task {number}")

            QMessageBox.information(self, "Result", response)

    def cancel_task(self):

        number, ok = self.ask_number("Cancel Task")

        if ok:

            response = handle_command(f"cancel task {number}")

            QMessageBox.information(self, "Result", response)

    def remove_all_tasks(self):

        response = handle_command("cancel all tasks")

        QMessageBox.information(self, "Result", response)

    def build_settings_page(self):

        container = QWidget()
        container.setStyleSheet("background-color: #0d1117;")

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        inner = QWidget()
        inner.setStyleSheet("background-color: #0d1117;")
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(32, 28, 32, 32)
        layout.setSpacing(0)

        # ── Helper: section header ─────────────────────────────────────────────
        def _section(title_text, subtitle_text=""):
            layout.addSpacing(10)
            t = QLabel(title_text)
            t.setStyleSheet("font-size: 13px; font-weight: 600; color: #e6edf3;")
            layout.addWidget(t)
            if subtitle_text:
                s = QLabel(subtitle_text)
                s.setStyleSheet("color: #484f58; font-size: 11px; margin-top: 1px;")
                layout.addWidget(s)
            layout.addSpacing(8)

        def _divider():
            div = QFrame(); div.setFixedHeight(1)
            div.setStyleSheet("background-color: #21262d; margin: 14px 0;")
            layout.addWidget(div)

        def _row_checkbox(label_text, checked=False):
            cb = QCheckBox(label_text)
            cb.setChecked(checked)
            cb.setStyleSheet("""
                QCheckBox { color: #c9d1d9; font-size: 13px; spacing: 8px; }
                QCheckBox::indicator { width: 16px; height: 16px; border-radius: 4px;
                    border: 1px solid #30363d; background: #161b22; }
                QCheckBox::indicator:checked { background: #7c3aed; border-color: #7c3aed; }
                QCheckBox::indicator:hover { border-color: #7c3aed; }
            """)
            layout.addWidget(cb)
            return cb

        # ── Title ──────────────────────────────────────────────────────────────
        title = QLabel("Settings")
        title.setStyleSheet("font-size: 22px; font-weight: 700; color: #e6edf3; letter-spacing: -0.4px;")
        layout.addWidget(title)
        subtitle = QLabel("Manage your assistant preferences")
        subtitle.setStyleSheet("color: #484f58; font-size: 12px; margin-top: 2px;")
        layout.addWidget(subtitle)
        _divider()

        # ── AI Model ──────────────────────────────────────────────────────────
        _section("🤖  AI Model", "Choose the Ollama model to use for chat responses")
        config = load_config()
        self.model_dropdown = QComboBox()
        self.model_dropdown.addItems([
            "qwen2.5:3b", "qwen2.5:7b", "llama3:8b", "mistral:7b", "phi3:mini", "gemma:2b"
        ])
        self.model_dropdown.setCurrentText(config.get("model", "qwen2.5:3b"))
        self.model_dropdown.setStyleSheet("""
            QComboBox {
                background-color: #161b22; color: #e6edf3; border: 1px solid #30363d;
                border-radius: 8px; padding: 8px 12px; font-size: 13px;
            }
            QComboBox:focus { border-color: #7c3aed; }
            QComboBox::drop-down { border: none; width: 24px; }
            QComboBox QAbstractItemView {
                background-color: #161b22; color: #e6edf3;
                selection-background-color: #7c3aed; border: 1px solid #30363d;
            }
        """)
        layout.addWidget(self.model_dropdown)
        _divider()

        # ── Chat Behaviour ─────────────────────────────────────────────────────
        _section("💬  Chat Behaviour")
        self.setting_tts_default = _row_checkbox(
            "Enable voice (TTS) by default on startup",
            checked=config.get("tts_default", True)
        )
        self.setting_stream = _row_checkbox(
            "Stream AI responses token by token",
            checked=config.get("stream_responses", True)
        )
        self.setting_show_typing = _row_checkbox(
            "Show 'Nova is typing…' indicator while streaming",
            checked=config.get("show_typing_indicator", True)
        )
        self.setting_autocomplete = _row_checkbox(
            "Show command autocomplete suggestions while typing",
            checked=config.get("autocomplete_enabled", True)
        )
        _divider()

        # ── Memory ────────────────────────────────────────────────────────────
        _section("🧠  Memory", "Control what the assistant remembers about you")
        self.setting_memory = _row_checkbox(
            "Enable memory — remember facts across conversations",
            checked=config.get("memory_enabled", True)
        )
        self.setting_memory_prompt = _row_checkbox(
            "Inject memory into AI system prompt",
            checked=config.get("memory_in_prompt", True)
        )
        _divider()

        # ── Notifications ─────────────────────────────────────────────────────
        _section("🔔  Notifications")
        self.setting_tray_notif = _row_checkbox(
            "Show system tray notifications for scheduled tasks",
            checked=config.get("tray_notifications", True)
        )
        self.setting_task_sound = _row_checkbox(
            "Play sound when a scheduled task fires",
            checked=config.get("task_sound", False)
        )
        _divider()

        # ── Appearance ────────────────────────────────────────────────────────
        _section("🎨  Appearance")
        self.setting_compact = _row_checkbox(
            "Compact chat bubbles (reduced padding)",
            checked=config.get("compact_bubbles", False)
        )
        self.setting_timestamps = _row_checkbox(
            "Show timestamps on chat messages",
            checked=config.get("show_timestamps", False)
        )
        _divider()

        # ── Startup ───────────────────────────────────────────────────────────
        _section("🚀  Startup")
        self.auto_start_checkbox = _row_checkbox(
            "Launch Assistant automatically when Windows starts",
            checked=is_auto_start_enabled()
        )
        self.setting_start_minimized = _row_checkbox(
            "Start minimized to system tray",
            checked=config.get("start_minimized", False)
        )
        _divider()

        # ── Privacy ───────────────────────────────────────────────────────────
        _section("🔒  Privacy")
        self.setting_log_conversations = _row_checkbox(
            "Save conversations to session history",
            checked=config.get("log_conversations", True)
        )
        self.setting_anon_errors = _row_checkbox(
            "Log errors to local log file",
            checked=config.get("log_errors", True)
        )

        layout.addSpacing(20)

        # ── Save button ────────────────────────────────────────────────────────
        save_button = QPushButton("  💾   Save Settings")
        save_button.setFixedHeight(42)
        save_button.setStyleSheet("""
            QPushButton {
                background-color: #7c3aed; color: #ffffff; border: none;
                border-radius: 10px; font-size: 13px; font-weight: 600;
            }
            QPushButton:hover { background-color: #8b5cf6; }
            QPushButton:pressed { background-color: #6d28d9; }
        """)
        save_button.clicked.connect(self.save_settings)
        layout.addWidget(save_button)

        scroll.setWidget(inner)

        outer_layout = QVBoxLayout(container)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(scroll)

        return container

    def save_settings(self):

        config = load_config()

        selected_model = self.model_dropdown.currentText()
        config["model"] = selected_model

        # Chat behaviour
        config["tts_default"]            = self.setting_tts_default.isChecked()
        config["stream_responses"]       = self.setting_stream.isChecked()
        config["show_typing_indicator"]  = self.setting_show_typing.isChecked()
        config["autocomplete_enabled"]   = self.setting_autocomplete.isChecked()

        # Memory
        config["memory_enabled"]         = self.setting_memory.isChecked()
        config["memory_in_prompt"]       = self.setting_memory_prompt.isChecked()

        # Notifications
        config["tray_notifications"]     = self.setting_tray_notif.isChecked()
        config["task_sound"]             = self.setting_task_sound.isChecked()

        # Appearance
        config["compact_bubbles"]        = self.setting_compact.isChecked()
        config["show_timestamps"]        = self.setting_timestamps.isChecked()

        # Startup
        config["start_minimized"]        = self.setting_start_minimized.isChecked()

        # Privacy
        config["log_conversations"]      = self.setting_log_conversations.isChecked()
        config["log_errors"]             = self.setting_anon_errors.isChecked()

        save_config(config)

        if not is_model_installed(selected_model):
            reply = QMessageBox.question(
                self,
                "Download Model",
                f"{selected_model} is not installed. Download it now?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                dialog = ModelDownloadDialog(
                    preselect_model=selected_model,
                    lock_model=True
                )
                dialog.exec()

        if self.auto_start_checkbox.isChecked():
            enable_auto_start()
            self.status_bar.setText("Startup enabled")
        else:
            disable_auto_start()
            self.status_bar.setText("Startup disabled")

        # Apply TTS default immediately
        self._tts_enabled = self.setting_tts_default.isChecked()
        if self._tts_enabled:
            self.tts_toggle_btn.setText("🔊  Voice On")
        else:
            self.tts_toggle_btn.setText("🔇  Voice Off")

        self.status_bar.setText("Settings saved ✓")
        QMessageBox.information(self, "Settings", "Settings saved successfully.")


# ---------- ENSURE MODEL INSTALLED ----------

def ensure_model_installed():

    try:

        model = get_setting("model")

    except Exception:

        model = None

    if model and is_model_installed(model):

        return

    dialog = ModelDownloadDialog(
        preselect_model=model,
        lock_model=False
    )

    result = dialog.exec()

    if result != QDialog.Accepted:

        sys.exit(0)


# ---------- MAIN ----------

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

    sys.exit(app.exec())


if __name__ == "__main__":

    main()