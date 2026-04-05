from tools.system_tools import open_app as _sys_open_app
from core.run_python import run_python_script
from services.memory_service import (
    save_memory,
    load_memory
)

from services.conversation_service import clear_history

import tools.file_tools
from tools.registry import registry
from tools.system_info_tools import get_system_info



from services.scheduler_service import (
    schedule_in_minutes,
    schedule_in_seconds,
    schedule_script_at,
    schedule_every_minutes,
    schedule_every_day,
    list_tasks,
    cancel_task,
    cancel_all_tasks,
    pause_task,
    resume_task
)

from tools.time_tools import (
    get_current_time,
    get_current_date
)

import os
import shutil



# ---------- OPEN APP TOOL ----------

def open_app_tool(text):

    text = text.lower()

    keywords = [
        "open",
        "launch",
        "start"
    ]

    app = None

    for word in keywords:

        if word in text:

            parts = text.split(word, 1)

            app = parts[1].strip()

            break

    if not app:

        return "Please specify an application"

    return _sys_open_app(text)


# ---------- REMEMBER TOOL ----------

def remember_tool(text):

    data = text.lower().replace(
        "remember",
        "",
        1
    ).strip()

    if data.startswith("that"):

        data = data.replace(
            "that",
            "",
            1
        ).strip()

    if " is " in data:

        key, value = data.split(
            " is ",
            1
        )

        save_memory(
            key.strip(),
            value.strip()
        )

        return "Saved to memory"

    elif " am " in data:

        key, value = data.split(
            " am ",
            1
        )

        save_memory(
            key.strip(),
            value.strip()
        )

        return "Saved to memory"

    else:

        save_memory(
            data,
            "true"
        )

        return "Saved to memory"


# ---------- SHOW MEMORY TOOL ----------

def show_memory_tool(text):

    memory_data = load_memory()

    if not memory_data:

        return "Memory is empty"

    lines = []

    for k, v in memory_data.items():

        lines.append(
            f"{k}: {v}"
        )

    return "\n".join(lines)


# ---------- CLEAR CONVERSATION TOOL ----------

def clear_conversation_tool(text):

    return clear_history()


# ---------- FILE SEARCH TOOL ----------

def search_file_tool(text):

    keywords = [
        "find",
        "search",
        "locate"
    ]

    query = text.lower()

    for word in keywords:

        if word in query:

            parts = query.split(word, 1)

            query = parts[1].strip()

            break

    if not query:

        return "Please specify what to search for"

    results = tools.file_tools.search_files(query)

    if not results:

        return "No files found"

    numbered = []

    for i, path in enumerate(results, start=1):

        numbered.append(
            f"{i}. {path}"
        )

    return "\n".join(numbered)


# ---------- OPEN FILE TOOL ----------

def open_file_tool(text):

    text = text.lower()

    if "file" in text:

        parts = text.split()

        for word in parts:

            if word.isdigit():

                index = int(word) - 1

                results = tools.file_tools.last_search_results

                if 0 <= index < len(results):

                    path = results[index]

                    os.startfile(path)

                    return f"Opening {path}"

                return "Invalid file number"

    return "File not found"


# ---------- SYSTEM INFO TOOL ----------

def system_info_tool(text):

    return get_system_info()


# ---------- RUN PYTHON TOOL ----------

def run_python_tool(text):

    text = text.lower()

    if "file" in text:

        parts = text.split()

        for word in parts:

            if word.isdigit():

                index = int(word) - 1

                results = tools.file_tools.last_search_results

                if 0 <= index < len(results):

                    path = results[index]

                    return run_python_script(path)

                return "Invalid file number"

    keywords = [
        "run script",
        "run python",
        "run file",
        "execute"
    ]

    script = text

    for word in keywords:

        if word in script:

            parts = script.split(word, 1)

            script = parts[1].strip()

            break

    return run_python_script(script)


