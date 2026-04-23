"""Persistent long-term memory for Jarvis — JSON storage."""

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

_LOCK = threading.Lock()
_MEMORY_FILE = Path.home() / ".jarvis_memory.json"

_DEFAULT = {
    "facts": {},          # Key-value facts: {"user_name": "Furkan", ...}
    "preferences": {},    # User preferences
    "learned": [],        # Explicitly learned items with timestamps
    "episodes": [],       # Conversation episodes / important moments
    "skills_created": [], # Self-created skills log
}


def _load() -> dict:
    if not _MEMORY_FILE.is_file():
        return dict(_DEFAULT)
    try:
        data = json.loads(_MEMORY_FILE.read_text(encoding="utf-8"))
        for k, v in _DEFAULT.items():
            data.setdefault(k, v if not isinstance(v, (dict, list)) else type(v)())
        return data
    except Exception:
        return dict(_DEFAULT)


def _save(data: dict) -> None:
    _MEMORY_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ── Public API ───────────────────────────────────────────────────────────────

def get_fact(key: str) -> Optional[Any]:
    with _LOCK:
        return _load()["facts"].get(key)


def set_fact(key: str, value: Any) -> None:
    with _LOCK:
        data = _load()
        data["facts"][key] = value
        _save(data)


def all_facts() -> dict:
    with _LOCK:
        return dict(_load()["facts"])


def forget_fact(key: str) -> bool:
    with _LOCK:
        data = _load()
        if key in data["facts"]:
            del data["facts"][key]
            _save(data)
            return True
        return False


def learn(topic: str, content: str) -> None:
    """Store a learned item with a timestamp."""
    with _LOCK:
        data = _load()
        data["learned"].append({
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "topic": topic,
            "content": content,
        })
        # Keep last 500
        data["learned"] = data["learned"][-500:]
        _save(data)


def recall(query: str, limit: int = 5) -> list[dict]:
    """Simple keyword search over learned items."""
    q = query.lower()
    with _LOCK:
        items = _load()["learned"]
    hits = [
        item for item in items
        if q in item["topic"].lower() or q in item["content"].lower()
    ]
    return hits[-limit:]


def all_learned(limit: int = 20) -> list[dict]:
    with _LOCK:
        return _load()["learned"][-limit:]


def summary_for_system_prompt(max_chars: int = 800) -> str:
    """Compact summary of known facts & recent learning for LLM context."""
    with _LOCK:
        data = _load()
    parts = []
    if data["facts"]:
        facts_str = ", ".join(f"{k}: {v}" for k, v in list(data["facts"].items())[:20])
        parts.append(f"Bekannte Fakten: {facts_str}")
    if data["learned"]:
        recent = data["learned"][-8:]
        learned_str = "; ".join(f"{x['topic']} → {x['content']}" for x in recent)
        parts.append(f"Gelernt: {learned_str}")
    out = " | ".join(parts)
    return out[:max_chars]


def log_episode(event: str) -> None:
    with _LOCK:
        data = _load()
        data["episodes"].append({
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "event": event,
        })
        data["episodes"] = data["episodes"][-200:]
        _save(data)


def log_self_improvement(description: str) -> None:
    with _LOCK:
        data = _load()
        data["skills_created"].append({
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "description": description,
        })
        data["skills_created"] = data["skills_created"][-100:]
        _save(data)
