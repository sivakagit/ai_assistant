import time
import threading
import psutil
import requests

from core.logger import get_logger
from services.scheduler_service import list_tasks
from services.scheduler_service import is_scheduler_running
from core.config import get_setting

logger = get_logger()

_start_time = time.time()

_error_count = 0

_memory_history = []


# ---------- ERROR COUNTER ----------

def increment_error_count():

    global _error_count

    _error_count += 1


def get_error_count():

    return _error_count


# ---------- UPTIME ----------

def get_uptime():

    seconds = int(
        time.time() - _start_time
    )

    minutes = seconds // 60

    return f"{minutes} minutes"


# ---------- SYSTEM STATS ----------

def get_thread_count():

    return threading.active_count()


def get_memory_usage():

    process = psutil.Process()

    memory = process.memory_info()

    return memory.rss / (1024 * 1024)


def get_cpu_usage():

    return psutil.cpu_percent()


def update_memory_history():

    memory = get_memory_usage()

    _memory_history.append(memory)

    if len(_memory_history) > 60:

        _memory_history.pop(0)

    return list(_memory_history)


# ---------- SERVICE STATUS ----------

def get_scheduler_status():

    try:

        return is_scheduler_running()

    except Exception:

        return False


def get_ollama_status():

    try:

        response = requests.get(
            "http://localhost:11434/api/tags",
            timeout=1
        )

        if response.status_code == 200:

            return "Running"

        return "Unavailable"

    except Exception:

        return "Stopped"


def get_model_status():

    try:

        model = get_setting("model")

        if not model:

            return "None"

        return model

    except Exception:

        return "Unknown"


# ---------- FULL SNAPSHOT ----------

def get_health_snapshot():

    try:

        memory = get_memory_usage()

        cpu = get_cpu_usage()

        threads = get_thread_count()

        scheduler = get_scheduler_status()

        ollama = get_ollama_status()

        model = get_model_status()

        errors = get_error_count()

        tasks = list_tasks()

        trend = update_memory_history()

        return {

            "cpu": cpu,

            "memory": memory,

            "memory_trend": trend,

            "threads": threads,

            "scheduler": scheduler,

            "ollama": ollama,

            "model": model,

            "uptime": get_uptime(),

            "errors": errors,

            "tasks": tasks

        }

    except Exception:

        logger.exception(
            "Health snapshot failed"
        )

        return None