# ---------- FILE OPERATION TOOL ----------

def file_operation_tool(text):

    text = text.lower()

    results = tools.file_tools.last_search_results

    parts = text.split()

    file_index = None

    for word in parts:

        if word.isdigit():

            file_index = int(word) - 1

            break

    if file_index is None:

        return "Please specify file number"

    if not (0 <= file_index < len(results)):

        return "Invalid file number"

    source = results[file_index]

    # COPY

    if "copy" in text:

        if "desktop" in text:

            destination = os.path.join(
                os.path.expanduser("~"),
                "Desktop"
            )

        elif "documents" in text:

            destination = os.path.join(
                os.path.expanduser("~"),
                "Documents"
            )

        elif "downloads" in text:

            destination = os.path.join(
                os.path.expanduser("~"),
                "Downloads"
            )

        else:

            return "Unknown destination"

        shutil.copy(source, destination)

        return f"Copied to {destination}"

    # MOVE

    if "move" in text:

        destination = os.path.join(
            os.path.expanduser("~"),
            "Desktop"
        )

        shutil.move(source, destination)

        return f"Moved to {destination}"

    # DELETE

    if "delete" in text:

        os.remove(source)

        return "File deleted"

    return "Unknown file operation"


# ---------- SCHEDULER TOOL ----------

def schedule_task_tool(text):

    text = text.lower()

    parts = text.split()

    # every X minutes

    if "every" in text and "minutes" in text:

        for word in parts:

            if word.isdigit():

                return schedule_every_minutes(
                    int(word),
                    text
                )

    # every day

    if "every day" in text and "at" in text:

        for word in parts:

            if ":" in word:

                return schedule_every_day(
                    word,
                    text
                )

    # seconds

    if "seconds" in text:

        for word in parts:

            if word.isdigit():

                return schedule_in_seconds(
                    int(word),
                    text
                )

    # minutes

    if "minutes" in text:

        for word in parts:

            if word.isdigit():

                return schedule_in_minutes(
                    int(word),
                    text
                )

    # run at time

    if "at" in text:

        for word in parts:

            if ":" in word:

                return schedule_script_at(
                    word,
                    text
                )

        return "Invalid time format. Use HH:MM"

    return "Could not schedule task"


# ---------- TIME TOOL ----------

def get_time_tool(text):

    return get_current_time()


# ---------- DATE TOOL ----------

def get_date_tool(text):

    return get_current_date()


# ---------- TASK MANAGEMENT TOOL ----------

def task_management_tool(text):

    text = text.lower()

    if "show tasks" in text:

        return list_tasks()

    if "pause task" in text:

        parts = text.split()

        for word in parts:

            if word.isdigit():

                index = int(word) - 1

                return pause_task(index)

        return "Please specify task number"

    if "resume task" in text:

        parts = text.split()

        for word in parts:

            if word.isdigit():

                index = int(word) - 1

                return resume_task(index)

        return "Please specify task number"

    if "cancel all tasks" in text:

        return cancel_all_tasks()

    if "cancel task" in text:

        parts = text.split()

        for word in parts:

            if word.isdigit():

                index = int(word) - 1

                return cancel_task(index)

        return "Please specify task number"

    return "Unknown task command"


# ---------- REGISTER TOOLS ----------

registry.register("open_app", open_app_tool)

registry.register("remember", remember_tool)

registry.register("show_memory", show_memory_tool)

registry.register("clear_conversation", clear_conversation_tool)

registry.register("search_file", search_file_tool)

registry.register("open_file", open_file_tool)

registry.register("system_info", system_info_tool)

registry.register("run_python", run_python_tool)

registry.register("file_operation", file_operation_tool)

registry.register("schedule_task", schedule_task_tool)

registry.register("get_time", get_time_tool)

registry.register("get_date", get_date_tool)

registry.register("task_management", task_management_tool)

# ---------- SCREEN READER TOOLS ----------

