#!/bin/bash
# Baut Jarvis.app vollautomatisch und legt sie auf den Desktop
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT="$DIR/JarvisApp/JarvisApp.xcodeproj"
BUILD_DIR="/tmp/JarvisBuild"
DEST="$HOME/Desktop/Jarvis.app"

echo "▶  Jarvis App wird gebaut..."

# Xcode Command Line Tools prüfen
if ! command -v xcodebuild &>/dev/null; then
    echo "▶  Installiere Xcode Command Line Tools..."
    xcode-select --install
    echo ""
    echo "⚠️  Bitte warte bis die Installation fertig ist, dann starte dieses Script nochmal."
    exit 1
fi

# Code updaten
echo "▶  Code aktualisieren..."
cd "$DIR"
git pull origin claude/setup-reezxy-repo-gFugx 2>/dev/null || true

# Alten Build löschen
rm -rf "$BUILD_DIR"

# App bauen (ohne Apple-Konto, ad-hoc signiert)
echo "▶  Kompiliere Jarvis.app (dauert ~30 Sekunden)..."
xcodebuild \
    -project "$PROJECT" \
    -scheme Jarvis \
    -configuration Release \
    -derivedDataPath "$BUILD_DIR" \
    CODE_SIGN_IDENTITY="-" \
    CODE_SIGNING_REQUIRED=NO \
    CODE_SIGNING_ALLOWED=NO \
    DEVELOPMENT_TEAM="" \
    build 2>&1 | grep -E "(error:|warning:|Build succeeded|Build FAILED|▶|✅|❌)" || true

# Gebaute App finden
BUILT_APP=$(find "$BUILD_DIR" -name "Jarvis.app" -maxdepth 6 | head -1)

if [ -z "$BUILT_APP" ]; then
    echo "❌  Build fehlgeschlagen. Vollständige Ausgabe:"
    xcodebuild \
        -project "$PROJECT" \
        -scheme Jarvis \
        -configuration Release \
        -derivedDataPath "$BUILD_DIR" \
        CODE_SIGN_IDENTITY="-" \
        CODE_SIGNING_REQUIRED=NO \
        CODE_SIGNING_ALLOWED=NO \
        DEVELOPMENT_TEAM="" \
        build 2>&1 | tail -30
    exit 1
fi

echo "▶  App auf Desktop kopieren..."
rm -rf "$DEST"
cp -r "$BUILT_APP" "$DEST"

# Ad-hoc signieren (verhindert "beschädigt"-Fehler)
echo "▶  App signieren..."
codesign --force --deep --sign - "$DEST" 2>/dev/null || true
xattr -cr "$DEST" 2>/dev/null || true

echo ""
echo "✅  Fertig! Jarvis.app ist auf deinem Desktop."
echo ""
echo "Doppelklick auf Jarvis.app → Orb öffnet sich direkt im Fenster!"
echo ""

# Direkt starten
open "$DEST"
