import os
import sys

# Don't pre-initialize COM - let pywindow handle it properly per-thread
# Instead, set Qt to use multithreaded COM initialization
if sys.platform == "win32":
    # Tell Qt to initialize COM in multithreaded mode
    os.environ["QT_QPA_PLATFORM"] = "windows"

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