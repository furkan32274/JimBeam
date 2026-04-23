"""Email skill — reads and sends emails via macOS Mail app (AppleScript)."""
import subprocess

TRIGGERS = [
    "email", "mail", "e-mail", "emails lesen", "ungelesene",
    "neue nachrichten", "schreib eine mail", "send mail",
    "nachrichten in mail",
]

def execute(user_input: str) -> str:
    t = user_input.lower()

    if any(w in t for w in ["lesen", "ungelesen", "neue", "check", "read"]):
        return _read_emails()

    if any(w in t for w in ["schreib", "sende", "send", "write", "compose"]):
        return "Sage: 'Schreib eine Mail an [Name], Betreff [Betreff], Inhalt [Text]' — noch nicht vollständig implementiert."

    return _read_emails()


def _read_emails() -> str:
    script = '''
    tell application "Mail"
        set unread_msgs to (messages of inbox whose read status is false)
        set count_unread to count of unread_msgs
        if count_unread is 0 then
            return "Keine ungelesenen Emails."
        end if
        set result_text to "Du hast " & count_unread & " ungelesene Email"
        if count_unread > 1 then set result_text to result_text & "s"
        set result_text to result_text & ": "
        set shown to 0
        repeat with msg in unread_msgs
            if shown >= 3 then exit repeat
            set result_text to result_text & (sender of msg) & " schreibt über "" & (subject of msg) & "". "
            set shown to shown + 1
        end repeat
        return result_text
    end tell
    '''
    try:
        out = subprocess.check_output(["osascript", "-e", script], timeout=10).decode().strip()
        return out
    except Exception:
        return "Mail konnte nicht gelesen werden. Ist die Mail-App installiert?"
