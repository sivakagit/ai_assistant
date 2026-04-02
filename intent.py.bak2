def detect_intent(text):

    text = text.lower().strip()


    # ---------- EXIT ----------

    if text in [

        "exit",
        "quit"

    ]:

        return "exit"



    # ---------- MEMORY ----------

    if text.startswith("remember"):

        return "remember"

    if any(

        phrase in text for phrase in [

            "show memory",
            "what do you remember"

        ]

    ):

        return "show_memory"



    # ---------- TASK MANAGEMENT ----------

    if any(

        phrase in text for phrase in [

            "show tasks",
            "list tasks",
            "view tasks"

        ]

    ):

        return "task_management"



    if any(

        phrase in text for phrase in [

            "cancel all tasks",
            "remove all tasks",
            "delete all tasks",
            "clear all tasks"

        ]

    ):

        return "task_management"



    if any(

        phrase in text for phrase in [

            "cancel task",
            "pause task",
            "resume task"

        ]

    ):

        return "task_management"



    # ---------- SCHEDULER ----------

    if text.startswith("remind me"):

        return "schedule_task"

    if " in " in text and any(

        unit in text for unit in [

            "seconds",
            "minutes"

        ]

    ):

        return "schedule_task"

    if "every" in text:

        return "schedule_task"

    if " at " in text and any(

        word in text for word in [

            "run",
            "remind",
            "schedule"

        ]

    ):

        return "schedule_task"



    # ---------- FILE SEARCH ----------

    if text.startswith(

        ("find ", "search ", "locate ")

    ):

        return "search_file"



    # ---------- OPEN FILE ----------

    if text.startswith("open file"):

        return "open_file"



    # ---------- RUN PYTHON ----------

    if any(

        phrase in text for phrase in [

            "run file",
            "run script",
            "execute"

        ]

    ):

        return "run_python"



    # ---------- FILE OPERATIONS ----------

    if any(

        phrase in text for phrase in [

            "copy file",
            "move file",
            "delete file"

        ]

    ):

        return "file_operation"



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

        return "close_external_app"



    # ---------- OPEN APP ----------

    if any(

        phrase in text for phrase in [

            "open chrome",
            "launch",
            "start calculator",
            "open calculator",
            "open notepad",
            "open paint",
            "open explorer",
            "open word",
            "open excel",
            "open vlc",
            "open spotify",
            "open discord",
            "open vscode",
            "open vs code",
            "open task manager"

        ]

    ):

        return "open_app"



    # ---------- SYSTEM INFO ----------

    if any(

        phrase in text for phrase in [

            "system info",
            "system status"

        ]

    ):

        return "system_info"



    # ---------- TIME ----------

    if any(

        phrase in text for phrase in [

            "what is the time",
            "current time",
            "time now"

        ]

    ):

        return "get_time"



    # ---------- DATE ----------

    if any(

        phrase in text for phrase in [

            "what is the date",
            "today date"

        ]

    ):

        return "get_date"



    # ---------- SYSTEM ACTIONS ----------

    if "close" in text and "app" in text:

        return "close_app"

    if "shutdown" in text:

        return "shutdown_pc"

    if "restart" in text:

        return "restart_pc"

    if "kill" in text:

        return "kill_process"



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
        return "read_screen"

    if any(phrase in text for phrase in [
        "take a screenshot",
        "take screenshot",
        "capture screen",
        "save screenshot",
        "screenshot",
    ]):
        return "screenshot"

    if any(phrase in text for phrase in [
        "what did my screen say",
        "last screen",
        "previous screen text",
        "show last screen",
    ]):
        return "last_screen"


    # ---------- SCREEN EXPLANATION ----------

    if any(phrase in text for phrase in [
        "explain screen",
        "explain my screen",
        "describe screen",
        "describe my screen",
        "what is on my screen",
        "what's on my screen",
        "whats on my screen",
        "what do you see on screen",
        "tell me what's on screen",
        "tell me what is on screen",
        "what app is open",
        "what application is open",
        "what window is open",
        "what am i looking at",
        "describe what you see",
        "explain what you see",
    ]):
        return "explain_screen"

    # ---------- HANDWRITING READER ----------

    if any(phrase in text for phrase in [
        "read handwriting",
        "read handwritten",
        "read this handwritten",
        "ocr handwriting",
        "scan handwriting",
        "read old book",
        "read scanned book",
        "read scan",
        "read image text",
        "extract handwriting",
        "correct ocr",
        "fix ocr",
    ]):
        return "read_handwriting"

    # ---------- KEYBOARD NAVIGATION ----------

    if any(phrase in text for phrase in [
        "what is focused",
        "what has focus",
        "what control is focused",
        "read focused element",
        "what element is focused",
        "whats focused",
        "read focus",
        "current focus",
    ]):
        return "nav_focus"

    if any(phrase in text for phrase in [
        "what window is this",
        "what window am i in",
        "read window title",
        "current window",
        "active window",
        "window title",
        "what program is this",
    ]):
        return "nav_title"

    if any(phrase in text for phrase in [
        "list windows",
        "list open windows",
        "what windows are open",
        "show all windows",
        "open windows",
        "what is open",
        "what programs are open",
        "what apps are running",
    ]):
        return "nav_windows"

    if any(phrase in text for phrase in [
        "read clipboard",
        "what is in clipboard",
        "clipboard contents",
        "what did i copy",
        "paste contents",
        "show clipboard",
    ]):
        return "nav_clipboard"

    if any(phrase in text for phrase in [
        "toggle auto announce",
        "auto announce",
        "enable auto read",
        "disable auto read",
        "start reading focus",
        "stop reading focus",
        "turn on screen reader",
        "turn off screen reader",
        "enable screen reader",
        "disable screen reader",
    ]):
        return "nav_auto"

    if any(phrase in text for phrase in [
        "next window",
        "switch window",
        "alt tab",
        "go to next window",
        "switch to next window",
    ]):
        return "nav_next_window"

    if any(phrase in text for phrase in [
        "previous window",
        "go back window",
        "previous app",
        "switch to previous window",
    ]):
        return "nav_prev_window"

    # ---------- DEFAULT ----------

    return "chat"