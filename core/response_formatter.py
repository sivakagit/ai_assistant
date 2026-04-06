def normalize_response(text: str) -> str:
    """
    Clean and standardize assistant output before display.
    """

    if not text:
        return "No result."

    text = text.strip()

    # Remove common filler / hallucination phrases
    fillers = [
        "I don't have direct access",
        "You can check",
        "Would you like me to",
        "I am an AI",
        "As an AI",
    ]

    for phrase in fillers:

        if text.lower().startswith(
            phrase.lower()
        ):

            return "Searching online..."

    # Collapse whitespace
    text = " ".join(
        text.split()
    )

    return text


def classify_result(text: str) -> str:

    if not text:
        return "empty"

    if len(text) < 80:
        return "short"

    if "\n" in text:
        return "structured"

    return "long"


def limit_length(
    text: str,
    max_chars: int = 800
) -> str:

    if len(text) <= max_chars:

        return text

    return text[:max_chars] + "..."