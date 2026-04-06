import os
import sys

if sys.platform == "win32":
    # Import PySide6 FIRST on Windows to initialize COM in multithreaded mode
    # This must happen before any other COM-using libraries are imported
    try:
        import ctypes
        # Manually initialize COM in multithreaded mode for this thread
        ole32 = ctypes.windll.ole32
        ole32.CoInitializeEx(0, 0)  # COINIT_MULTITHREADED
    except Exception:
        pass

os.environ["QT_LOGGING_RULES"] = "*.debug=false;qt.qpa.window=false"
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"

# Import the main function from the UI module
# By this point, COM has been initialized in the right mode
from ui.main_window import main

main()