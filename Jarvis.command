#!/bin/bash
cd ~/JimBeam
source .venv311/bin/activate

# Jarvis im Hintergrund starten und auf localhost:3000 warten
python chatbot_speech_to_speech.py &
JARVIS_PID=$!

echo "Jarvis startet..."
for i in $(seq 1 40); do
    if curl -s http://localhost:3000 > /dev/null 2>&1; then
        osascript -e 'tell application "Google Chrome" to open location "http://localhost:3000"'
        osascript -e 'tell application "Google Chrome" to activate'
        break
    fi
    sleep 1
done

# Warten bis Jarvis beendet wird
wait $JARVIS_PID
