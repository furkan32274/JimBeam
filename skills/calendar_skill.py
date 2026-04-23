"""Skill: macOS Calendar — read today's events and create reminders"""

SKILL_NAME = "Kalender"
TRIGGERS = [
    "kalender", "termine", "termine heute", "was habe ich heute",
    "was steht an", "meine termine", "appointments", "calendar",
    "erinnerung erstellen", "termin erstellen", "reminder",
]


def execute(user_input: str) -> str:
    import subprocess
    t = user_input.lower()

    if any(w in t for w in ["was habe ich", "termine heute", "was steht", "zeig", "show", "lese", "read"]):
        script = """
tell application "Calendar"
    set todayEvents to {}
    set today to current date
    set startOfDay to today - (time of today)
    set endOfDay to startOfDay + 86399
    repeat with cal in calendars
        set evs to (every event of cal whose start date >= startOfDay and start date <= endOfDay)
        repeat with ev in evs
            set end of todayEvents to (summary of ev & " um " & time string of (start date of ev))
        end repeat
    end repeat
    if (count of todayEvents) = 0 then
        return "Keine Termine heute"
    end if
    return todayEvents as text
end tell
"""
        result = subprocess.run(["osascript", "-e", script],
                                capture_output=True, text=True).stdout.strip()
        if not result or result == "Keine Termine heute":
            return "Sie haben heute keine Termine, Sir."
        return f"Ihre heutigen Termine: {result}, Sir."

    if any(w in t for w in ["erstell", "create", "neu", "new", "erinnerung", "reminder"]):
        return "Um einen Termin zu erstellen öffne ich die Kalender-App für Sie, Sir."
        subprocess.run(["open", "-a", "Calendar"], check=False)

    return None
