"""Skill: File operations — search, rename, move files"""

SKILL_NAME = "Dateiverwaltung"
TRIGGERS = [
    "datei suchen", "finde datei", "suche datei", "find file", "search file",
    "datei umbenennen", "rename file", "datei verschieben", "move file",
    "datei löschen", "delete file", "öffne ordner", "open folder",
    "dateien in", "zeig dateien",
]


def execute(user_input: str) -> str:
    import subprocess
    import os
    t = user_input.lower()

    if any(w in t for w in ["suche", "finde", "find", "search"]):
        # Extract search term (basic)
        for keyword in ["suche nach", "finde", "find file", "search for"]:
            if keyword in t:
                term = t.split(keyword)[-1].strip().split()[0] if t.split(keyword)[-1].strip() else ""
                if term:
                    result = subprocess.run(
                        ["find", os.path.expanduser("~"), "-name", f"*{term}*",
                         "-maxdepth", "5", "-not", "-path", "*/.*"],
                        capture_output=True, text=True, timeout=10
                    ).stdout.strip()
                    lines = result.splitlines()[:5]
                    if lines:
                        return f"Gefunden: {', '.join(lines)}, Sir."
                    return f"Keine Datei mit '{term}' gefunden, Sir."

    if any(w in t for w in ["schreibtisch", "desktop", "downloads", "dokumente", "documents"]):
        folder_map = {
            "schreibtisch": "~/Desktop", "desktop": "~/Desktop",
            "downloads": "~/Downloads",
            "dokumente": "~/Documents", "documents": "~/Documents",
        }
        for key, path in folder_map.items():
            if key in t:
                subprocess.run(["open", os.path.expanduser(path)], check=False)
                return f"Ich öffne {key.capitalize()} für Sie, Sir."

    return None
