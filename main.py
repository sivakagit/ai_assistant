import os
import sys
import ctypes

# Initialize COM in multithreaded mode before Qt tries to use it
# This prevents "Cannot change thread mode after it is set" error on Windows
if sys.platform == "win32":
    try:
        # COINIT_MULTITHREADED = 0
        # COINIT_APARTMENTTHREADED = 2
        # Try to set multithreaded mode for compatibility with Qt
        ole32 = ctypes.windll.ole32
        ole32.CoInitializeEx(0, 0)  # COINIT_MULTITHREADED
    except Exception:
        # If this fails, that's okay - COM will be initialized  later anyway
        pass

# Redirect stderr to suppress Qt's internal C++ OleInitialize warning.
# This message is printed by Qt's DLL before Python can intercept it,
# so we must close the OS-level stderr handle before importing Qt.
if sys.platform == "win32":
    # Reopen stderr to NUL for startup only, restore after Qt initialises
    _devnull = open(os.devnull, "w")
    _old_stderr_fd = os.dup(2)
    os.dup2(_devnull.fileno(), 2)

os.environ["QT_LOGGING_RULES"] = "*.debug=false;qt.qpa.window=false"
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"

# --- your existing imports below ---
from ui.main_window import main   # Qt loads here

# Restore stderr so your app's real errors still show
if sys.platform == "win32":
    os.dup2(_old_stderr_fd, 2)
    os.close(_old_stderr_fd)
    _devnull.close()

main()