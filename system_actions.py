import os
import subprocess


# ---------- APP NAME → PROCESS / EXECUTABLE MAP ----------

APP_MAP = {
    "chrome":      {"exe": "chrome.exe",     "launch": r"C:\Program Files\Google\Chrome\Application\chrome.exe"},
    "notepad":     {"exe": "notepad.exe",     "launch": "notepad"},
    "calculator":  {"exe": "CalculatorApp.exe", "launch": "calc"},
    "calc":        {"exe": "CalculatorApp.exe", "launch": "calc"},
    "paint":       {"exe": "mspaint.exe",     "launch": "mspaint"},
    "explorer":    {"exe": "explorer.exe",    "launch": "explorer"},
    "word":        {"exe": "WINWORD.EXE",     "launch": "winword"},
    "excel":       {"exe": "EXCEL.EXE",       "launch": "excel"},
    "vlc":         {"exe": "vlc.exe",         "launch": "vlc"},
    "spotify":     {"exe": "Spotify.exe",     "launch": "spotify"},
    "discord":     {"exe": "Discord.exe",     "launch": "discord"},
    "vscode":      {"exe": "Code.exe",        "launch": "code"},
    "vs code":     {"exe": "Code.exe",        "launch": "code"},
    "task manager":{"exe": "Taskmgr.exe",     "launch": "taskmgr"},
}


def _resolve_app_name(text: str):
    """Return the APP_MAP key that appears in text, or None."""
    text = text.lower()
    for key in APP_MAP:
        if key in text:
            return key
    return None


# ---------- OPEN APP ----------

def open_app(user_input: str) -> str:
    """
    Open an application by name extracted from user_input.
    Falls back to ShellExecute so Windows can resolve the name itself.
    """
    key = _resolve_app_name(user_input)

    if key:
        # For Chrome, try multiple known install paths
        if key == "chrome":
            chrome_paths = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
            ]
            for path in chrome_paths:
                if os.path.exists(path):
                    try:
                        subprocess.Popen([path], shell=False)
                        return "Opening Chrome"
                    except Exception as e:
                        return f"Failed to open Chrome: {e}"
            # Last resort: shell command
            try:
                subprocess.Popen("start chrome", shell=True)
                return "Opening Chrome"
            except Exception as e:
                return f"Chrome not found. Please check if it is installed: {e}"

        launch = APP_MAP[key]["launch"]
        try:
            subprocess.Popen(launch, shell=True)
            return f"Opening {key}"
        except Exception as e:
            return f"Failed to open {key}: {e}"

    # Generic fallback — try to shell-execute whatever word follows open/launch/start
    words = user_input.lower().split()
    for trigger in ("open", "launch", "start"):
        if trigger in words:
            idx = words.index(trigger)
            if idx + 1 < len(words):
                app_word = words[idx + 1]
                try:
                    subprocess.Popen(app_word, shell=True)
                    return f"Trying to open '{app_word}'"
                except Exception as e:
                    return f"Could not open '{app_word}': {e}"

    return "I don't know which app to open. Please be more specific."


# ---------- CLOSE EXTERNAL APP ----------

def close_external_app(user_input: str) -> str:
    """
    Close a running application by killing its process.
    """
    key = _resolve_app_name(user_input)

    if key:
        exe = APP_MAP[key]["exe"]
        result = subprocess.run(
            ["taskkill", "/IM", exe, "/F"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            return f"Closed {key}"
        else:
            return f"{key} is not running or could not be closed."

    # Generic fallback
    words = user_input.lower().split()
    for trigger in ("close", "kill", "quit", "exit"):
        if trigger in words:
            idx = words.index(trigger)
            if idx + 1 < len(words):
                app_word = words[idx + 1]
                exe_guess = app_word if app_word.endswith(".exe") else app_word + ".exe"
                result = subprocess.run(
                    ["taskkill", "/IM", exe_guess, "/F"],
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0:
                    return f"Closed '{app_word}'"
                else:
                    return f"'{app_word}' is not running or could not be closed."

    return "I don't know which app to close. Please be more specific."


# ---------- CLOSE ASSISTANT ----------

def close_app():
    """Exits the assistant itself."""
    print("Closing assistant")
    os._exit(0)


# ---------- SYSTEM POWER ----------

def shutdown_pc():
    subprocess.run(["shutdown", "/s", "/t", "0"], shell=False)


def restart_pc():
    subprocess.run(["shutdown", "/r", "/t", "0"], shell=False)


# ---------- KILL PROCESS BY NAME ----------

def kill_process(process_name: str) -> str:
    if not process_name:
        return "Process name required"
    subprocess.run(["taskkill", "/IM", process_name, "/F"], shell=False)
    return f"Process '{process_name}' terminated"