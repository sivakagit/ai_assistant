import os


LOG_FILE = os.path.join("logs", "assistant.log")


def read_recent_logs(lines=100):

    try:

        with open(LOG_FILE, "r", encoding="utf-8") as f:

            data = f.readlines()

        return "".join(data[-lines:])

    except FileNotFoundError:

        return "No logs available yet."

    except Exception as e:

        return f"Error reading logs: {e}"
