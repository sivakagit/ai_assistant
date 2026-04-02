import winreg
import sys
import os

APP_NAME = "Assistant"


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

        winreg.SetValueEx(
            key,
            APP_NAME,
            0,
            winreg.REG_SZ,
            exe_path
        )

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

        winreg.DeleteValue(
            key,
            APP_NAME
        )

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

        winreg.QueryValueEx(
            key,
            APP_NAME
        )

        winreg.CloseKey(key)

        return True

    except FileNotFoundError:

        return False