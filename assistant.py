import ollama

from tools_manager import registry
from intent import detect_intent

from memory import load_memory
from conversation import (
    add_message,
    get_history
)

from scheduler import start_scheduler


from settings import get_setting

MODEL = get_setting("model")


# ---------- MEMORY PROMPT ----------

def build_memory_prompt(user_input):

    memory_data = load_memory()

    if not memory_data:

        return user_input

    memory_lines = []

    for key, value in memory_data.items():

        memory_lines.append(
            f"{key}: {value}"
        )

    memory_text = "\n".join(memory_lines)

    prompt = f"""
You are a personal assistant.

Use stored memory when relevant.

Memory:

{memory_text}

User message:

{user_input}

Respond naturally.
"""

    return prompt.strip()


# ---------- LLM ----------

def ask_llm(user_input):

    prompt = build_memory_prompt(
        user_input
    )

    history = get_history()

    messages = history + [

        {
            "role": "user",
            "content": prompt
        }

    ]

    response = ollama.chat(

        model=MODEL,

        messages=messages

    )

    assistant_reply = response[
        "message"
    ][
        "content"
    ]

    add_message(
        "assistant",
        assistant_reply
    )

    return assistant_reply


# ---------- COMMAND ROUTER ----------

def handle_command(text):

    text_lower = text.lower().strip()

    add_message(
        "user",
        text
    )

    intent = detect_intent(
        text_lower
    )

    tool = registry.get(
        intent
    )

    if tool:

        return tool(text)

    return ask_llm(text)


# ---------- MAIN ----------

def main():

    print(
        "Assistant started. Type 'exit' to quit."
    )

    start_scheduler()

    while True:

        try:

            user_input = input("You: ")

            if user_input.lower() == "exit":

                print(
                    "Assistant stopped."
                )

                break

            response = handle_command(
                user_input
            )

            print(
                "Assistant:",
                response
            )

        except KeyboardInterrupt:

            print(
                "\nAssistant stopped."
            )

            break

        except Exception as e:

            print(
                "Error:",
                str(e)
            )


if __name__ == "__main__":

    main()