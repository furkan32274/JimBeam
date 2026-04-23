#!/bin/bash
# Einmaliges Setup: Jarvis läuft automatisch, Desktop-Icon öffnet Orb

set -e

DIR="$HOME/JimBeam"
AGENT="$HOME/Library/LaunchAgents/com.furkan.jarvis.plist"
APP="$HOME/Desktop/Jarvis.app"

echo "▶  Beende alte Prozesse..."
launchctl unload "$AGENT" 2>/dev/null || true
pkill -f chatbot_speech_to_speech.py 2>/dev/null || true
sleep 1

echo "▶  Launch Agent erstellen (Jarvis startet automatisch)..."
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$AGENT" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.furkan.jarvis</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>-c</string>
        <string>cd $DIR && source .venv311/bin/activate && exec python chatbot_speech_to_speech.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/jarvis.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/jarvis.err</string>
</dict>
</plist>
PLIST

launchctl load -w "$AGENT"

echo "▶  Desktop App erstellen..."
rm -rf "$APP"
osacompile -o "$APP" <<'APPLESCRIPT'
on run
    -- Warten bis Jarvis-Server bereit ist
    repeat 30 times
        try
            do shell script "curl -s http://localhost:3000 > /dev/null"
            exit repeat
        on error
            delay 1
        end try
    end repeat

    tell application "Google Chrome"
        activate
        open location "http://localhost:3000"
    end tell
end run
APPLESCRIPT

echo "▶  App ad-hoc signieren (gegen 'beschädigt' Fehler)..."
codesign --force --deep --sign - "$APP" 2>/dev/null || true

echo "▶  Quarantäne-Flag entfernen..."
xattr -d com.apple.quarantine "$APP" 2>/dev/null || true

echo "▶  Icon setzen..."
ICON_PNG="$DIR/JarvisApp/JarvisApp/Assets.xcassets/AppIcon.appiconset/icon_256.png"
if [ -f "$ICON_PNG" ]; then
    ICONSET="/tmp/Jarvis.iconset"
    rm -rf "$ICONSET"
    mkdir -p "$ICONSET"
    for size in 16 32 128 256 512; do
        sips -z $size $size "$ICON_PNG" --out "$ICONSET/icon_${size}x${size}.png" 2>/dev/null
        double=$((size*2))
        sips -z $double $double "$ICON_PNG" --out "$ICONSET/icon_${size}x${size}@2x.png" 2>/dev/null
    done
    iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/applet.icns" 2>/dev/null
    rm -rf "$ICONSET"
    touch "$APP"
fi

echo ""
echo "✅  Setup komplett!"
echo ""
echo "Jarvis läuft jetzt 24/7 im Hintergrund."
echo "Doppelklick auf Jarvis.app auf Desktop → Orb öffnet sich in Chrome!"
echo ""

# Warten bis Jarvis Modelle geladen hat, dann App starten
echo "Warte bis Jarvis bereit ist..."
for i in $(seq 1 90); do
    if curl -s http://localhost:3000 > /dev/null 2>&1; then
        echo "✅  Jarvis läuft!"
        open "$APP"
        exit 0
    fi
    sleep 2
done
echo "⚠️   Jarvis braucht länger zum Starten. Schau in /tmp/jarvis.log"
