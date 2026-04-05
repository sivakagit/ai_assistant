import subprocess
import psutil
import ollama
import threading
import time
from collections import deque


def is_model_installed(model):

    try:

        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True
        )

        return model in result.stdout

    except Exception:

        return False


def detect_hardware():

    ram = psutil.virtual_memory().total / (1024 ** 3)

    if ram < 8:

        return "phi3:mini"

    if ram < 16:

        return "qwen2.5:3b"

    return "llama3:8b"


def format_speed(bytes_per_sec):
    """Return human-readable speed string: KB/s, MB/s, or GB/s."""

    if bytes_per_sec <= 0:
        return "— KB/s"

    if bytes_per_sec < 1024 * 1024:
        return f"{bytes_per_sec / 1024:.1f} KB/s"

    if bytes_per_sec < 1024 * 1024 * 1024:
        return f"{bytes_per_sec / (1024 * 1024):.2f} MB/s"

    return f"{bytes_per_sec / (1024 * 1024 * 1024):.2f} GB/s"


# ---------- DOWNLOAD CONTROLLER ----------

class DownloadController:

    MAX_RETRIES = 999
    RETRY_DELAY = 5
    SPEED_WINDOW = 3       # FIX: reduced from 5s to 3s for faster response

    def __init__(self):

        self._paused = threading.Event()
        self._paused.set()

        self._cancelled = threading.Event()
        self._cancelled.clear()

        self.last_percent = 0
        self.last_completed = 0
        self.last_total = 0

        self._speed_samples = deque()
        self._download_start_time = None   # FIX: track start time for first-sample speed

    def pause(self):
        self._paused.clear()

    def resume(self):
        self._paused.set()

    def cancel(self):
        self._cancelled.set()
        self._paused.set()

    @property
    def is_cancelled(self):
        return self._cancelled.is_set()

    @property
    def is_paused(self):
        return not self._paused.is_set()

    def wait_if_paused(self):
        self._paused.wait()
        return not self._cancelled.is_set()

    def _record_sample(self, completed):
        """Add a speed sample and discard old ones outside the window."""
        now = time.time()
        self._speed_samples.append((now, completed))

        cutoff = now - self.SPEED_WINDOW
        while self._speed_samples and self._speed_samples[0][0] < cutoff:
            self._speed_samples.popleft()

    def _get_rolling_speed(self):
        """
        Return rolling average speed in bytes/sec.

        FIX: Works from the very first sample by using _download_start_time
        as the baseline when only one sample exists, instead of requiring 2+
        samples (which caused speed to show '— KB/s' for the first few seconds).
        """
        if not self._speed_samples:
            return 0.0

        newest_time, newest_bytes = self._speed_samples[-1]

        if len(self._speed_samples) >= 2:
            oldest_time, oldest_bytes = self._speed_samples[0]
        else:
            # FIX: use download start as baseline for first sample
            oldest_time = self._download_start_time if self._download_start_time else newest_time
            oldest_bytes = 0

        elapsed = newest_time - oldest_time
        if elapsed <= 0:
            return 0.0

        return (newest_bytes - oldest_bytes) / elapsed

    def _clear_speed_samples(self):
        """Clear speed history (used after pause/resume to avoid stale data)."""
        self._speed_samples.clear()
        # FIX: reset start time on resume so first-sample speed calc stays accurate
        self._download_start_time = time.time()

    def download(self, model, callback=None):

        retries = 0

        while not self._cancelled.is_set():

            try:

                # FIX: record start time at the beginning of each attempt
                self._download_start_time = time.time()

                stream = ollama.pull(model, stream=True)

                for chunk in stream:

                    if self._cancelled.is_set():

                        if callback:
                            callback(
                                self.last_percent,
                                self.last_completed,
                                self.last_total,
                                "—",
                                "—",
                                "cancelled"
                            )

                        return False

                    if self.is_paused:

                        if callback:
                            callback(
                                self.last_percent,
                                self.last_completed,
                                self.last_total,
                                "—",
                                "—",
                                "paused"
                            )

                        still_going = self.wait_if_paused()

                        if not still_going:
                            return False

                        self._clear_speed_samples()

                    total = chunk.get("total", 0) or 0
                    completed = chunk.get("completed", 0) or 0
                    status_str = chunk.get("status", "")

                    if total > 0 and completed > 0:

                        self.last_percent = int((completed / total) * 100)
                        self.last_completed = completed
                        self.last_total = total

                        self._record_sample(completed)

                        speed_bps = self._get_rolling_speed()
                        speed_str = format_speed(speed_bps)

                        remaining_bytes = total - completed

                        if speed_bps > 0:
                            eta_seconds = remaining_bytes / speed_bps
                            m = int(eta_seconds // 60)
                            s = int(eta_seconds % 60)
                            eta_str = f"{m}:{s:02d}"
                        else:
                            eta_str = "—"

                        if callback:
                            callback(
                                self.last_percent,
                                completed,
                                total,
                                speed_str,
                                eta_str,
                                "downloading"
                            )

                    else:

                        if callback:
                            callback(
                                self.last_percent,
                                0,
                                0,
                                "—",
                                "—",
                                status_str or "downloading"
                            )

                if not self._cancelled.is_set():

                    if callback:
                        callback(100, self.last_total, self.last_total, "—", "Done", "done")

                    return True

            except Exception as e:

                error_msg = str(e).lower()

                if self._cancelled.is_set():
                    return False

                network_errors = [
                    "connection",
                    "timeout",
                    "network",
                    "reset",
                    "eof",
                    "broken pipe",
                    "remote end closed"
                ]

                is_network_error = any(
                    kw in error_msg for kw in network_errors
                )

                if is_network_error and retries < self.MAX_RETRIES:

                    retries += 1

                    self._clear_speed_samples()

                    if callback:
                        callback(
                            self.last_percent,
                            self.last_completed,
                            self.last_total,
                            "—",
                            "—",
                            "retrying"
                        )

                    for _ in range(self.RETRY_DELAY):

                        if self._cancelled.is_set():
                            return False

                        time.sleep(1)

                    continue

                else:

                    if callback:
                        callback(
                            self.last_percent,
                            self.last_completed,
                            self.last_total,
                            "—",
                            "—",
                            f"error: {str(e)}"
                        )

                    return False

        return False