import os
import threading

# ---------- CONFIGURATION ----------

MAX_RESULTS = 10

# Search these high-priority folders first (fast, covers 95% of user files)
PRIORITY_ROOTS = [
    os.path.join(os.path.expanduser("~"), "Desktop"),
    os.path.join(os.path.expanduser("~"), "Documents"),
    os.path.join(os.path.expanduser("~"), "Downloads"),
    os.path.join(os.path.expanduser("~"), "Pictures"),
    os.path.join(os.path.expanduser("~"), "Videos"),
    os.path.join(os.path.expanduser("~"), "Music"),
    os.path.expanduser("~"),   # Home folder itself
]

# Only fall back to full drive scan if nothing found in priority folders
FALLBACK_ROOTS = [
    "C:\\",
    "D:\\",
    "E:\\",
]

# Skip these folders entirely — they are huge, system-only, and never
# contain user files. Skipping them makes drive-wide search tolerable.
SKIP_DIRS = {
    "windows",
    "system32",
    "syswow64",
    "winsxs",
    "program files",
    "program files (x86)",
    "programdata",
    "appdata",
    "$recycle.bin",
    "system volume information",
    "recovery",
    "perflogs",
    "boot",
    "msocache",
    "intel",
    "amd",
    "nvidia",
    "node_modules",
    "__pycache__",
    ".git",
}

# Skip files with these extensions (binary / system junk)
SKIP_EXTENSIONS = {
    ".lnk", ".tmp", ".log", ".sys", ".dll", ".exe",
    ".dat", ".db", ".sqlite", ".cache", ".mui",
    ".cat", ".inf", ".ini",
}

# How many seconds to allow for the full drive fallback scan
FALLBACK_TIMEOUT = 10.0

# Thread-safe storage of last results
last_search_results = []
_lock = threading.Lock()


# ---------- HELPERS ----------

def _should_skip_dir(dirname):
    return dirname.lower() in SKIP_DIRS


def _should_skip_file(filename):
    _, ext = os.path.splitext(filename)
    return ext.lower() in SKIP_EXTENSIONS


def _walk_root(root, query, matches, max_results, stop_event):
    """Walk a directory tree, appending matches. Stops when stop_event is set."""
    try:
        for dirpath, dirnames, files in os.walk(root, topdown=True, onerror=None):

            if stop_event.is_set():
                return

            # Prune skip dirs in-place so os.walk won't descend into them
            dirnames[:] = [
                d for d in dirnames
                if not _should_skip_dir(d)
            ]

            for name in files:
                if stop_event.is_set():
                    return

                if _should_skip_file(name):
                    continue

                if query in name.lower():
                    full_path = os.path.join(dirpath, name)
                    matches.append(full_path)

                    if len(matches) >= max_results:
                        stop_event.set()
                        return

    except PermissionError:
        pass
    except Exception:
        pass


def _fallback_scan(query, matches, stop_event):
    """Scan full drives for files not found in priority folders."""
    seen = set(matches)  # avoid duplicates from phase 1

    for drive in FALLBACK_ROOTS:
        if stop_event.is_set():
            return
        if not os.path.exists(drive):
            continue

        temp = []
        _walk_root(drive, query, temp, MAX_RESULTS, stop_event)

        for path in temp:
            if path not in seen:
                seen.add(path)
                matches.append(path)
                if len(matches) >= MAX_RESULTS:
                    stop_event.set()
                    return


# ---------- PUBLIC API ----------

def search_files(query):
    """
    Search for files matching *query* (case-insensitive substring match).

    Strategy:
      1. Search priority user folders immediately (fast, no timeout needed).
      2. If still under MAX_RESULTS, do a capped-time full drive scan in a
         background thread so the caller is never blocked for long.

    Returns a list of matching absolute paths (up to MAX_RESULTS).
    """
    global last_search_results

    query = query.lower().strip()
    if not query:
        return []

    matches = []
    stop_event = threading.Event()

    # --- Phase 1: priority folders (synchronous, fast) ---
    for root in PRIORITY_ROOTS:
        if stop_event.is_set():
            break
        if os.path.exists(root):
            _walk_root(root, query, matches, MAX_RESULTS, stop_event)

    # --- Phase 2: full drive fallback (background thread with timeout) ---
    if not stop_event.is_set():
        fallback_thread = threading.Thread(
            target=_fallback_scan,
            args=(query, matches, stop_event),
            daemon=True
        )
        fallback_thread.start()
        fallback_thread.join(timeout=FALLBACK_TIMEOUT)
        # Signal the thread to stop whether it finished or timed out
        stop_event.set()

    with _lock:
        last_search_results = list(matches[:MAX_RESULTS])

    return last_search_results