"""
debug_intent.py  —  Run in your project folder to test intent detection.

    python debug_intent.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from intent import detect_intent

tests = [
    "read my screen",
    "read the screen",
    "read screen",
    "what's on my screen",
    "what is on my screen",
    "scan my screen",
    "take a screenshot",
    "screenshot",
    "what did my screen say",
    "last screen",
]

print("=" * 50)
print("INTENT DETECTION TEST")
print("=" * 50)
for phrase in tests:
    result = detect_intent(phrase)
    status = "✓" if result in ("read_screen", "screenshot", "last_screen") else "✗ WRONG"
    print(f"  {status}  '{phrase}' → '{result}'")

print()
print("Type a phrase to test (or 'quit' to exit):")
while True:
    try:
        phrase = input("  > ").strip()
        if phrase.lower() in ("quit", "exit", "q"):
            break
        print(f"    intent: '{detect_intent(phrase)}'")
    except (EOFError, KeyboardInterrupt):
        break
