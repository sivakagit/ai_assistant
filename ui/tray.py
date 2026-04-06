import os

from PySide6.QtWidgets import (
    QSystemTrayIcon,
    QMenu,
    QApplication,
    QStyle
)

from PySide6.QtGui import (
    QIcon,
    QAction
)


class TrayManager:

    def __init__(self, window):

        self.window = window

        if not QSystemTrayIcon.isSystemTrayAvailable():

            print("System tray NOT available")

            return

        print("System tray available")

        self.tray_icon = QSystemTrayIcon()

        icon = self.load_icon()

        self.tray_icon.setIcon(icon)

        try:
            from core.config import get_setting
            hotkey = get_setting("global_hotkey") or "ctrl+shift+space"
            self.tray_icon.setToolTip(f"Nova AI  •  {hotkey.upper()} to toggle")
        except Exception:
            self.tray_icon.setToolTip("Nova AI")

        self.menu = QMenu()

        show_action = QAction(
            "Open Assistant",
            window
        )

        exit_action = QAction(
            "Exit",
            window
        )

        show_action.triggered.connect(
            self.show_window
        )

        exit_action.triggered.connect(
            self.exit_app
        )

        self.menu.addAction(show_action)

        self.menu.addSeparator()

        self.menu.addAction(exit_action)

        self.tray_icon.setContextMenu(
            self.menu
        )

        self.tray_icon.activated.connect(
            self.on_click
        )

        self.tray_icon.show()

        print("Tray icon created")

    def load_icon(self):

        icon_path = "app_icon.ico"

        if os.path.exists(icon_path):

            print("Using icon:", icon_path)

            return QIcon(icon_path)

        print("Using default system icon")

        return QApplication.style().standardIcon(
            QStyle.SP_ComputerIcon
        )

    def on_click(self, reason):

        if reason == QSystemTrayIcon.DoubleClick:

            self.show_window()

    def show_window(self):

        print("Tray → show window")

        self.window.show()

        self.window.raise_()

        self.window.activateWindow()

    def exit_app(self):

        print("Tray → exit")

        self.tray_icon.hide()

        QApplication.quit()