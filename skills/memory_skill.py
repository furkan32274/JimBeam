"""Memory skill — learn, remember, and recall facts on demand.

Triggers:
  - "Merke dir: X"           → store as fact
  - "Lerne: X ist Y"         → store with topic Y
  - "Was weißt du über X?"   → recall
  - "Vergiss X"              → forget
  - "Was hast du gelernt?"   → list recent learned items
"""
import re
import sys
import os

# Make parent dir importable so we can "import memory"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import memory

TRIGGERS = [
    "merke dir", "merk dir", "speicher", "behalte",
    "lerne", "lern", "notier dir",
    "was weißt du über", "weißt du was über", "erinnere dich an",
    "vergiss", "lösche die info",
    "was hast du gelernt", "was weißt du alles",
]


def execute(user_input: str) -> str:
    t = user_input.strip()
    low = t.lower()

    # ── Forget ──────────────────────────────────────────────
    if low.startswith("vergiss") or "lösche die info" in low:
        key = re.sub(r'^(vergiss|lösche die info( über)?)', '', t, flags=re.IGNORECASE).strip(" :,.?!")
        if memory.forget_fact(key):
            return f"Vergessen: {key}"
        return f"Ich hatte keine Info über '{key}'."

    # ── Recall ──────────────────────────────────────────────
    if "was weißt du über" in low or "weißt du was über" in low or "erinnere dich an" in low:
        m = re.search(r'(?:was weißt du über|weißt du was über|erinnere dich an)\s+(.+?)[?.!]?$', t, re.IGNORECASE)
        if not m:
            return "Worüber soll ich nachdenken?"
        query = m.group(1).strip()

        fact = memory.get_fact(query)
        if fact:
            return f"{query}: {fact}"

        hits = memory.recall(query, limit=3)
        if hits:
            parts = [f"{h['topic']} → {h['content']}" for h in hits]
            return "Das weiß ich dazu: " + "; ".join(parts)
        return f"Ich weiß nichts über '{query}'. Sag mir was, dann merke ich es mir."

    # ── List learned ────────────────────────────────────────
    if "was hast du gelernt" in low or "was weißt du alles" in low:
        items = memory.all_learned(limit=10)
        facts = memory.all_facts()
        parts = []
        if facts:
            parts.append(f"Fakten: {', '.join(list(facts.keys())[:10])}")
        if items:
            parts.append(f"Zuletzt gelernt: " + "; ".join(x['topic'] for x in items))
        return " | ".join(parts) if parts else "Ich habe noch nichts gelernt."

    # ── Learn / Remember ────────────────────────────────────
    # "merke dir: X" or "lerne: X"
    m = re.match(r'^(?:merke?\s+dir|speicher|behalte|lerne?|notier\s+dir)[:\s]+(.+)$', t, re.IGNORECASE)
    if not m:
        return ""   # not a memory command — fall through to LLM
    content = m.group(1).strip(" .!?")

    # Try to parse "X ist Y" form → key-value fact
    kv = re.match(r'^(.+?)\s+ist\s+(.+)$', content, re.IGNORECASE)
    if kv:
        key = kv.group(1).strip().lower()
        val = kv.group(2).strip()
        memory.set_fact(key, val)
        return f"Gespeichert: {key} ist {val}."

    # Fallback: free-form learned item with topic = first 3 words
    words = content.split()
    topic = " ".join(words[:3])
    memory.learn(topic, content)
    return f"Gemerkt: {content}"
