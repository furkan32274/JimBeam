"""Online AI connection for Jarvis — uses Pollinations AI (free, no API key).

Automatically falls back to local LLM if online is unavailable.
"""

import json
import urllib.request
import urllib.error
from typing import Optional

POLLINATIONS_URL = "https://text.pollinations.ai/openai"
DEFAULT_TIMEOUT  = 15
DEFAULT_MODEL    = "openai"   # backed by GPT-4o-mini on Pollinations


# Keywords that suggest a complex/current query where online AI is better
_ONLINE_TRIGGERS = [
    "erkläre", "erkläre mir", "wie funktioniert", "warum",
    "berechne", "rechne aus", "mathe",
    "code", "programmier", "schreib code",
    "übersetze", "translate",
    "gedicht", "geschichte schreiben", "essay",
    "definier", "was bedeutet",
    "vergleich", "unterschied",
    "analysier", "fasse zusammen",
]


def should_use_online(user_text: str) -> bool:
    t = user_text.lower()
    if any(kw in t for kw in _ONLINE_TRIGGERS):
        return True
    # Long complex questions → online
    if len(user_text.split()) > 15:
        return True
    return False


def ask(
    question: str,
    system_prompt: str = "",
    memory_context: str = "",
    web_context: str = "",
    history: Optional[list] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> Optional[str]:
    """Query online AI. Returns the answer text, or None on failure."""

    messages = []
    sys_parts = []
    if system_prompt:
        sys_parts.append(system_prompt)
    if memory_context:
        sys_parts.append(f"\n[Langzeitgedächtnis: {memory_context}]")
    if sys_parts:
        messages.append({"role": "system", "content": "".join(sys_parts)})

    if history:
        for turn in history[-8:]:
            if turn.get("role") in ("user", "assistant"):
                messages.append({"role": turn["role"], "content": turn.get("content", "")})

    user_content = question
    if web_context:
        user_content = f"{question}\n\n[Aktuelle Web-Suchergebnisse:\n{web_context}]"
    messages.append({"role": "user", "content": user_content})

    payload = {
        "messages": messages,
        "model": DEFAULT_MODEL,
        "jsonMode": False,
    }

    try:
        req = urllib.request.Request(
            POLLINATIONS_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"].strip()
    except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as e:
        print(f"[OnlineAI] fehlgeschlagen: {e}", flush=True)
        return None


def is_reachable(timeout: int = 3) -> bool:
    try:
        urllib.request.urlopen("https://text.pollinations.ai", timeout=timeout)
        return True
    except Exception:
        return False
