"""Skill: Spotify control via AppleScript"""

SKILL_NAME = "Spotify"
TRIGGERS = [
    "spotify", "musik pause", "musik weiter", "nächster song", "next song",
    "vorheriger song", "previous song", "lautstärke spotify", "was läuft",
    "play spotify", "stop spotify", "skip", "pause music", "play music",
]


def execute(user_input: str) -> str:
    import subprocess
    t = user_input.lower()

    def _osa(cmd: str) -> str:
        return subprocess.run(["osascript", "-e", cmd],
                              capture_output=True, text=True).stdout.strip()

    if any(w in t for w in ["pause", "stop", "stopp"]):
        _osa('tell application "Spotify" to pause')
        return "Spotify pausiert, Sir."

    if any(w in t for w in ["weiter", "play", "fortsetzen", "resume"]):
        _osa('tell application "Spotify" to play')
        return "Spotify läuft wieder, Sir."

    if any(w in t for w in ["nächst", "next", "skip", "überspringen"]):
        _osa('tell application "Spotify" to next track')
        return "Nächster Track, Sir."

    if any(w in t for w in ["vorherig", "previous", "zurück", "back"]):
        _osa('tell application "Spotify" to previous track')
        return "Vorheriger Track, Sir."

    if any(w in t for w in ["was läuft", "aktuell", "current", "welches lied", "welcher song"]):
        track  = _osa('tell application "Spotify" to name of current track')
        artist = _osa('tell application "Spotify" to artist of current track')
        if track:
            return f"Gerade läuft '{track}' von {artist}, Sir."
        return "Ich konnte den aktuellen Track nicht lesen, Sir."

    return None
