import threading
import time
import json
import os

from datetime import datetime, timedelta

from core.run_python import run_python_script

# NEW — import resource_path safely
from core.config import resource_path

_scheduler_running = False
# ---------- WINDOWS NOTIFICATION (RELIABLE) ----------

try:

    from winotify import Notification

    def notify(title, message):

        toast = Notification(

            app_id="Assistant",

            title=title,

            msg=message,

            duration="short"

        )

        toast.show()

except Exception:

    # fallback if notifications fail

    def notify(title, message):

        print(title + ": " + message)


# UPDATED — use resource_path instead of relative path

TASK_FILE = resource_path("tasks.json")

scheduled_tasks = []


# ---------- SAVE TASKS ----------

def save_tasks():

    data = []

    for task in scheduled_tasks:

        interval = task.get("interval")

        interval_seconds = None

        if interval:

            interval_seconds = int(
                interval.total_seconds()
            )

        data.append({

            "time": task["time"].isoformat(),

            "type": task["type"],

            "action": task["action"],

            "recurring": task.get("recurring"),

            "interval_seconds": interval_seconds,

            "paused": task.get(
                "paused",
                False
            )

        })

    with open(TASK_FILE, "w") as f:

        json.dump(
            data,
            f,
            indent=2
        )


# ---------- LOAD TASKS (CRASH SAFE) ----------

def load_tasks():

    global scheduled_tasks

    if not os.path.exists(TASK_FILE):

        return

    try:

        with open(TASK_FILE, "r") as f:

            content = f.read().strip()

            if not content:

                scheduled_tasks = []

                return

            data = json.loads(content)

    except json.JSONDecodeError:

        print(
            "⚠ tasks.json corrupted — resetting file"
        )

        scheduled_tasks = []

        save_tasks()

        return

    scheduled_tasks = []

    for task in data:

        interval = None

        if task.get("interval_seconds"):

            interval = timedelta(

                seconds=task[
                    "interval_seconds"
                ]

            )

        scheduled_tasks.append({

            "time": datetime.fromisoformat(
                task["time"]
            ),

            "type": task["type"],

            "action": task["action"],

            "recurring": task.get("recurring"),

            "interval": interval,

            "paused": task.get(
                "paused",
                False
            )

        })


# ---------- LIST TASKS ----------

def list_tasks():

    if not scheduled_tasks:

        return "No scheduled tasks"

    lines = []

    for i, task in enumerate(
        scheduled_tasks,
        start=1
    ):

        status = (
            "PAUSED"
            if task.get("paused")
            else "ACTIVE"
        )

        recurring = task.get(
            "recurring"
        )

        if recurring:

            lines.append(

                f"{i}. [{status}] reminder every "

                f"{recurring} — "

                f"{task['action']}"

            )

        else:

            time_str = task["time"].strftime(
                "%Y-%m-%d %H:%M:%S"
            )

            lines.append(

                f"{i}. [{status}] reminder at "

                f"{time_str} — "

                f"{task['action']}"

            )

    return "\n".join(lines)


# ---------- CANCEL TASK ----------

def cancel_task(index):

    if not scheduled_tasks:

        return "No tasks to cancel"

    if not (0 <= index < len(scheduled_tasks)):

        return "Invalid task number"

    removed = scheduled_tasks.pop(index)

    save_tasks()

    return f"Cancelled task: {removed['action']}"


def cancel_all_tasks():

    scheduled_tasks.clear()

    save_tasks()

    return "All tasks cancelled"


# ---------- PAUSE TASK ----------

def pause_task(index):

    if not (0 <= index < len(scheduled_tasks)):

        return "Invalid task number"

    scheduled_tasks[index]["paused"] = True

    save_tasks()

    return "Task paused"


# ---------- RESUME TASK ----------

def resume_task(index):

    if not (0 <= index < len(scheduled_tasks)):

        return "Invalid task number"

    scheduled_tasks[index]["paused"] = False

    save_tasks()

    return "Task resumed"


# ---------- RUN LOOP ----------

def run_scheduler():

    global _scheduler_running

    _scheduler_running = True

    while _scheduler_running:

        now = datetime.now()

        for task in scheduled_tasks[:]:

            if task.get("paused"):

                continue

            if now >= task["time"]:

                message = task["action"]

                print()
                print(
                    "🔔 Reminder:",
                    message
                )

                notify(
                    "Reminder",
                    message
                )

                if task["type"] == "script":

                    print(
                        "▶ Running scheduled script:"
                    )

                    output = run_python_script(
                        message
                    )

                    print(output)

                    notify(
                        "Script Executed",
                        message
                    )

                print()

                print(
                    "You:",
                    end=" ",
                    flush=True
                )

                if task.get("recurring"):

                    interval = task["interval"]

                    task["time"] = now + interval

                else:

                    scheduled_tasks.remove(
                        task
                    )

                save_tasks()

        time.sleep(1)


# ---------- START SCHEDULER ----------

def start_scheduler():

    load_tasks()

    thread = threading.Thread(

        target=run_scheduler,

        daemon=True

    )

    thread.start()

def stop_scheduler():

    global _scheduler_running

    _scheduler_running = False

    print("Scheduler stopped")
# ---------- ONE-TIME TASKS ----------

def schedule_in_minutes(minutes, message):

    run_time = datetime.now() + timedelta(
        minutes=minutes
    )

    scheduled_tasks.append({

        "time": run_time,

        "type": "reminder",

        "action": message,

        "paused": False

    })

    save_tasks()

    return f"Reminder set for {minutes} minutes"


def schedule_in_seconds(seconds, message):

    run_time = datetime.now() + timedelta(
        seconds=seconds
    )

    scheduled_tasks.append({

        "time": run_time,

        "type": "reminder",

        "action": message,

        "paused": False

    })

    save_tasks()

    return f"Reminder set for {seconds} seconds"


# ---------- RECURRING TASKS ----------

def schedule_every_minutes(minutes, message):

    run_time = datetime.now() + timedelta(
        minutes=minutes
    )

    scheduled_tasks.append({

        "time": run_time,

        "type": "reminder",

        "action": message,

        "recurring": f"{minutes} minutes",

        "interval": timedelta(minutes=minutes),

        "paused": False

    })

    save_tasks()

    return f"Recurring reminder every {minutes} minutes"


def schedule_every_day(time_str, message):

    try:

        now = datetime.now()

        target_time = datetime.strptime(
            time_str,
            "%H:%M"
        )

        run_time = now.replace(

            hour=target_time.hour,
            minute=target_time.minute,
            second=0

        )

        if run_time < now:

            run_time += timedelta(days=1)

        scheduled_tasks.append({

            "time": run_time,

            "type": "reminder",

            "action": message,

            "recurring": "day",

            "interval": timedelta(days=1),

            "paused": False

        })

        save_tasks()

        return f"Daily reminder at {time_str}"

    except ValueError:

        return "Invalid time format. Use HH:MM"


# ---------- SCHEDULER STATUS ----------

def is_scheduler_running():

    return _scheduler_running


# ---------- SCRIPT TASK ----------

def schedule_script_at(time_str, script):

    try:

        now = datetime.now()

        target_time = datetime.strptime(
            time_str,
            "%H:%M"
        )

        run_time = now.replace(

            hour=target_time.hour,
            minute=target_time.minute,
            second=0

        )

        if run_time < now:

            run_time += timedelta(days=1)

        scheduled_tasks.append({

            "time": run_time,

            "type": "script",

            "action": script,

            "paused": False

        })

        save_tasks()

        return f"Script scheduled at {time_str}"

    except ValueError:

        return "Invalid time format. Use HH:MM"