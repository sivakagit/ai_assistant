import json
import os
from datetime import datetime

from core.config import resource_path
from core.logger import get_logger

logger = get_logger()

STATE_FILE = resource_path("runtime_state.json")


def _default_state():

    return {
        "last_shutdown_clean": True,
        "last_start_time": None,
        "last_shutdown_time": None,
    }


def load_state():

    if not os.path.exists(STATE_FILE):

        return _default_state()

    try:

        with open(STATE_FILE, "r") as f:

            return json.load(f)

    except Exception:

        logger.exception("Failed to read runtime state")

        return _default_state()


def save_state(state):

    try:

        with open(STATE_FILE, "w") as f:

            json.dump(state, f, indent=2)

    except Exception:

        logger.exception("Failed to save runtime state")


def mark_startup():

    state = load_state()

    crashed = not state.get("last_shutdown_clean", True)

    state["last_shutdown_clean"] = False
    state["last_start_time"] = datetime.now().isoformat()

    save_state(state)

    if crashed:

        logger.warning("Previous shutdown was not clean")

        return True

    return False


def mark_clean_shutdown():

    state = load_state()

    state["last_shutdown_clean"] = True
    state["last_shutdown_time"] = datetime.now().isoformat()

    save_state(state)

    logger.info("Clean shutdown recorded")