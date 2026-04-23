#!/bin/bash
# Richtet Jarvis für Handy & iPad ein — automatisch
# Gleiches WLAN: sofort nutzen
# Von überall (unterwegs): Tailscale installieren

set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ""
echo "══════════════════════════════════════════════"
echo "   Jarvis Mobile Setup"
echo "══════════════════════════════════════════════"
echo ""

# Lokale IP ermitteln
LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "unbekannt")

echo "▶  Mac lokale IP: $LOCAL_IP"
echo ""
echo "──────────────────────────────────────────────"
echo "  IM HEIMNETZ (gleiches WLAN):"
echo "──────────────────────────────────────────────"
echo "  Öffne auf Handy/iPad im Browser:"
echo ""
echo "  http://$LOCAL_IP:3000"
echo ""
echo "  (Jarvis muss laufen: cd ~/JimBeam && bash start.command)"
echo ""

# Prüfe ob Tailscale bereits installiert
if command -v tailscale &>/dev/null; then
    echo "──────────────────────────────────────────────"
    echo "  TAILSCALE (von überall erreichbar):"
    echo "──────────────────────────────────────────────"
    TS_IP=$(tailscale ip -4 2>/dev/null || echo "")
    if [ -n "$TS_IP" ]; then
        echo "  ✅  Tailscale läuft! Deine Adresse:"
        echo ""
        echo "  http://$TS_IP:3000"
        echo ""
        echo "  → Installiere Tailscale auf Handy/iPad (kostenlos)"
        echo "  → Mit demselben Account einloggen"
        echo "  → Diese URL im Browser öffnen"
    else
        echo "  Tailscale installiert aber nicht verbunden."
        echo "  Starte: tailscale up"
    fi
else
    echo "──────────────────────────────────────────────"
    echo "  VON ÜBERALL (Schule, unterwegs etc.):"
    echo "──────────────────────────────────────────────"
    echo "  Tailscale installieren (kostenlos, kein Server nötig):"
    echo ""
    echo "  Installiere jetzt? (j/n)"
    read -r yn
    if [[ "$yn" == "j" || "$yn" == "J" ]]; then
        echo "▶  Tailscale installieren..."
        if ! command -v brew &>/dev/null; then
            echo "❌  Homebrew nicht gefunden. Installiere zuerst Homebrew."
            exit 1
        fi
        brew install --cask tailscale
        echo ""
        echo "▶  Tailscale starten..."
        open -a Tailscale
        sleep 3
        tailscale up --accept-routes 2>/dev/null || true
        sleep 5
        TS_IP=$(tailscale ip -4 2>/dev/null || echo "")
        if [ -n "$TS_IP" ]; then
            echo ""
            echo "✅  Tailscale aktiv! Deine Adresse:"
            echo ""
            echo "  http://$TS_IP:3000"
            echo ""
        else
            echo "▶  Bitte im Browser-Fenster mit deinem Account einloggen."
            echo "   Danach diese URL auf Handy/iPad nutzen:"
            echo "   tailscale ip -4  (im Terminal)"
        fi
    fi
fi

echo ""
echo "══════════════════════════════════════════════"
echo "  AUF HANDY/IPAD:"
echo "══════════════════════════════════════════════"
echo "  1. Gleiche URL im Safari/Chrome öffnen"
echo "  2. Auf 'Teilen' → 'Zum Home-Bildschirm'"
echo "     → wird zur App auf dem Homescreen!"
echo "══════════════════════════════════════════════"
echo ""
