import os
import shutil
from datetime import datetime

# ---------- BACKUP ----------

def create_backup():

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    backup_name = f"backup_before_refactor_{timestamp}"

    shutil.copytree(
        ".",
        backup_name,
        ignore=shutil.ignore_patterns(
            "__pycache__",
            ".git",
            backup_name
        )
    )

    print("Backup created:", backup_name)


# ---------- FOLDERS ----------

FOLDERS = [

    "core",
    "services",
    "tools",
    "ui",
    "models",
    "install",
    "patches",
    "data",
    "infrastructure",
    "backup",
    "workspace"

]


def create_folders():

    for folder in FOLDERS:

        os.makedirs(folder, exist_ok=True)

        print("Created:", folder)


# ---------- MOVE MAP ----------

MOVE_MAP = {

    # core

    "assistant.py":
        "core/assistant.py",

    "intent.py":
        "core/intent_engine.py",

    "settings.py":
        "core/config.py",

    "startup.py":
        "core/startup.py",

    "run_python.py":
        "core/run_python.py",

    # services

    "memory.py":
        "services/memory_service.py",

    "conversation.py":
        "services/conversation_service.py",

    "scheduler.py":
        "services/scheduler_service.py",

    "accessibility.py":
        "services/accessibility_service.py",

    "tts.py":
        "services/tts_service.py",

    # tools

    "screen_reader.py":
        "tools/screen_tools.py",

    "system_actions.py":
        "tools/system_tools.py",

    "file_search.py":
        "tools/file_tools.py",

    "export.py":
        "tools/export_tools.py",

    "conversation_search.py":
        "tools/conversation_search_tools.py",

    "system_info.py":
        "tools/system_info_tools.py",

    "time_utils.py":
        "tools/time_tools.py",

    "tool_registry.py":
        "tools/registry.py",

    "tools_manager.py":
        "tools/tools_manager.py",

    # ui

    "modern_gui.py":
        "ui/main_window.py",

    "tray_qt.py":
        "ui/tray.py",

    "confirmation_dialog.py":
        "ui/confirmation_dialog.py",

    # models

    "model_downloader.py":
        "models/downloader.py",

    "ollama_setup.py":
        "models/ollama_setup.py",

    # install

    "install_ollama":
        "install/install_ollama.ps1",

    "installer":
        "install/installer.iss",

    # patches

    "modern_gui_accessibility_patch.py":
        "patches/modern_gui_accessibility_patch.py",

    "patch_intent_accessibility.py":
        "patches/patch_intent_accessibility.py",

    "tools_manager_accessibility_addon.py":
        "patches/tools_manager_accessibility_addon.py",

    # data

    "config":
        "data/config.json",

    "memory":
        "data/memory.json",

    "conversation":
        "data/conversation.json",

    "tasks":
        "data/tasks.json",

    # misc

    "intent.py.bak2":
        "backup/intent.py.bak2",

    "Assistant":
        "workspace/Assistant.code-workspace",

    "requirements":
        "requirements.txt"

}


def move_files():

    for src, dst in MOVE_MAP.items():

        if not os.path.exists(src):

            continue

        os.makedirs(
            os.path.dirname(dst),
            exist_ok=True
        )

        shutil.move(src, dst)

        print("Moved:", src, "→", dst)


def move_directories():

    if os.path.exists("sessions"):

        shutil.move(
            "sessions",
            "data/sessions"
        )

        print("Moved sessions")

    if os.path.exists("Output"):

        shutil.move(
            "Output",
            "data/Output"
        )

        print("Moved Output")


def create_main():

    content = '''

from core.assistant import main

if __name__ == "__main__":
    main()

'''

    with open("main.py", "w") as f:

        f.write(content)

    print("Created main.py")


def run():

    print()
    print("Starting full restructuring...")
    print()

    create_backup()

    create_folders()

    move_files()

    move_directories()

    create_main()

    print()
    print("Restructuring complete.")
    print()


if __name__ == "__main__":

    run()