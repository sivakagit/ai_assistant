import json
import os

from core.config import resource_path

MEMORY_FILE = resource_path("memory.json")


def load_memory():

    if not os.path.exists(MEMORY_FILE):

        return {}

    try:

        with open(MEMORY_FILE, "r") as f:

            return json.load(f)

    except Exception:

        return {}


def save_memory(key, value):

    memory = load_memory()

    if "profile" not in memory:

        memory["profile"] = {}

    memory["profile"][key] = value

    with open(MEMORY_FILE, "w") as f:

        json.dump(
            memory,
            f,
            indent=2
        )


def get_memory(key):

    memory = load_memory()

    # Check nested profile first, then flat for backwards compatibility
    profile = memory.get("profile", {})

    if key in profile:

        return profile[key]

    return memory.get(key)


def maybe_store_memory(text):

    text_lower = text.lower()

    if "my name is" in text_lower:

        name = text.split("is")[-1].strip().rstrip(".")

        save_memory("name", name)

    if "i am a" in text_lower:

        role = text_lower.split("i am a")[-1].strip().rstrip(".")

        save_memory("role", role)

    if "i am an" in text_lower:

        role = text_lower.split("i am an")[-1].strip().rstrip(".")

        save_memory("role", role)

    if "i study" in text_lower:

        subject = text_lower.split("i study")[-1].strip().rstrip(".")

        save_memory("field_of_study", subject)

    if "i work as" in text_lower:

        job = text_lower.split("i work as")[-1].strip().rstrip(".")

        save_memory("role", job)

    if "i live in" in text_lower:

        location = text.split("i live in")[-1].strip().rstrip(".")

        save_memory("location", location)

    if "i'm a" in text_lower:

        role = text_lower.split("i'm a")[-1].strip().rstrip(".")

        save_memory("role", role)