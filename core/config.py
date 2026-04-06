import json
import os
import sys
from threading import Lock
from typing import Any

_config_lock = Lock()

CONFIG_FILE_NAME = "data/config/config.json"


# ---------- RESOURCE PATH ----------

def resource_path(filename: str) -> str:

    if getattr(sys, "frozen", False):

        base = os.path.dirname(sys.executable)

    else:

        base = os.getcwd()

    return os.path.join(base, filename)


# ---------- DEFAULT SETTINGS ----------

DEFAULT_CONFIG = {
    "model": "qwen2.5:3b",
    "auto_start": False,
    "theme": "dark",
    "notifications": True,
    "max_history": 20,
    "window_minimize_to_tray": True
}


def get_config_file() -> str:

    return resource_path(CONFIG_FILE_NAME)


# ---------- ENSURE CONFIG EXISTS ----------

def _ensure_config_exists() -> None:

    config_file = get_config_file()

    if not os.path.exists(config_file):

        with open(config_file, "w") as f:

            json.dump(
                DEFAULT_CONFIG,
                f,
                indent=2
            )


# ---------- LOAD CONFIG ----------

def load_config() -> dict:

    _ensure_config_exists()

    config_file = get_config_file()

    try:

        with _config_lock:

            with open(config_file, "r") as f:

                data = json.load(f)

                updated = False

                for key, value in DEFAULT_CONFIG.items():

                    if key not in data:

                        data[key] = value
                        updated = True

                if updated:

                    save_config(data)

                return data

    except Exception:

        return DEFAULT_CONFIG.copy()


# ---------- SAVE CONFIG ----------

def save_config(config: dict) -> None:

    config_file = get_config_file()

    with _config_lock:

        with open(config_file, "w") as f:

            json.dump(
                config,
                f,
                indent=2
            )


# ---------- GET SETTING ----------

def get_setting(key: str) -> Any:

    config = load_config()

    return config.get(key)


# ---------- SET SETTING ----------

def set_setting(key: str, value: Any) -> bool:

    config = load_config()

    config[key] = value

    save_config(config)

    return True


# ---------- RESET CONFIG ----------

def reset_config() -> bool:

    config_file = get_config_file()

    with _config_lock:

        with open(config_file, "w") as f:

            json.dump(
                DEFAULT_CONFIG,
                f,
                indent=2
            )

    return True


# ---------- LIST SETTINGS ----------

def list_settings() -> str:

    config = load_config()

    lines = []

    for key, value in config.items():

        lines.append(
            f"{key}: {value}"
        )

    return "\n".join(lines)


# ---------- DELETE SETTING ----------

def delete_setting(key: str) -> bool:

    config = load_config()

    if key in config:

        del config[key]

        save_config(config)

        return True

    return False


# ---------- CHECK BOOLEAN ----------

def is_enabled(key: str) -> bool:

    value = get_setting(key)

    return bool(value)


# ---------- TOGGLE BOOLEAN ----------

def toggle_setting(key: str) -> bool:

    config = load_config()

    current = config.get(key, False)

    config[key] = not current

    save_config(config)

    return config[key]