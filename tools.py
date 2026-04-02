import os
import subprocess

# ---------- Scan installed apps ----------

START_MENU_PATHS = [
    r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs",
    os.path.expandvars(
        r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"
    ),
]


def scan_apps():

    apps = {}

    for path in START_MENU_PATHS:

        if not os.path.exists(path):
            continue

        for root, dirs, files in os.walk(path):

            for file in files:

                if file.endswith(".lnk"):

                    name = file.replace(".lnk", "").lower()

                    full_path = os.path.join(root, file)

                    apps[name] = full_path

    return apps


# IMPORTANT — this creates the APPS variable
APPS = scan_apps()

# ---------- Open app function ----------


def open_app(app_name):

    app_name = app_name.lower()

    # Special Windows locations

    SPECIAL_LOCATIONS = {
        "thispc": "explorer shell:MyComputerFolder",
        "my computer": "explorer shell:MyComputerFolder",
        "file explorer": "explorer",
        "explorer": "explorer",
        "documents": "explorer shell:Personal",
        "downloads": "explorer shell:Downloads",
        "desktop": "explorer shell:Desktop",
    }

    if app_name in SPECIAL_LOCATIONS:

        subprocess.Popen(
            SPECIAL_LOCATIONS[app_name],
            shell=True
        )

        return f"Opening {app_name}"

    # Built-in apps

    BUILTIN_APPS = {
        "notepad": ["notepad"],
        "calculator": ["calc"],
        "paint": ["mspaint"],
        "cmd": ["cmd"],
        "powershell": ["powershell"],
    }

    if app_name in BUILTIN_APPS:

        subprocess.Popen(BUILTIN_APPS[app_name])

        return f"Opening {app_name}"

    # Installed apps

    for name, path in APPS.items():

        if app_name in name:

            try:

                os.startfile(path)

                return f"Opening {name}"

            except Exception as e:

                return str(e)

    return "App not found"