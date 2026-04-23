#!/bin/bash
# ══════════════════════════════════════════════════════
#   VOICE ASSISTANT — Linux Launcher
#   Doppelklick oder bash start_linux.sh zum Starten
# ══════════════════════════════════════════════════════

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

clear
echo ""
echo "  ╔══════════════════════════════════════════╗"
echo "  ║         🎙  VOICE ASSISTANT              ║"
echo "  ╚══════════════════════════════════════════╝"
echo ""

# ── Python-Umgebung einrichten falls nötig ───────────
if [ ! -d "$DIR/.venv311" ]; then
  echo "  ▶  Erstelle Python-Umgebung (.venv311)…"
  python3.11 -m venv "$DIR/.venv311"
  source "$DIR/.venv311/bin/activate"
  echo "  ▶  Installiere Abhängigkeiten…"
  pip install --upgrade pip -q
  pip install -r "$DIR/requirements_speech_to_speech.txt"
  echo "  ✅  Umgebung bereit!"
  echo ""
fi

# ── Frontend-Build falls nötig ────────────────────────
if [ ! -d "$DIR/frontend/dist" ]; then
  echo "  ▶  Erstelle UI-Build (einmalig)…"
  if ! command -v npm &>/dev/null; then
    echo "  ✗  npm nicht gefunden. Bitte Node.js installieren:"
    echo "     sudo apt install nodejs npm"
    read -rp "  Enter zum Beenden…"
    exit 1
  fi
  cd "$DIR/frontend"
  [ ! -d "node_modules" ] && npm install
  npm run build
  cd "$DIR"
  echo "  ✅  UI gebaut!"
  echo ""
fi

# ── Aufräumen beim Beenden ────────────────────────────
PYTHON_PID=""

cleanup() {
  echo ""
  echo "  Stopping Voice Assistant…"
  [ -n "$PYTHON_PID" ] && kill "$PYTHON_PID" 2>/dev/null
  fuser -k 8765/tcp 2>/dev/null
  fuser -k 3000/tcp 2>/dev/null
  echo "  Stopped. Tschüss!"
  exit 0
}
trap cleanup EXIT INT TERM

# ── Python starten ────────────────────────────────────
echo "  ▶  Lade KI-Modelle (~15 Sek.)…"
source "$DIR/.venv311/bin/activate"
python "$DIR/chatbot_speech_to_speech.py" &
PYTHON_PID=$!

# ── Warten bis HTTP-Server bereit ────────────────────
echo "  ▶  Starte UI-Server…"
for i in $(seq 1 30); do
  if ss -tlnp 2>/dev/null | grep -q ':3000' || netstat -tlnp 2>/dev/null | grep -q ':3000'; then
    break
  fi
  sleep 1
done

# ── Browser öffnen ───────────────────────────────────
if command -v xdg-open &>/dev/null; then
  xdg-open http://localhost:3000
elif command -v firefox &>/dev/null; then
  firefox http://localhost:3000 &
elif command -v chromium-browser &>/dev/null; then
  chromium-browser http://localhost:3000 &
elif command -v google-chrome &>/dev/null; then
  google-chrome http://localhost:3000 &
else
  echo "  ℹ  Kein Browser gefunden. Öffne manuell: http://localhost:3000"
fi

echo ""
echo "  ══════════════════════════════════════════"
echo "  ✅  Voice Assistant läuft!"
echo "  ✅  Browser → http://localhost:3000"
echo "  ══════════════════════════════════════════"
echo ""
echo "  Ctrl+C zum Beenden."
echo ""

wait "$PYTHON_PID"
