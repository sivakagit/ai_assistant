def detect_intent(text):
    """
    Detect intent from user text.
    Returns: (intent: str, confidence: float)
    confidence ranges from 0.0 (unknown) to 1.0 (certain).
    """

    text = text.lower().strip()


    # ---------- EXIT ----------

    if text in [

        "exit",
        "quit"

    ]:

        return "exit", 1.0



    # ---------- MEMORY ----------

    if text.startswith("remember"):

        return "remember", 0.97

    if any(

        phrase in text for phrase in [

            "show memory",
            "what do you remember"

        ]

    ):

        return "show_memory", 0.97



    # ---------- TASK MANAGEMENT ----------

    if any(

        phrase in text for phrase in [

            "show tasks",
            "list tasks",
            "view tasks"

        ]

    ):

        return "task_management", 0.95



    if any(

        phrase in text for phrase in [

            "cancel all tasks",
            "remove all tasks",
            "delete all tasks",
            "clear all tasks"

        ]

    ):

        return "task_management", 0.95



    if any(

        phrase in text for phrase in [

            "cancel task",
            "pause task",
            "resume task"

        ]

    ):

        return "task_management", 0.95



    # ---------- SCHEDULER ----------

    if text.startswith("remind me"):

        return "schedule_task", 0.97

    if " in " in text and any(

        unit in text for unit in [

            "seconds",
            "minutes"

        ]

    ):

        return "schedule_task", 0.85

    if "every" in text:

        return "schedule_task", 0.80

    if " at " in text and any(

        word in text for word in [

            "run",
            "remind",
            "schedule"

        ]

    ):

        return "schedule_task", 0.88



    # ---------- WEATHER ----------

    if any(phrase in text for phrase in [
        "weather in",
        "weather for",
        "weather at",
        "weather today",
        "what's the weather",
        "what is the weather",
        "how's the weather",
        "how is the weather",
        "current weather",
        "temperature in",
        "is it raining",
        "will it rain",
        "forecast for",
        "forecast in",
    ]):
        return "weather", 0.97

    # plain "weather" as its own word — avoid matching "whether"
    if text == "weather" or text.startswith("weather "):
        return "weather", 0.95



    # ---------- WEB SEARCH ----------

    if any(phrase in text for phrase in [
        "search the web for",
        "search web for",
        "web search for",
        "web search",
        "search the web",
        "google ",
        "look up",
        "find info on",
        "find information on",
        "search for",
        "browse for",
        "internet search",
    ]):
        return "web_search", 0.95



    # ---------- FILE SEARCH ----------
    # NOTE: kept AFTER web_search so "search for X" goes to web_search,
    # but "find file X" / "locate X" still hits search_file.

    if text.startswith(("find file", "locate ", "search file")):
        return "search_file", 0.95

    # Generic "find" / "search" with no web-search trigger → file search
    if text.startswith(("find ", "search ")):
        return "search_file", 0.80



    # ---------- OPEN FILE ----------

    if text.startswith("open file"):

        return "open_file", 0.97



    # ---------- RUN PYTHON ----------

    if any(

        phrase in text for phrase in [

            "run file",
            "run script",
            "execute"

        ]

    ):

        return "run_python", 0.92



    # ---------- FILE OPERATIONS ----------

    if any(

        phrase in text for phrase in [

            "copy file",
            "move file",
            "delete file"

        ]

    ):

        return "file_operation", 0.95



    # ---------- CLOSE EXTERNAL APP ----------
    # Must be checked BEFORE open_app and the assistant close_app below.

    _known_apps = [
        "chrome", "notepad", "calculator", "calc", "paint",
        "explorer", "word", "excel", "vlc", "spotify",
        "discord", "vscode", "vs code", "task manager"
    ]

    _close_triggers = ["close", "quit", "kill", "exit", "stop", "terminate"]

    if any(trigger in text for trigger in _close_triggers) and \
       any(app in text for app in _known_apps):

        return "close_external_app", 0.95



    # ---------- OPEN APP ----------

    _open_triggers = ["open", "launch", "start", "run"]

    if any(trigger in text for trigger in _open_triggers) and \
       any(app in text for app in _known_apps):

        return "open_app", 0.95



    # ---------- SYSTEM INFO ----------

    if any(

        phrase in text for phrase in [

            "system info",
            "system status"

        ]

    ):

        return "system_info", 0.97



    # ---------- TIME ----------

    if any(

        phrase in text for phrase in [

            "what is the time",
            "what's the time",
            "whats the time",
            "current time",
            "time now",
            "what time is it",
            "tell me the time"

        ]

    ):

        return "get_time", 1.0



    # ---------- DATE ----------

    if any(

        phrase in text for phrase in [

            "what is the date",
            "what's the date",
            "whats the date",
            "today date",
            "today's date",
            "what day is it",
            "current date"

        ]

    ):

        return "get_date", 1.0



    # ---------- SYSTEM ACTIONS ----------

    if "close" in text and "app" in text:

        return "close_app", 0.92

    if "shutdown" in text:

        return "shutdown_pc", 1.0

    if "restart" in text:

        return "restart_pc", 1.0

    if "kill" in text:

        return "kill_process", 0.95

    # ---------- ACCESSIBILITY NAVIGATION ----------

    if text in [
        "read focus",
        "current item",
        "what is selected"
    ]:
        return "read_focus", 1.0

    if text in [
        "next",
        "next item",
        "next element"
    ]:
        return "next_element", 1.0

    if text in [
        "previous",
        "previous item",
        "go back"
    ]:
        return "previous_element", 1.0

    if text in [
        "click",
        "activate",
        "press enter"
    ]:
        return "activate_element", 1.0

    if text.startswith("type "):
        return "type_text", 0.97

    if text in [
        "scroll down"
    ]:
        return "scroll_down", 1.0

    if text in [
        "scroll up"
    ]:
        return "scroll_up", 1.0

    if text in [
        "where am i",
        "current window"
    ]:
        return "where_am_i", 1.0

    # ---------- SCREEN READER ----------

    if any(phrase in text for phrase in [
        "read my screen",
        "read the screen",
        "read screen",
        "what's on my screen",
        "what is on my screen",
        "whats on my screen",
        "what's on screen",
        "scan my screen",
        "scan the screen",
        "extract text from screen",
        "get text from screen",
        "read top left",
        "read top right",
        "read bottom left",
        "read bottom right",
        "read center",
        "read top half",
        "read bottom half",
        "read left half",
        "read right half",
    ]):
        return "read_screen", 0.97

    if any(phrase in text for phrase in [
        "take a screenshot",
        "take screenshot",
        "capture screen",
        "save screenshot",
        "screenshot",
    ]):
        return "screenshot", 1.0

    if any(phrase in text for phrase in [
        "what did my screen say",
        "last screen",
        "previous screen text",
        "show last screen",
    ]):
        return "last_screen", 0.97

    # ---------- FALLBACK TOOL MATCH ----------
    # If nothing matched above, check if any registered tool name appears in the text.
    try:
        from tools.registry import registry as _registry
        for name in _registry.tools:
            if name in text:
                return name, 0.70
    except Exception:
        pass

    # ---------- DEFAULT ----------

    return "chat", 0.40