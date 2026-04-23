"""Telegram skill — read and send messages via Telegram Bot API.

Setup (einmalig):
  1. @BotFather auf Telegram → /newbot → Token kopieren
  2. Dem Bot eine Nachricht schicken (damit er die Chat-ID kennt)
  3. In ~/JimBeam/telegram_config.json:
     {"token": "DEIN_TOKEN", "chat_id": "DEINE_CHAT_ID"}
"""
import json
import subprocess
import urllib.request
import urllib.parse
from pathlib import Path

TRIGGERS = [
    "telegram", "nachricht schicken", "schreib mir", "schick mir",
    "telegram nachrichten", "telegram lesen", "schick eine nachricht",
]

_CFG_PATH = Path(__file__).parent.parent / "telegram_config.json"


def _cfg():
    if not _CFG_PATH.is_file():
        return None
    try:
        return json.loads(_CFG_PATH.read_text())
    except Exception:
        return None


def execute(user_input: str) -> str:
    t = user_input.lower()
    cfg = _cfg()

    if cfg is None:
        return (
            "Telegram ist noch nicht eingerichtet. Erstelle ~/JimBeam/telegram_config.json "
            "mit deinem Bot-Token und Chat-ID. Frag mich wie, wenn du Hilfe brauchst."
        )

    if any(w in t for w in ["lesen", "nachrichten", "check", "neue", "ungelesen"]):
        return _get_messages(cfg)

    # Everything else: try to send a message
    # Strip trigger words to get the actual message text
    import re
    text = re.sub(
        r'(telegram|nachricht schicken|schreib mir|schick mir|schick eine nachricht)',
        '', user_input, flags=re.IGNORECASE
    ).strip(" :,")

    if not text:
        return "Was soll ich auf Telegram schicken?"
    return _send_message(cfg, text)


def _send_message(cfg: dict, text: str) -> str:
    try:
        token   = cfg["token"]
        chat_id = cfg["chat_id"]
        url     = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = json.dumps({"chat_id": chat_id, "text": text}).encode()
        req     = urllib.request.Request(url, data=payload,
                                         headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=8)
        return f"Telegram-Nachricht gesendet: {text}"
    except Exception as e:
        return f"Telegram senden fehlgeschlagen: {e}"


def _get_messages(cfg: dict) -> str:
    try:
        token = cfg["token"]
        url   = f"https://api.telegram.org/bot{token}/getUpdates?limit=5&offset=-5"
        with urllib.request.urlopen(url, timeout=8) as r:
            data = json.loads(r.read())
        msgs = data.get("result", [])
        if not msgs:
            return "Keine neuen Telegram-Nachrichten."
        parts = []
        for m in msgs[-3:]:
            msg = m.get("message", {})
            sender = msg.get("from", {}).get("first_name", "Unbekannt")
            text   = msg.get("text", "(kein Text)")
            parts.append(f"{sender}: {text}")
        return "Letzte Telegram-Nachrichten: " + " | ".join(parts)
    except Exception as e:
        return f"Telegram lesen fehlgeschlagen: {e}"
