"""
ui/command_palette.py

Global Command Palette — press Ctrl+Space anywhere in the app to open.
Type any command, press Enter or click to execute instantly.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLineEdit, QListWidget, QListWidgetItem,
    QLabel, QFrame, QApplication,
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QKeySequence, QShortcut


# ── All known commands (intent → display label → example phrases) ─────────────

PALETTE_COMMANDS = [
    # ── System ──────────────────────────────────────────────────────────────
    {"label": "Open App",          "category": "System",    "examples": ["open chrome", "open notepad", "open calculator", "open spotify"]},
    {"label": "Close App",         "category": "System",    "examples": ["close chrome", "close notepad", "close discord"]},
    {"label": "Shutdown PC",       "category": "System",    "examples": ["shutdown pc", "power off", "shut down computer"]},
    {"label": "Restart PC",        "category": "System",    "examples": ["restart pc", "reboot computer"]},
    {"label": "Kill Process",      "category": "System",    "examples": ["kill notepad", "kill chrome", "kill process explorer"]},
    {"label": "System Info",       "category": "System",    "examples": ["system info", "show system info", "my specs"]},
    # ── Screen ──────────────────────────────────────────────────────────────
    {"label": "Take Screenshot",   "category": "Screen",    "examples": ["take screenshot", "capture screen", "screenshot now"]},
    {"label": "Read Screen",       "category": "Screen",    "examples": ["read my screen", "what's on my screen", "scan screen"]},
    {"label": "Explain Screen",    "category": "Screen",    "examples": ["explain my screen", "describe what you see", "what app is open"]},
    {"label": "Last Screen Text",  "category": "Screen",    "examples": ["show last screen text", "what did you read last"]},
    # ── Info ────────────────────────────────────────────────────────────────
    {"label": "Current Time",      "category": "Info",      "examples": ["what time is it", "current time", "time now"]},
    {"label": "Today's Date",      "category": "Info",      "examples": ["what's today's date", "what day is it", "today's date"]},
    # ── Scheduler ───────────────────────────────────────────────────────────
    {"label": "Create Reminder",   "category": "Scheduler", "examples": ["remind me in 10 minutes", "remind me to drink water", "set a reminder for 5pm"]},
    {"label": "Show Tasks",        "category": "Scheduler", "examples": ["show tasks", "list tasks", "what tasks are scheduled"]},
    {"label": "Cancel All Tasks",  "category": "Scheduler", "examples": ["cancel all tasks", "clear all tasks", "remove all reminders"]},
    # ── Files ────────────────────────────────────────────────────────────────
    {"label": "Search File",       "category": "Files",     "examples": ["find file report.pdf", "search file budget.xlsx", "locate invoice"]},
    {"label": "Open File",         "category": "Files",     "examples": ["open file 1", "open file 2"]},
    # ── Memory ───────────────────────────────────────────────────────────────
    {"label": "Remember Fact",     "category": "Memory",    "examples": ["remember my name is Alex", "remember that I like Python", "remember I work at Google"]},
    {"label": "Show Memory",       "category": "Memory",    "examples": ["show memory", "what do you remember", "recall all facts"]},
    # ── Clipboard ────────────────────────────────────────────────────────────
    {"label": "Read Clipboard",    "category": "Clipboard", "examples": ["read clipboard", "what's in my clipboard"]},
    # ── Web ──────────────────────────────────────────────────────────────────
    {"label": "Web Search",        "category": "Web",       "examples": ["search for python tutorials", "look up AI news", "google quantum computing", "web search latest tech"]},
    {"label": "Weather",           "category": "Web",       "examples": ["weather in London", "temperature in Tokyo", "weather in New York", "forecast for Mumbai"]},
    # ── Navigation ───────────────────────────────────────────────────────────
    {"label": "Active Window",     "category": "Navigate",  "examples": ["what window is open", "current window", "where am i"]},
    {"label": "List Windows",      "category": "Navigate",  "examples": ["list open windows", "show all windows"]},
    {"label": "Switch Window",     "category": "Navigate",  "examples": ["next window", "switch to next window"]},
    # ── Chat ─────────────────────────────────────────────────────────────────
    {"label": "New Chat",          "category": "Chat",      "examples": ["new chat", "start new conversation", "clear chat"]},
    {"label": "Ask AI",            "category": "Chat",      "examples": ["explain quantum computing", "write a poem", "what is machine learning"]},
]

CATEGORY_COLORS = {
    "System":    "#7c3aed",
    "Screen":    "#0ea5e9",
    "Info":      "#10b981",
    "Scheduler": "#f59e0b",
    "Files":     "#f97316",
    "Memory":    "#ec4899",
    "Clipboard": "#06b6d4",
    "Web":       "#06b6d4",
    "Navigate":  "#a78bfa",
    "Chat":      "#3fb950",
}


class CommandPalette(QDialog):
    """
    Floating command palette overlay.
    Emits command_selected(text) when the user picks a command.
    The parent (AssistantUI) connects this signal to send_message().
    """

    command_selected = Signal(str)   # emits the command text to execute

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("")
        self.setModal(True)
        self.setFixedWidth(620)
        self.setWindowFlags(
            Qt.Dialog |
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._all_items = []   # (command_dict, QListWidgetItem)
        self._build_ui()

    # ── UI Construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Main card ─────────────────────────────────────────────────────────
        card = QFrame()
        card.setObjectName("paletteCard")
        card.setStyleSheet("""
            QFrame#paletteCard {
                background-color: #13161d;
                border: 1px solid #7c3aed66;
                border-radius: 16px;
            }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 12)
        card_layout.setSpacing(0)

        # ── Search bar ────────────────────────────────────────────────────────
        search_frame = QFrame()
        search_frame.setStyleSheet("""
            QFrame {
                background-color: #161b22;
                border-bottom: 1px solid #21262d;
                border-top-left-radius: 16px;
                border-top-right-radius: 16px;
            }
        """)
        search_frame.setFixedHeight(56)
        search_h = QHBoxLayout(search_frame)
        search_h.setContentsMargins(18, 0, 18, 0)
        search_h.setSpacing(10)

        icon = QLabel("⌘")
        icon.setStyleSheet("color: #7c3aed; font-size: 18px; background: transparent;")
        search_h.addWidget(icon)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "Type a command… (e.g. open chrome, weather in London, remind me)"
        )
        self.search_input.setStyleSheet("""
            QLineEdit {
                background: transparent;
                color: #e6edf3;
                border: none;
                font-size: 15px;
                font-family: "Segoe UI", sans-serif;
                padding: 0;
            }
        """)
        self.search_input.textChanged.connect(self._filter)
        self.search_input.returnPressed.connect(self._execute_selected)
        search_h.addWidget(self.search_input)

        esc_lbl = QLabel("Esc to close")
        esc_lbl.setStyleSheet("color: #484f58; font-size: 10px; background: transparent;")
        search_h.addWidget(esc_lbl)

        card_layout.addWidget(search_frame)

        # ── Results list ──────────────────────────────────────────────────────
        self.results = QListWidget()
        self.results.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.results.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.results.setMaximumHeight(380)
        self.results.setStyleSheet("""
            QListWidget {
                background: transparent;
                border: none;
                outline: none;
                padding: 6px 10px;
            }
            QListWidget::item {
                border-radius: 8px;
                padding: 0;
                margin: 2px 0;
            }
            QListWidget::item:selected {
                background-color: #1c1029;
                border: 1px solid #7c3aed44;
            }
            QListWidget::item:hover:!selected {
                background-color: #161b22;
            }
        """)
        self.results.itemActivated.connect(self._on_item_activated)
        self.results.itemClicked.connect(self._on_item_activated)
        card_layout.addWidget(self.results)

        # ── Footer hint ───────────────────────────────────────────────────────
        footer = QLabel("↑↓ navigate  ·  Enter execute  ·  Ctrl+Space toggle")
        footer.setAlignment(Qt.AlignCenter)
        footer.setStyleSheet("color: #30363d; font-size: 10px; padding: 4px 0;")
        card_layout.addWidget(footer)

        outer.addWidget(card)

        # ── Populate all commands ─────────────────────────────────────────────
        self._populate_all()
        self._filter("")

    def _make_item_widget(self, cmd: dict) -> QFrame:
        """Build the rich widget for one command row."""
        cat     = cmd["category"]
        color   = CATEGORY_COLORS.get(cat, "#7c3aed")
        example = cmd["examples"][0] if cmd["examples"] else ""

        frame = QFrame()
        frame.setFixedHeight(52)
        frame.setStyleSheet("background: transparent;")

        h = QHBoxLayout(frame)
        h.setContentsMargins(8, 0, 12, 0)
        h.setSpacing(10)

        # Category badge
        badge = QLabel(f" {cat} ")
        badge.setFixedHeight(18)
        badge.setStyleSheet(f"""
            QLabel {{
                background-color: {color}22;
                color: {color};
                border: 1px solid {color}44;
                border-radius: 4px;
                font-size: 9px;
                font-weight: 600;
                padding: 0 5px;
            }}
        """)

        # Main label
        name_lbl = QLabel(cmd["label"])
        name_lbl.setStyleSheet("color: #e6edf3; font-size: 13px; font-weight: 600; background: transparent;")

        # Example chip
        chip = QLabel(f'"{example}"')
        chip.setStyleSheet(f"""
            QLabel {{
                color: {color};
                background-color: transparent;
                font-size: 11px;
                font-family: 'Consolas', monospace;
            }}
        """)

        v = QVBoxLayout()
        v.setSpacing(2)
        v.setContentsMargins(0, 0, 0, 0)
        top_h = QHBoxLayout()
        top_h.setSpacing(8)
        top_h.addWidget(name_lbl)
        top_h.addWidget(badge)
        top_h.addStretch()
        v.addLayout(top_h)
        v.addWidget(chip)

        h.addLayout(v)

        return frame

    def _populate_all(self):
        """Add all commands to the list once."""
        self._all_items.clear()
        self.results.clear()
        for cmd in PALETTE_COMMANDS:
            item = QListWidgetItem()
            item.setSizeHint(__import__('PySide6.QtCore', fromlist=['QSize']).QSize(600, 54))
            item.setData(Qt.UserRole, cmd)
            self.results.addItem(item)
            widget = self._make_item_widget(cmd)
            self.results.setItemWidget(item, widget)
            self._all_items.append((cmd, item))

        if self.results.count():
            self.results.setCurrentRow(0)

    # ── Filtering ─────────────────────────────────────────────────────────────

    def _filter(self, query: str):
        q = query.strip().lower()
        first_visible = None

        for cmd, item in self._all_items:
            haystack = (
                cmd["label"] + " " +
                cmd["category"] + " " +
                " ".join(cmd["examples"])
            ).lower()

            visible = (not q) or (q in haystack)
            item.setHidden(not visible)

            if visible and first_visible is None:
                first_visible = item

        if first_visible:
            self.results.setCurrentItem(first_visible)

    # ── Keyboard navigation ───────────────────────────────────────────────────

    def keyPressEvent(self, event):
        key = event.key()

        if key == Qt.Key_Escape:
            self.close()
            return

        if key in (Qt.Key_Down, Qt.Key_Up):
            # Move selection through visible items
            visible = [item for _, item in self._all_items if not item.isHidden()]
            if not visible:
                return
            current = self.results.currentItem()
            try:
                idx = visible.index(current)
            except ValueError:
                idx = -1

            if key == Qt.Key_Down:
                idx = min(idx + 1, len(visible) - 1)
            else:
                idx = max(idx - 1, 0)
            self.results.setCurrentItem(visible[idx])
            self.results.scrollToItem(visible[idx])
            return

        if key == Qt.Key_Return:
            self._execute_selected()
            return

        super().keyPressEvent(event)

    # ── Execution ─────────────────────────────────────────────────────────────

    def _on_item_activated(self, item):
        cmd = item.data(Qt.UserRole)
        if cmd:
            text = cmd["examples"][0]
            # If user typed something custom, use that instead
            typed = self.search_input.text().strip()
            if typed and not any(
                typed.lower() == ex.lower() for ex in cmd["examples"]
            ):
                text = typed
            self.command_selected.emit(text)
            self.close()

    def _execute_selected(self):
        # If there's custom text that doesn't match any command, send it as-is
        typed = self.search_input.text().strip()
        item  = self.results.currentItem()

        if item and not item.isHidden():
            cmd = item.data(Qt.UserRole)
            text = typed if typed else cmd["examples"][0]
            self.command_selected.emit(text)
        elif typed:
            self.command_selected.emit(typed)

        self.close()

    # ── Show / position ───────────────────────────────────────────────────────

    def show_centered(self, parent_widget=None):
        """Show the palette centered on the parent window (or screen)."""
        self.search_input.clear()
        self._filter("")
        self.search_input.setFocus()

        if parent_widget:
            geo = parent_widget.geometry()
            x   = geo.x() + (geo.width()  - self.width())  // 2
            y   = geo.y() + (geo.height() - self.height()) // 2 - 60
            self.move(x, y)
        else:
            screen = QApplication.primaryScreen().geometry()
            self.move(
                (screen.width()  - self.width())  // 2,
                (screen.height() - self.height()) // 2 - 60,
            )

        self.show()
        self.raise_()
        self.activateWindow()


# ── Mixin: adds the palette + Ctrl+Space hotkey to AssistantUI ────────────────

class CommandPaletteMixin:
    """
    Mix this into AssistantUI to get Ctrl+Space command palette support.

    Call self._init_command_palette() inside build_ui(), AFTER
    the rest of the UI is set up.
    """

    def _init_command_palette(self):
        self._palette = CommandPalette(self)
        self._palette.command_selected.connect(self._on_palette_command)

        # Ctrl+Space global shortcut
        shortcut = QShortcut(QKeySequence("Ctrl+Space"), self)
        shortcut.activated.connect(self._open_palette)
        shortcut.setContext(Qt.ApplicationShortcut)

    def _open_palette(self):
        if self._palette.isVisible():
            self._palette.close()
        else:
            self._palette.show_centered(self)

    def _on_palette_command(self, text: str):
        """Paste the command into the input box and execute it."""
        # Switch to Chat page
        self.sidebar.setCurrentRow(0)
        # Set input and fire
        self.input_box.setText(text)
        self.send_message()