from tools.screen_tools import (
    read_screen,
    screenshot_to_file,
    last_screen_text
)

def setup_tools():

    registry.register(...)

def read_screen_tool(text: str) -> str:
    text_lower = text.lower()
    REGIONS = {
        "top left":     (0,    0,    960, 540),
        "top right":    (960,  0,    960, 540),
        "bottom left":  (0,    540,  960, 540),
        "bottom right": (960,  540,  960, 540),
        "center":       (480,  270,  960, 540),
        "top half":     (0,    0,    1920, 540),
        "bottom half":  (0,    540,  1920, 540),
        "left half":    (0,    0,    960, 1080),
        "right half":   (960,  0,    960, 1080),
    }
    for label, region in REGIONS.items():
        if label in text_lower:
            return f"[{label.title()} region]\n\n{read_screen(region=region)}"
    result = read_screen()
    return "No text detected on screen." if not result else f"[Full screen]\n\n{result}"


def screenshot_tool(text: str) -> str:
    path = screenshot_to_file()
    if path.startswith(("Screenshot failed", "Pillow", "pytesseract")):
        return path
    return f"Screenshot saved to:\n{path}"


def last_screen_tool(text: str) -> str:
    return last_screen_text()


registry.register("read_screen", read_screen_tool)
registry.register("screenshot",  screenshot_tool)
registry.register("last_screen", last_screen_tool)


# ---------- ACCESSIBILITY / SCREEN EXPLANATION / NAV TOOLS ----------

from tools.screen_tools import explain_screen, read_handwriting as _read_handwriting
from services.accessibility_service import AccessibilityEngine
from services.tts_service import speak_async as _speak_async, stop as _stop_tts

_acc = AccessibilityEngine(speak_fn=_speak_async, stop_fn=_stop_tts)


def explain_screen_tool(text: str) -> str:
    question = text.lower()
    for prefix in ("explain screen", "explain my screen", "describe screen",
                   "describe my screen", "what is on my screen", "what's on my screen",
                   "whats on my screen", "what do you see on screen",
                   "tell me what's on screen", "tell me what is on screen",
                   "what app is open", "what application is open",
                   "what window is open", "what am i looking at",
                   "describe what you see", "explain what you see"):
        if question.startswith(prefix):
            question = question[len(prefix):].strip()
            break
    return explain_screen(question=question or "")


def read_handwriting_tool(text: str) -> str:
    # Extract a file path from the command if present
    import re
    match = re.search(r'["\']?([a-zA-Z]:\\[^\'"]+|/[^\'"]+\.[a-zA-Z]{2,5})["\']?', text)
    if match:
        return _read_handwriting(match.group(1))
    return "Please provide a path to the image file, e.g. 'read handwriting C:\\scans\\page1.png'"


def nav_focus_tool(text: str) -> str:
    return _acc.get_focused_element()


def nav_title_tool(text: str) -> str:
    return _acc.get_active_window_title()


def nav_windows_tool(text: str) -> str:
    return _acc.list_open_windows()


def nav_clipboard_tool(text: str) -> str:
    return _acc.read_clipboard()


def nav_auto_tool(text: str) -> str:
    return _acc.toggle_auto_announce()


def nav_next_window_tool(text: str) -> str:
    return _acc.switch_to_next_window()


def nav_prev_window_tool(text: str) -> str:
    return _acc.switch_to_prev_window()


registry.register("explain_screen",   explain_screen_tool)
registry.register("read_handwriting",  read_handwriting_tool)
registry.register("nav_focus",         nav_focus_tool)
registry.register("nav_title",         nav_title_tool)
registry.register("nav_windows",       nav_windows_tool)
registry.register("nav_clipboard",     nav_clipboard_tool)
registry.register("nav_auto",          nav_auto_tool)
registry.register("nav_next_window",   nav_next_window_tool)
registry.register("nav_prev_window",   nav_prev_window_tool)