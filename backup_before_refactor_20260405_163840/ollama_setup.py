import subprocess
import shutil
import time
import os
import socket


DEFAULT_MODEL = "qwen2.5:3b"


# ---------- FIND OLLAMA ----------

def get_ollama_path():

    path = shutil.which("ollama")

    if path:
        return path

    default = r"C:\Program Files\Ollama\ollama.exe"

    if os.path.exists(default):
        return default

    return None


# ---------- CHECK IF SERVICE RUNNING ----------

def is_ollama_running():

    try:

        sock = socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM
        )

        sock.settimeout(1)  # ← FIX: without this, connect_ex can hang indefinitely

        result = sock.connect_ex(
            ("127.0.0.1", 11434)
        )

        sock.close()

        return result == 0

    except Exception:

        return False


# ---------- START SERVICE ----------

def start_ollama_service():

    ollama = get_ollama_path()

    if not ollama:

        print("Ollama not found")

        return False

    try:

        subprocess.Popen(
            [ollama, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

    except Exception as e:

        print("Failed to start Ollama:", e)

        return False

    # Wait up to 15 seconds

    for _ in range(15):

        if is_ollama_running():

            return True

        time.sleep(1)

    return False


# ---------- MAIN ENTRY ----------

def ensure_ollama_ready(model=DEFAULT_MODEL):

    print("Checking Ollama...")

    if not get_ollama_path():

        print("Ollama not installed")

        return False

    if is_ollama_running():

        print("Ollama already running")

        return True

    print("Starting Ollama service...")

    started = start_ollama_service()

    if not started:

        print("Failed to start Ollama")

        return False

    return True