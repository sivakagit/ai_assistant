import sys
import time
from threading import Thread
from ollama_setup import ensure_ollama_ready

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
)

from PySide6.QtCore import (
    QTimer,
    Signal,
    QObject,
    Qt
)

import ollama

from tools_manager import registry
from tts import speak_async, stop

from confirmation_dialog import confirm_action

from system_actions import (
    close_app,
    shutdown_pc,
    restart_pc,
    kill_process
)
from intent import detect_intent

from scheduler import (
    start_scheduler,
    list_tasks
)

from memory import load_memory, maybe_store_memory
from conversation import (
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

from conversation_search import search_conversations
from export import export_session, export_all_sessions

from settings import (
    load_config,
    save_config,
    get_setting
)

from tray_qt import TrayManager

from startup import (
    enable_auto_start,
    disable_auto_start,
    is_auto_start_enabled
)

from model_downloader import (
    is_model_installed,
    detect_hardware,
    DownloadController
)


# ---------- SYSTEM ACTION REGISTRATIONS ----------

registry.register("close_app", close_app)

registry.register("shutdown_pc", shutdown_pc)

registry.register("restart_pc", restart_pc)

registry.register("kill_process", kill_process)


# ---------- STREAM SIGNALS ----------

class StreamSignals(QObject):

    token = Signal(str)

    finished = Signal()


# ---------- MEMORY PROMPT ----------

def build_memory_prompt(user_input):
    """Returns the plain user message unchanged.
    Memory is injected only into the system prompt by build_system_prompt().
    """
    return user_input


def build_system_prompt():
    """Builds the system prompt, embedding memory as silent background context."""

    base = (
        "You are a personal AI assistant. "
        "Be concise and focused on what the user actually asks. "
        "If they say hi or chat casually, just respond naturally — "
        "do not bring up anything about them unless they ask."
    )

    memory_data = load_memory()

    if not memory_data:

        return base

    memory_lines = []

    for key, value in memory_data.items():

        if isinstance(value, dict):

            for subkey, subvalue in value.items():

                memory_lines.append(f"{subkey}: {subvalue}")

        else:

            memory_lines.append(f"{key}: {value}")

    if not memory_lines:

        return base

    memory_text = "\n".join(memory_lines)

    return (
        f"{base}\n\n"
        f"The following facts about the user are stored for context. "
        f"Do NOT mention them unless the user's message makes them directly relevant:\n"
        f"{memory_text}"
    )


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

            messages = [

                {
                    "role": "system",
                    "content": build_system_prompt()
                }

            ] + history + [

                {
                    "role": "user",
                    "content": memory_prompt
                }

            ]

            stream = ollama.chat(
                model=get_setting("model"),
                messages=messages,
                stream=True
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

        except Exception:

            pass

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

class AssistantUI(QWidget):

    _screen_result_signal = Signal(str)

    def __init__(self):

        super().__init__()

        self.setWindowTitle("Assistant")

        self.resize(1150, 720)

        # TTS toggle state — False means muted, True means speaking enabled
        self._tts_enabled = True

        self.apply_styles()

        self.build_ui()

        self.init_tray()

        self._screen_result_signal.connect(self._on_screen_result)

    def _on_screen_result(self, display: str):

        self.append_assistant(display)

        self._maybe_speak(display)

    def _maybe_speak(self, text: str):
        if self._tts_enabled:
        # pyttsx3 on Windows stops at newlines — replace with a pause (space)
            clean = text.replace("\n", " ").replace("\r", " ").strip()
            speak_async(clean)

    def _toggle_tts(self):
        """Toggle TTS on/off and update the button appearance."""
        self._tts_enabled = not self._tts_enabled
        if self._tts_enabled:
            self.tts_toggle_btn.setText("🔊 Voice On")
            self.tts_toggle_btn.setStyleSheet("""
                QPushButton {
                    background-color: #0078d4;
                    color: white;
                    border: none;
                    padding: 8px 14px;
                    border-radius: 6px;
                    font-size: 12px;
                }
                QPushButton:hover { background-color: #2893ff; }
            """)
        else:
            stop()
            self.tts_toggle_btn.setText("🔇 Voice Off")
            self.tts_toggle_btn.setStyleSheet("""
                QPushButton {
                    background-color: #444444;
                    color: #aaaaaa;
                    border: 1px solid #555555;
                    padding: 8px 14px;
                    border-radius: 6px;
                    font-size: 12px;
                }
                QPushButton:hover { background-color: #555555; }
            """)

    def init_tray(self):

        try:

            if not QSystemTrayIcon.isSystemTrayAvailable():

                print("System tray not available")

                return

            self.tray = TrayManager(self)

            print("Tray initialized")

        except Exception as e:

            print("Tray initialization failed:", e)

    def apply_styles(self):

        self.setStyleSheet("""
        QWidget {
            background-color: #1e1e1e;
            color: white;
            font-family: Segoe UI;
            font-size: 13px;
        }
        QListWidget {
            background-color: #252526;
            border: none;
        }
        QListWidget::item {
            padding: 12px;
        }
        QListWidget::item:selected {
            background-color: #0078d4;
        }
        QPushButton {
            background-color: #0078d4;
            color: white;
            border: none;
            padding: 8px 14px;
            border-radius: 6px;
        }
        QPushButton:hover {
            background-color: #2893ff;
        }
        """)

    def closeEvent(self, event):

        try:

            minimize = get_setting("window_minimize_to_tray")

        except Exception:

            minimize = True

        if minimize:

            event.ignore()

            self.hide()

            self.status_bar.setText("Running in system tray")

        else:

            event.accept()

    def build_ui(self):

        main_layout = QVBoxLayout(self)

        header = QLabel("Assistant")

        header.setStyleSheet("""
            font-size: 18px;
            font-weight: bold;
            padding: 12px;
            background-color: #2d2d30;
        """)

        main_layout.addWidget(header)

        body_layout = QHBoxLayout()

        main_layout.addLayout(body_layout)

        self.sidebar = QListWidget()

        self.add_sidebar_item("💬  Chat")

        self.add_sidebar_item("🗂️  Sessions")

        self.add_sidebar_item("📋  Tasks")

        self.add_sidebar_item("⚙️  Settings")

        self.sidebar.setFixedWidth(190)

        self.sidebar.currentRowChanged.connect(self.switch_page)

        body_layout.addWidget(self.sidebar)

        self.pages = QVBoxLayout()

        self.chat_page     = self.build_chat_page()

        self.sessions_page = self.build_sessions_page()

        self.tasks_page    = self.build_tasks_page()

        self.settings_page = self.build_settings_page()

        self.pages.addWidget(self.chat_page)

        self.pages.addWidget(self.sessions_page)

        self.pages.addWidget(self.tasks_page)

        self.pages.addWidget(self.settings_page)

        body_layout.addLayout(self.pages)

        self.sidebar.setCurrentRow(0)

        self.status_bar = QLabel("Status: Running")

        self.status_bar.setStyleSheet("""
            padding: 6px;
            background-color: #2d2d30;
        """)

        main_layout.addWidget(self.status_bar)

    def add_sidebar_item(self, text):

        item = QListWidgetItem(text)

        self.sidebar.addItem(item)

    def switch_page(self, index):

        for i in range(self.pages.count()):

            widget = self.pages.itemAt(i).widget()

            widget.setVisible(False)

        widget = self.pages.itemAt(index).widget()

        widget.setVisible(True)

        # Refresh sessions list whenever the sessions tab is opened

        if index == 1:

            self._reload_sessions_page()

    def build_chat_page(self):

        container = QWidget()

        layout = QVBoxLayout(container)

        layout.setSpacing(6)

        # ── session toolbar ──────────────────────────────────────────────────

        toolbar = QHBoxLayout()

        toolbar.setSpacing(6)

        self.session_title_label = QLabel("New Chat")

        self.session_title_label.setStyleSheet(

            "color: #aaaaaa; font-size: 12px; padding: 0 4px;"

        )

        new_chat_btn = QPushButton("＋ New Chat")

        new_chat_btn.setStyleSheet("""
            QPushButton {
                background-color: #0078d4;
                color: white;
                border: none;
                padding: 5px 12px;
                border-radius: 5px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #2893ff; }
        """)

        new_chat_btn.clicked.connect(self.start_new_chat)

        sessions_btn = QPushButton("🗂 Sessions")

        sessions_btn.setStyleSheet("""
            QPushButton {
                background-color: #2d2d30;
                color: #cccccc;
                border: 1px solid #3f3f3f;
                padding: 5px 12px;
                border-radius: 5px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #3a3a3a; }
        """)

        sessions_btn.clicked.connect(self.open_sessions_dialog)

        search_btn = QPushButton("🔍 Search")

        search_btn.setStyleSheet("""
            QPushButton {
                background-color: #2d2d30;
                color: #cccccc;
                border: 1px solid #3f3f3f;
                padding: 5px 12px;
                border-radius: 5px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #3a3a3a; }
        """)

        search_btn.clicked.connect(self.open_search_dialog)

        toolbar.addWidget(self.session_title_label)

        toolbar.addStretch()

        toolbar.addWidget(new_chat_btn)

        toolbar.addWidget(sessions_btn)

        toolbar.addWidget(search_btn)

        layout.addLayout(toolbar)

        # ── chat display ─────────────────────────────────────────────────────

        self.chat_display = QTextEdit()

        self.chat_display.setReadOnly(True)

        self.chat_display.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #ffffff;
                font-family: Segoe UI;
                font-size: 13px;
                border: none;
                padding: 10px;
            }
        """)

        layout.addWidget(self.chat_display)

        # ── input row ────────────────────────────────────────────────────────

        input_layout = QHBoxLayout()

        self.input_box = QLineEdit()

        self.input_box.setPlaceholderText("Type a message…")

        self.input_box.setStyleSheet("""
            QLineEdit {
                background-color: #2d2d30;
                color: #ffffff;
                border: 1px solid #3f3f3f;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
            }
        """)

        self.input_box.returnPressed.connect(self.send_message)

        send_button = QPushButton("Send")

        # ── TTS toggle button ─────────────────────────────────────────────────

        self.tts_toggle_btn = QPushButton("🔊 Voice On")

        self.tts_toggle_btn.setStyleSheet("""
            QPushButton {
                background-color: #0078d4;
                color: white;
                border: none;
                padding: 8px 14px;
                border-radius: 6px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #2893ff; }
        """)

        self.tts_toggle_btn.setToolTip("Toggle voice output on/off")

        self.tts_toggle_btn.clicked.connect(self._toggle_tts)

        exit_button = QPushButton("Exit")

        exit_button.setStyleSheet("""
            QPushButton {
                background-color: #c42b1c;
                color: white;
                border: none;
                padding: 8px 14px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #e03a28;
            }
        """)

        send_button.clicked.connect(self.send_message)

        exit_button.clicked.connect(QApplication.quit)

        input_layout.addWidget(self.input_box)

        input_layout.addWidget(send_button)

        input_layout.addWidget(self.tts_toggle_btn)

        input_layout.addWidget(exit_button)

        layout.addLayout(input_layout)

        # ── init session title ───────────────────────────────────────────────

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

        layout = QVBoxLayout(container)

        layout.setContentsMargins(12, 12, 12, 12)

        layout.setSpacing(8)

        title = QLabel("Chat Sessions")

        title.setStyleSheet("font-size: 15px; font-weight: bold;")

        layout.addWidget(title)

        subtitle = QLabel("Double-click a session to open it.")

        subtitle.setStyleSheet("color: #888888; font-size: 11px;")

        layout.addWidget(subtitle)

        # ── search bar ──

        self.sessions_search = QLineEdit()

        self.sessions_search.setPlaceholderText("Filter sessions…")

        self.sessions_search.setStyleSheet("""
            QLineEdit {
                background-color: #2d2d30;
                color: #ffffff;
                border: 1px solid #3f3f3f;
                border-radius: 6px;
                padding: 7px 10px;
            }
        """)

        self.sessions_search.textChanged.connect(self._filter_sessions_page)

        layout.addWidget(self.sessions_search)

        # ── list ──

        self.sessions_list_page = QListWidget()

        self.sessions_list_page.setStyleSheet("""
            QListWidget {
                background-color: #252526;
                border: 1px solid #3f3f3f;
                border-radius: 6px;
            }
            QListWidget::item { padding: 10px; border-bottom: 1px solid #2d2d30; }
            QListWidget::item:selected { background-color: #0078d4; }
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

        open_btn = QPushButton("Open")

        open_btn.clicked.connect(lambda: self._open_selected_session_page())

        rename_btn = QPushButton("Rename")

        rename_btn.setStyleSheet("""
            QPushButton {
                background-color: #2d2d30;
                border: 1px solid #3f3f3f;
                color: #cccccc;
                padding: 7px 14px;
                border-radius: 6px;
            }
            QPushButton:hover { background-color: #3a3a3a; }
        """)

        rename_btn.clicked.connect(self._rename_selected_session_page)

        delete_btn = QPushButton("Delete")

        delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #c42b1c;
                color: white;
                border: none;
                padding: 7px 14px;
                border-radius: 6px;
            }
            QPushButton:hover { background-color: #e03a28; }
        """)

        delete_btn.clicked.connect(self._delete_selected_session_page)

        export_btn = QPushButton("Export…")

        export_btn.setStyleSheet("""
            QPushButton {
                background-color: #2d2d30;
                border: 1px solid #3f3f3f;
                color: #cccccc;
                padding: 7px 14px;
                border-radius: 6px;
            }
            QPushButton:hover { background-color: #3a3a3a; }
        """)

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

    def send_message(self):

        message = self.input_box.text().strip()

        if not message:

            return

        self.input_box.clear()

        self.append_user(message)

        # --- System actions: require confirmation before executing ---

        from intent import detect_intent as _detect

        _intent = _detect(message.lower())

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

            from system_actions import open_app as _open_app

            response = _open_app(message)

            self.append_assistant(response)

            return

        if _intent == "close_external_app":

            from system_actions import close_external_app as _close_external_app

            response = _close_external_app(message)

            self.append_assistant(response)

            return

        if _intent == "read_screen":
            self.append_assistant("Reading screen, please wait...")

            def _do_read_screen():
                from screen_reader import read_screen as _rs
                result = _rs()
                display = result if result else "No text detected on screen."
                self._screen_result_signal.emit(display)

            Thread(target=_do_read_screen, daemon=True).start()
            return

        if _intent == "screenshot":
            self.append_assistant("Taking screenshot...")

            def _do_screenshot():
                from screen_reader import screenshot_to_file as _ss
                path = _ss()
                self._screen_result_signal.emit(f"Screenshot saved:\n{path}")

            Thread(target=_do_screenshot, daemon=True).start()
            return

        if _intent == "last_screen":
            from screen_reader import last_screen_text as _ls
            result = _ls()
            self.append_assistant(result)
            self._maybe_speak(result)
            return

        # --- Normal command / chat flow ---

        tool_response = handle_command(message)

        if tool_response is not None:

            self.append_assistant(tool_response)

            self._maybe_speak(tool_response)

            return

        self.start_stream(message)

    def append_user(self, message):

        self.chat_display.append(
            f'<div style="margin: 8px 0 2px 0;">'
            f'<span style="color:#7eb8f7; font-weight:bold;">You</span>'
            f'<span style="color:#555;"> ▸ </span>'
            f'<span style="color:#ffffff;">{message}</span>'
            f'</div>'
        )

    def append_assistant(self, message):

        message = message.replace("\n", "<br>")

        self.chat_display.append(
            f'<div style="margin: 2px 0 12px 0; padding: 8px 12px;'
            f'background-color:#252526; border-left: 3px solid #0078d4;'
            f'border-radius:4px;">'
            f'<span style="color:#0078d4; font-weight:bold;">Assistant</span><br>'
            f'<span style="color:#cccccc;">{message}</span>'
            f'</div>'
        )

    def start_stream(self, prompt):

        self._stream_buffer = ""

        self.worker = StreamWorker(prompt)

        self.worker.signals.token.connect(self.buffer_token)

        self.worker.signals.finished.connect(self.stream_finished)

        Thread(target=self.worker.run, daemon=True).start()

    def buffer_token(self, token):

        self._stream_buffer += token

    def stream_finished(self):

        self.append_assistant(self._stream_buffer)

        self._maybe_speak(self._stream_buffer)

        self._stream_buffer = ""

    def build_tasks_page(self):

        container = QWidget()

        layout = QVBoxLayout(container)

        self.task_display = QTextEdit()

        self.task_display.setReadOnly(True)

        layout.addWidget(self.task_display)

        button_layout = QHBoxLayout()

        pause_btn = QPushButton("Pause")

        resume_btn = QPushButton("Resume")

        cancel_btn = QPushButton("Cancel")

        remove_btn = QPushButton("Remove All")

        pause_btn.clicked.connect(self.pause_task)

        resume_btn.clicked.connect(self.resume_task)

        cancel_btn.clicked.connect(self.cancel_task)

        remove_btn.clicked.connect(self.remove_all_tasks)

        button_layout.addWidget(pause_btn)

        button_layout.addWidget(resume_btn)

        button_layout.addWidget(cancel_btn)

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

        layout = QVBoxLayout(container)

        config = load_config()

        layout.addWidget(QLabel("Model"))

        self.model_dropdown = QComboBox()

        self.model_dropdown.addItems([
            "qwen2.5:3b",
            "llama3:8b",
            "mistral:7b",
            "phi3:mini"
        ])

        self.model_dropdown.setCurrentText(config.get("model"))

        layout.addWidget(self.model_dropdown)

        self.auto_start_checkbox = QCheckBox("Start on Windows login")

        self.auto_start_checkbox.setChecked(is_auto_start_enabled())

        layout.addWidget(self.auto_start_checkbox)

        save_button = QPushButton("Save Settings")

        save_button.clicked.connect(self.save_settings)

        layout.addWidget(save_button)

        return container

    def save_settings(self):

        config = load_config()

        selected_model = self.model_dropdown.currentText()

        config["model"] = selected_model

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

        QMessageBox.information(self, "Settings", "Settings saved")


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