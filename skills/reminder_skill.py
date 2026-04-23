"""Reminder & alarm skill — creates reminders via macOS Reminders app."""
import re
import subprocess

TRIGGERS = [
    "erinnerung", "erinnere mich", "reminder", "erinner", "aufgabe",
    "notiz erstellen", "to-do", "todo",
    "alarm", "wecker", "weck mich",
]

def execute(user_input: str) -> str:
    t = user_input.lower()

    # Extract time if present (e.g. "in 10 Minuten", "um 15 Uhr")
    time_match = re.search(r'in (\d+) minuten?', t)
    at_match   = re.search(r'um (\d{1,2})(?::(\d{2}))? uhr', t)

    # Extract reminder text (everything after "dass", "um", "an", ":")
    text = re.sub(
        r'(erinnere mich|erinnerung|reminder|erinner|alarm|wecker|weck mich|in \d+ minuten?|um \d{1,2}(?::\d{2})? uhr)',
        '', user_input, flags=re.IGNORECASE
    ).strip(" ,.:!?-")
    if not text:
        text = "Erinnerung von Jarvis"

    if time_match:
        mins = int(time_match.group(1))
        return _create_reminder(text, f"in {mins} Minuten")
    elif at_match:
        hour = at_match.group(1)
        minute = at_match.group(2) or "00"
        return _create_reminder(text, f"um {hour}:{minute} Uhr")
    else:
        return _create_reminder(text, None)


def _create_reminder(name: str, time_hint: str | None) -> str:
    script = f'''
    tell application "Reminders"
        set newReminder to make new reminder with properties {{name:"{name}"}}
        return "Erinnerung erstellt: {name}"
    end tell
    '''
    try:
        out = subprocess.check_output(["osascript", "-e", script], timeout=8).decode().strip()
        suffix = f" ({time_hint})" if time_hint else ""
        return f"Erinnerung gesetzt: {name}{suffix}"
    except Exception:
        return f"Konnte Erinnerung nicht erstellen."
