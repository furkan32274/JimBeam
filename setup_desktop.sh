#!/bin/bash
# ══════════════════════════════════════════════════════
#   Jarvis Desktop Setup — einmal ausführen, für immer
# ══════════════════════════════════════════════════════

DIR="$HOME/JimBeam"
APP="$HOME/Desktop/Jarvis.app"

echo "Erstelle Jarvis Desktop App..."

# Alte Version löschen
rm -rf "$APP"

# AppleScript App erstellen
osacompile -o "$APP" << 'APPLESCRIPT'
on run
    -- Alten Prozess beenden falls läuft
    do shell script "pkill -f chatbot_speech_to_speech.py; sleep 1; true"

    -- Jarvis starten
    do shell script "cd $HOME/JimBeam && source .venv311/bin/activate && nohup python chatbot_speech_to_speech.py > /tmp/jarvis.log 2>&1 &"

    -- Warten bis Server bereit
    set ready to false
    repeat 40 times
        try
            do shell script "curl -s http://localhost:3000 > /dev/null"
            set ready to true
            exit repeat
        end try
        delay 1
    end repeat

    -- Chrome öffnen
    tell application "Google Chrome"
        activate
        open location "http://localhost:3000"
    end tell
end run
APPLESCRIPT

# Quarantäne entfernen damit macOS nicht blockiert
xattr -cr "$APP"

# Icon setzen
ICON="$DIR/JarvisApp/JarvisApp/Assets.xcassets/AppIcon.appiconset/icon_256.png"
if [ -f "$ICON" ]; then
    ICONSET="/tmp/Jarvis.iconset"
    mkdir -p "$ICONSET"
    sips -z 16 16 "$ICON" --out "$ICONSET/icon_16x16.png" 2>/dev/null
    sips -z 32 32 "$ICON" --out "$ICONSET/icon_16x16@2x.png" 2>/dev/null
    sips -z 32 32 "$ICON" --out "$ICONSET/icon_32x32.png" 2>/dev/null
    sips -z 64 64 "$ICON" --out "$ICONSET/icon_32x32@2x.png" 2>/dev/null
    sips -z 128 128 "$ICON" --out "$ICONSET/icon_128x128.png" 2>/dev/null
    sips -z 256 256 "$ICON" --out "$ICONSET/icon_128x128@2x.png" 2>/dev/null
    cp "$ICON" "$ICONSET/icon_256x256.png"
    iconutil -c icns "$ICONSET" -o "/tmp/JarvisIcon.icns" 2>/dev/null
    cp "/tmp/JarvisIcon.icns" "$APP/Contents/Resources/droplet.icns" 2>/dev/null
    rm -rf "$ICONSET"
fi

echo ""
echo "✅  Jarvis.app ist auf deinem Desktop!"
echo "    Doppelklick → Jarvis startet → Chrome öffnet sich automatisch"
echo ""

# Direkt starten?
read -rp "Jetzt sofort starten? (j/n) " yn
if [[ "$yn" == "j" || "$yn" == "J" ]]; then
    open "$APP"
fi
