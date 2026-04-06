import sys

# Qt must initialize COM before anything else on Windows
if sys.platform == "win32":
    try:
        from PySide6 import QtCore  # noqa: F401
    except Exception:
        pass

import os

os.environ["QT_LOGGING_RULES"] = "*.debug=false;qt.qpa.window=false"
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"

from ui.main_window import main

main()