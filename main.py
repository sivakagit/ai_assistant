import os
import sys

# Set environment variables BEFORE any Qt imports
os.environ["QT_LOGGING_RULES"] = "*.debug=false;qt.qpa.window=false"
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"

# Import QtCore IMMEDIATELY to let Qt initialize COM properly
# This must happen before any other imports that might use COM
if sys.platform == "win32":
    from PySide6 import QtCore  # noqa: F401 - triggers Qt's COM initialization

# NOW import everything else
from ui.main_window import main

main()