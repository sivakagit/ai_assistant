# ============================================================
#  PATCH for main_window.py
#  Replace the existing build_system_prompt() function
#  (lines ~252-303) with this upgraded version.
# ============================================================

from ui.main_window import retrieve_relevant_memory
from tools.registry import registry


def build_system_prompt(user_input: str = "") -> str:
    """
    Builds a structured system prompt with:
    - Clear behavior rules            (Step 1)
    - Web-answer handling rules       (Step 2 — NEW)
    - Available tools list            (Step 4)
    - Relevant memory only            (Step 5)
    """

    # ── Step 1: Structured base prompt ───────────────────────────────────────
    base = """\
You are Nova, a smart desktop AI assistant running on the user's PC.

Behavior rules:
1. Be concise and direct — avoid unnecessary filler words
2. Use tools when they are available instead of guessing
3. Ask for clarification only if truly needed
4. Never hallucinate facts, files, or system state
5. Prefer actionable, specific answers over vague ones
6. Use memory context when it is relevant to the question
7. Format output clearly — use bullet points for lists, short paragraphs for explanations

Response style:
- Keep replies short unless detail is explicitly requested
- Use plain language, not technical jargon unless the user is technical
- Never repeat the user's question back to them
- If a tool handled the request, confirm the result briefly"""

    # ── Step 2: Web search answer rules (NEW) ────────────────────────────────
    web_rules = """\
Web search answer rules (apply when a web search result is present in context):
- Treat the provided facts as ground truth — do NOT add information from your training data
- If the facts contain a specific number, price, or name — use it exactly as given
- If sources disagree, say so: "Sources give different values: X and Y"
- If confidence is flagged as low (< 70%), say: "This may be approximate — please verify"
- Never say "As of my last update" when live search data is provided
- Cite the source URL at the end if one was provided"""

    sections = [base, web_rules]

    # ── Step 4: Tool list awareness ──────────────────────────────────────────
    try:
        tool_names = registry.list_tools()
        if tool_names:
            tool_lines = "\n".join(f"  - {t}" for t in sorted(tool_names))
            sections.append(
                f"Available tools (already handled automatically — do not suggest these manually):\n"
                f"{tool_lines}"
            )
    except Exception:
        pass

    # ── Step 5: Relevant memory only ─────────────────────────────────────────
    relevant = retrieve_relevant_memory(user_input)
    if relevant:
        mem_lines = "\n".join(f"  {k}: {v}" for k, v in relevant.items())
        sections.append(
            f"Known facts about the user (use only when directly relevant — do not repeat unprompted):\n"
            f"{mem_lines}"
        )

    return "\n\n".join(sections)