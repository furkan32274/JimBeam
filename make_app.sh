#!/bin/bash
# ══════════════════════════════════════════════════════
#   Erstellt Jarvis.app für macOS (kein Xcode nötig)
# ══════════════════════════════════════════════════════

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP="$DIR/Jarvis.app"
MACOS="$APP/Contents/MacOS"
RES="$APP/Contents/Resources"

echo "Erstelle Jarvis.app …"

# App-Struktur
mkdir -p "$MACOS" "$RES"

# ── Launcher-Script ──────────────────────────────────
cat > "$MACOS/Jarvis" << 'LAUNCHER'
#!/bin/bash
DIR="$HOME/JimBeam"
LOG="$DIR/jarvis.log"

# Terminal mit Jarvis öffnen
osascript << EOF
tell application "Terminal"
    activate
    do script "cd '$DIR' && source .venv311/bin/activate && python chatbot_speech_to_speech.py"
end tell
EOF

# Warten bis Server läuft, dann Browser öffnen
for i in $(seq 1 30); do
    if curl -s http://localhost:3000 > /dev/null 2>&1; then
        open http://localhost:3000
        break
    fi
    sleep 2
done
LAUNCHER

chmod +x "$MACOS/Jarvis"

# ── Info.plist ───────────────────────────────────────
cat > "$APP/Contents/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>Jarvis</string>
    <key>CFBundleDisplayName</key>
    <string>Jarvis</string>
    <key>CFBundleIdentifier</key>
    <string>com.furkan.jarvis</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundleExecutable</key>
    <string>Jarvis</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>LSMinimumSystemVersion</key>
    <string>12.0</string>
    <key>NSMicrophoneUsageDescription</key>
    <string>Jarvis benötigt das Mikrofon für Spracherkennung.</string>
    <key>LSUIElement</key>
    <false/>
</dict>
</plist>
PLIST

# ── Icon kopieren ────────────────────────────────────
ICON_SRC="$DIR/JarvisApp/JarvisApp/Assets.xcassets/AppIcon.appiconset/icon_256.png"
if [ -f "$ICON_SRC" ]; then
    # PNG zu ICNS konvertieren
    ICONSET="$RES/AppIcon.iconset"
    mkdir -p "$ICONSET"
    cp "$ICON_SRC" "$ICONSET/icon_256x256.png"
    cp "$ICON_SRC" "$ICONSET/icon_128x128@2x.png"
    sips -z 128 128 "$ICON_SRC" --out "$ICONSET/icon_128x128.png" 2>/dev/null
    sips -z 64 64 "$ICON_SRC" --out "$ICONSET/icon_32x32@2x.png" 2>/dev/null
    sips -z 32 32 "$ICON_SRC" --out "$ICONSET/icon_32x32.png" 2>/dev/null
    sips -z 16 16 "$ICON_SRC" --out "$ICONSET/icon_16x16.png" 2>/dev/null
    iconutil -c icns "$ICONSET" -o "$RES/AppIcon.icns" 2>/dev/null
    rm -rf "$ICONSET"
    echo "CFBundleIconFile" >> /dev/null
    # Füge Icon zur plist hinzu
    /usr/libexec/PlistBuddy -c "Add :CFBundleIconFile string AppIcon" "$APP/Contents/Info.plist" 2>/dev/null
fi

# Quarantäne entfernen
xattr -cr "$APP" 2>/dev/null

echo ""
echo "✅  Jarvis.app wurde erstellt in: $DIR/Jarvis.app"
echo ""
echo "Jetzt:"
echo "  1. Jarvis.app in den Programme-Ordner ziehen (optional)"
echo "  2. Doppelklick auf Jarvis.app → Jarvis startet!"
echo ""

# App direkt ins Dock? (optional)
read -rp "Jarvis.app in Programme-Ordner kopieren? (j/n) " yn
if [[ "$yn" == "j" || "$yn" == "J" ]]; then
    cp -r "$APP" /Applications/Jarvis.app
    xattr -cr /Applications/Jarvis.app
    echo "✅  Jarvis.app ist jetzt in Programme!"
fi
