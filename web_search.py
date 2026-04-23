"""DuckDuckGo web search for Jarvis — kein API-Key nötig."""

import re
from typing import Optional

_TRIGGERS = [
    # Deutsch
    "heute", "aktuell", "jetzt", "momentan", "gerade",
    "news", "nachrichten", "neuigkeiten", "schlagzeilen",
    "wetter", "temperatur", "grad",
    "such", "google", "schau nach", "finde raus", "im internet",
    "wie viel kostet", "preis", "kurs", "aktie",
    "was passiert", "was ist passiert", "neueste", "neuester",
    "wer gewann", "ergebnis", "score", "live",
    "öffnungszeiten", "adresse von",
    # Englisch
    "today", "right now", "currently", "latest", "recent",
    "search", "look up", "find out", "weather",
    "how much", "price of", "stock", "score",
]

# Eigene Domäne (Zeit, Wissen aus LLM) — kein Search nötig
_NO_SEARCH = [
    "wie geht", "wie heißt du", "was kannst du",
    "erkläre", "erkläre mir", "was bedeutet",
    "schreib", "schreibe", "formulier", "übersetze",
    "was hast du gesagt", "wiederhol", "nochmal",
]


def needs_search(text: str) -> bool:
    t = text.lower()
    if any(skip in t for skip in _NO_SEARCH):
        return False
    return any(trigger in t for trigger in _TRIGGERS)


def search(query: str, max_results: int = 4) -> Optional[str]:
    """Gibt formatierte Suchergebnisse zurück oder None bei Fehler."""
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        if not results:
            return None
        lines = [f"- {r['title']}: {r['body']}" for r in results]
        return "\n".join(lines)
    except Exception as e:
        print(f"[Web] Suche fehlgeschlagen: {e}", flush=True)
        return None
