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

    text_lower = text.lower().strip()

    def _after(phrase):
        """Extract text after a phrase, strip punctuation."""
        return text.split(phrase, 1)[-1].strip().rstrip(".!,")

    def _after_lower(phrase):
        return text_lower.split(phrase, 1)[-1].strip().rstrip(".!,")

    # Name
    if "my name is" in text_lower:
        save_memory("name", _after("my name is") or _after("My name is"))

    # Role / job
    for phrase in ("i am a ", "i am an ", "i'm a ", "i'm an ", "i work as "):
        if phrase in text_lower:
            save_memory("role", _after_lower(phrase))
            break

    # Study
    if "i study" in text_lower:
        save_memory("field_of_study", _after_lower("i study"))

    # Location
    if "i live in" in text_lower:
        save_memory("location", _after("i live in") or _after("I live in"))

    # Age
    if "i am " in text_lower and " years old" in text_lower:
        age_part = _after_lower("i am ").split()[0]
        if age_part.isdigit():
            save_memory("age", age_part)

    # Language / preference
    if "i prefer" in text_lower:
        save_memory("preference", _after_lower("i prefer"))

    if "i like" in text_lower:
        save_memory("likes", _after_lower("i like"))

    if "i use" in text_lower:
        save_memory("tools", _after_lower("i use"))

    # Explicit "remember that X is Y"
    if text_lower.startswith("remember "):
        data = _after_lower("remember ").lstrip("that ").strip()
        if " is " in data:
            key, value = data.split(" is ", 1)
            save_memory(key.strip(), value.strip())