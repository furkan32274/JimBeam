"""
Jarvis Skill Manager
────────────────────
Dynamically loads, saves and executes skills from the skills/ folder.
Each skill is a .py file with TRIGGERS (list) and execute(user_input) -> str.
"""

import importlib.util
import re
from pathlib import Path
from typing import Optional

SKILLS_DIR = Path(__file__).parent / "skills"

_loaded: dict = {}


def load_all() -> None:
    SKILLS_DIR.mkdir(exist_ok=True)
    (SKILLS_DIR / "__init__.py").touch()
    _loaded.clear()
    for path in sorted(SKILLS_DIR.glob("*.py")):
        if path.name.startswith("_"):
            continue
        _load_file(path)
    if _loaded:
        print(f"[SKILL] {len(_loaded)} skill(s) loaded: {', '.join(_loaded)}")
    else:
        print("[SKILL] No custom skills yet — say 'Jarvis, lern wie du ...' to teach me.")


def _load_file(path: Path) -> bool:
    try:
        spec = importlib.util.spec_from_file_location(path.stem, path)
        mod  = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if hasattr(mod, "TRIGGERS") and hasattr(mod, "execute"):
            _loaded[path.stem] = mod
            return True
    except Exception as e:
        print(f"[SKILL] Failed to load {path.name}: {e}")
    return False


def save_and_load(name: str, code: str) -> bool:
    SKILLS_DIR.mkdir(exist_ok=True)
    (SKILLS_DIR / "__init__.py").touch()
    safe = re.sub(r"[^\w]", "_", name.lower().strip())[:40]
    path = SKILLS_DIR / f"{safe}.py"
    # Strip markdown fences if LLM wrapped the code
    code = re.sub(r"```(?:python)?\n?", "", code)
    code = re.sub(r"```\n?", "", code)
    code = code.strip()
    with open(path, "w", encoding="utf-8") as f:
        f.write(code)
    return _load_file(path)


def try_execute(user_input: str) -> Optional[str]:
    t = user_input.lower()
    for name, mod in _loaded.items():
        triggers = getattr(mod, "TRIGGERS", [])
        if any(tr.lower() in t for tr in triggers):
            try:
                result = mod.execute(user_input)
            except Exception as e:
                # Log technical error to console, speak a friendly German message
                print(f"[SKILL] '{name}' Fehler: {e}", flush=True)
                continue
            # Empty/None result → skill chose not to handle this input, try next or fall through
            if result is None:
                continue
            text = str(result).strip()
            if not text:
                continue
            return text
    return None


def list_skills() -> list[str]:
    return [getattr(mod, "SKILL_NAME", name) for name, mod in _loaded.items()]
