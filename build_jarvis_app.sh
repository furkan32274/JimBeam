#!/bin/bash
# Baut Jarvis.app vollautomatisch — funktioniert ohne Xcode, nur mit Command Line Tools
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SWIFT_SRC="$DIR/JarvisApp/jarvis_main.swift"
APP="$HOME/Desktop/Jarvis.app"
MACOS_DIR="$APP/Contents/MacOS"
RES_DIR="$APP/Contents/Resources"
TMP_BIN="/tmp/JarvisExe"

echo "▶  Code aktualisieren..."
cd "$DIR"
git pull origin claude/setup-reezxy-repo-gFugx 2>/dev/null || true

# Xcode-App vorhanden? → Pfad setzen
if [ -d "/Applications/Xcode.app" ]; then
    sudo xcode-select -s /Applications/Xcode.app/Contents/Developer 2>/dev/null || true
fi

echo "▶  Swift kompilieren..."
swiftc "$SWIFT_SRC" \
    -framework Cocoa \
    -framework WebKit \
    -O \
    -o "$TMP_BIN"

echo "▶  App-Bundle erstellen..."
rm -rf "$APP"
mkdir -p "$MACOS_DIR" "$RES_DIR"

cp "$TMP_BIN" "$MACOS_DIR/Jarvis"

# Info.plist
cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>Jarvis</string>
    <key>CFBundleDisplayName</key><string>Jarvis</string>
    <key>CFBundleIdentifier</key><string>com.furkan.jarvis</string>
    <key>CFBundleExecutable</key><string>Jarvis</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleVersion</key><string>1.0</string>
    <key>CFBundleShortVersionString</key><string>1.0</string>
    <key>LSMinimumSystemVersion</key><string>13.0</string>
    <key>NSPrincipalClass</key><string>NSApplication</string>
    <key>NSMicrophoneUsageDescription</key><string>Jarvis braucht das Mikrofon für Sprachbefehle.</string>
    <key>NSAppTransportSecurity</key>
    <dict><key>NSAllowsLocalNetworking</key><true/></dict>
</dict>
</plist>
PLIST

# Icon kopieren falls vorhanden
ICON_SRC="$DIR/JarvisApp/JarvisApp/Assets.xcassets/AppIcon.appiconset/icon_256.png"
if [ -f "$ICON_SRC" ]; then
    ICONSET="/tmp/Jarvis.iconset"
    rm -rf "$ICONSET"; mkdir -p "$ICONSET"
    for s in 16 32 128 256 512; do
        sips -z $s $s "$ICON_SRC" --out "$ICONSET/icon_${s}x${s}.png" 2>/dev/null
        d=$((s*2))
        sips -z $d $d "$ICON_SRC" --out "$ICONSET/icon_${s}x${s}@2x.png" 2>/dev/null
    done
    iconutil -c icns "$ICONSET" -o "$RES_DIR/AppIcon.icns" 2>/dev/null && \
        /usr/libexec/PlistBuddy -c "Add :CFBundleIconFile string AppIcon" "$APP/Contents/Info.plist" 2>/dev/null || true
    rm -rf "$ICONSET"
fi

echo "▶  Signieren..."
codesign --force --deep --sign - "$APP" 2>/dev/null || true
xattr -cr "$APP" 2>/dev/null || true

echo ""
echo "✅  Fertig! Jarvis.app liegt auf dem Desktop."
echo "    Doppelklick → Jarvis startet + Orb öffnet sich!"
echo ""

open "$APP"
