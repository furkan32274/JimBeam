"""Claude AI backend for Jarvis — uses Anthropic API (claude-haiku-4-5 by default).

Fast, smart, multilingual. Replaces or augments the local 3B LLM.
Set ANTHROPIC_API_KEY in environment or ~/.jarvis_secrets.json to enable.
"""

import json
import os
from pathlib import Path
from typing import Iterator, Optional

_SECRETS_FILE = Path.home() / ".jarvis_secrets.json"
_client = None
_model = "claude-haiku-4-5-20251001"   # fast + cheap; swap to claude-sonnet-4-6 for more power


def _load_key() -> Optional[str]:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    if _SECRETS_FILE.is_file():
        try:
            data = json.loads(_SECRETS_FILE.read_text(encoding="utf-8"))
            return data.get("anthropic_api_key") or data.get("ANTHROPIC_API_KEY")
        except Exception:
            pass
    return None


def _get_client():
    global _client
    if _client is not None:
        return _client
    key = _load_key()
    if not key:
        return None
    try:
        import anthropic
        _client = anthropic.Anthropic(api_key=key)
        return _client
    except ImportError:
        return None


def is_available() -> bool:
    return _get_client() is not None


def stream_response(
    user_text: str,
    system_prompt: str = "",
    memory_context: str = "",
    history: Optional[list] = None,
    max_tokens: int = 512,
) -> Iterator[str]:
    """Stream text chunks from Claude. Yields text deltas as they arrive."""
    client = _get_client()
    if not client:
        return

    sys_parts = [system_prompt] if system_prompt else []
    if memory_context:
        sys_parts.append(f"\n[Langzeitgedächtnis: {memory_context}]")
    full_system = "".join(sys_parts)

    messages = []
    if history:
        for turn in history[-(20):]:
            if turn.get("role") in ("user", "assistant"):
                messages.append({"role": turn["role"], "content": turn.get("content", "")})
    messages.append({"role": "user", "content": user_text})

    try:
        with client.messages.stream(
            model=_model,
            max_tokens=max_tokens,
            system=full_system,
            messages=messages,
        ) as stream:
            for text in stream.text_stream:
                yield text
    except Exception as e:
        print(f"[Claude] Fehler: {e}", flush=True)


def ask(
    user_text: str,
    system_prompt: str = "",
    memory_context: str = "",
    history: Optional[list] = None,
    max_tokens: int = 512,
) -> Optional[str]:
    """Single-shot response from Claude (non-streaming)."""
    client = _get_client()
    if not client:
        return None

    sys_parts = [system_prompt] if system_prompt else []
    if memory_context:
        sys_parts.append(f"\n[Langzeitgedächtnis: {memory_context}]")
    full_system = "".join(sys_parts)

    messages = []
    if history:
        for turn in history[-(20):]:
            if turn.get("role") in ("user", "assistant"):
                messages.append({"role": turn["role"], "content": turn.get("content", "")})
    messages.append({"role": "user", "content": user_text})

    try:
        resp = client.messages.create(
            model=_model,
            max_tokens=max_tokens,
            system=full_system,
            messages=messages,
        )
        return resp.content[0].text.strip()
    except Exception as e:
        print(f"[Claude] Fehler: {e}", flush=True)
        return None
