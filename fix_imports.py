import os
import re

ROOT = "."

IMPORT_MAP = {

    "memory": "services.memory_service",
    "conversation": "services.conversation_service",
    "scheduler": "services.scheduler_service",
    "accessibility": "services.accessibility_service",
    "tts": "services.tts_service",

    "system_actions": "tools.system_tools",
    "file_search": "tools.file_tools",
    "export": "tools.export_tools",
    "conversation_search": "tools.conversation_search_tools",
    "system_info": "tools.system_info_tools",
    "time_utils": "tools.time_tools",
    "tool_registry": "tools.registry",
    "tools_manager": "tools.tools_manager",
    "screen_reader": "tools.screen_tools",

    "modern_gui": "ui.main_window",
    "tray_qt": "ui.tray",
    "confirmation_dialog": "ui.confirmation_dialog",

    "intent": "core.intent_engine",
    "settings": "core.config",
    "assistant": "core.assistant"

}

def update_imports_in_file(filepath):

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    original = content

    for old, new in IMPORT_MAP.items():

        content = re.sub(
            rf"from\s+{old}\s+import",
            f"from {new} import",
            content
        )

        content = re.sub(
            rf"import\s+{old}",
            f"import {new}",
            content
        )

    if content != original:

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        print("Updated:", filepath)


def walk_python_files():

    for root, dirs, files in os.walk(ROOT):

        if "backup_before_refactor" in root:
            continue

        for file in files:

            if file.endswith(".py"):

                path = os.path.join(root, file)

                update_imports_in_file(path)


if __name__ == "__main__":

    walk_python_files()