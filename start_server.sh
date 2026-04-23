#!/bin/bash
# ═══════════════════════════════════════════════════════════
#   JARVIS SERVER — iPhone/iPad Zugriff im gleichen WLAN
# ═══════════════════════════════════════════════════════════

cd "$(dirname "${BASH_SOURCE[0]}")"

MODE="${1:-https}"

clear
echo ""
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║      JARVIS SERVER für Mac + iPhone/iPad     ║"
echo "  ╚══════════════════════════════════════════════╝"
echo ""

if [ "$MODE" = "http" ]; then
  echo "  Modus: HTTP (nur Mac, kein Mikro auf iPhone/iPad)"
  python3 server.py
else
  echo "  Modus: HTTPS (voller Zugriff von iPhone/iPad)"
  echo ""
  python3 server.py --https
fi
