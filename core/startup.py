import winreg
import sys
import os

import signal
from core.shutdown_manager import shutdown
from core.shutdown_manager import register_shutdown_hook
from services.scheduler_service import stop_scheduler
from services.memory_service import save_memory
from services.tts_service import stop
from core.logger import get_logger
from services.scheduler_service import start_scheduler
logger = get_logger()

APP_NAME = "Assistant"


def main():

    from PySide6.QtWidgets import QApplication
    from ui.main_window import AssistantUI

    logger.info("Assistant starting")

    # Create QApplication FIRST
    app = QApplication(sys.argv)

    # Register shutdown hooks
    register_shutdown_hook(stop_scheduler)
    register_shutdown_hook(save_memory)
    register_shutdown_hook(stop)

    # Register system signals
    signal.signal(signal.SIGINT, lambda s, f: shutdown())
    signal.signal(signal.SIGTERM, lambda s, f: shutdown())

    # Start background services
    start_scheduler()

    # Start UI
    window = AssistantUI()
    window.show()

    logger.info("Assistant UI started")

    sys.exit(app.exec())

def get_executable_path():
    if getattr(sys, "frozen", False):
        return sys.executable
    return os.path.abspath(sys.argv[0])


def enable_auto_start():
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE
        )
        exe_path = get_executable_path()
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, exe_path)
        winreg.CloseKey(key)
        print("Auto-start enabled")
        return True
    except Exception as e:
        print("Auto-start error:", e)
        return False


def disable_auto_start():
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE
        )
        winreg.DeleteValue(key, APP_NAME)
        winreg.CloseKey(key)
        print("Auto-start disabled")
        return True
    except FileNotFoundError:
        return False
    except Exception as e:
        print("Disable error:", e)
        return False


def is_auto_start_enabled():
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run"
        )
        winreg.QueryValueEx(key, APP_NAME)
        winreg.CloseKey(key)
        return True
    except FileNotFoundError:
        return False