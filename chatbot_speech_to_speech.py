"""
Local Voice Assistant — Jarvis Edition
─────────────────────────────────────────────────────────────────────────────
LLM  : Llama-3.2-3B-Instruct Q4_K_M via llama-cpp-python (Apple Metal GPU)
TTS  : Kokoro-82M ONNX  ·  voice: am_fenrir (male)  ·  ~200 ms/sentence
STT  : faster-whisper 'base' + int8 quantisation + VAD filter
─────────────────────────────────────────────────────────────────────────────
Pipeline   : LLM-stream → TTS-stream → SeamlessPlayer (zero-gap audio)
System cmds: volume, apps, screenshot, timer — executed locally, no LLM
"""

import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

import numpy as np
import sounddevice as sd
import webrtcvad

import ws_server
import skill_manager
import web_search
import memory
import online_ai
import claude_ai

# ── Data directory ────────────────────────────────────────────────────────────
# When running inside the macOS app, the Swift wrapper sets JARVIS_DATA_DIR to
# ~/Library/Application Support/Jarvis/ so models and config survive app updates.
# When running locally (start.command / CLI), falls back to the script directory.
_DATA_DIR = Path(os.environ["JARVIS_DATA_DIR"]) if "JARVIS_DATA_DIR" in os.environ else Path(__file__).parent

# ── Constants ─────────────────────────────────────────────────────────────────
# config.json: user's copy in data dir first, bundled default as fallback
CONFIG_PATH = _DATA_DIR / "config.json"
if not CONFIG_PATH.is_file():
    CONFIG_PATH = Path(__file__).parent / "config.json"
SAMPLE_RATE  = 16_000
TTS_RATE     = 24_000
FRAME_MS     = 30
FRAME_SIZE   = int(SAMPLE_RATE * FRAME_MS / 1_000)

# Adaptive silence: short for quick commands, longer once you've been speaking a while
SILENCE_CUTOFF_SHORT_MS  = 520
SILENCE_CUTOFF_LONG_MS   = 950
LONG_SPEECH_THRESHOLD_MS = 2_500   # use long cutoff after 2.5 s of speech

PLAYER_BLOCKSIZE = 4_096

SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
CLAUSE_RE   = re.compile(r"(?<=[,;:])\s+")
MIN_CLAUSE_WORDS = 8


# ── Helpers ───────────────────────────────────────────────────────────────────
def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  Downloading {dest.name} …", flush=True)

    def _hook(count: int, block: int, total: int) -> None:
        pct = min(100, count * block * 100 // max(total, 1))
        sys.stdout.write(f"\r  {pct:3d}%")
        sys.stdout.flush()

    urllib.request.urlretrieve(url, dest, _hook)
    print()


def _clean(text: str) -> str:
    """Strip LLM artefacts: <think> tags, markdown symbols, excess newlines."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\*+", "", text)
    text = re.sub(r"#+\s*", "", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


# ── Seamless audio player ──────────────────────────────────────────────────────
class SeamlessPlayer:
    """
    Plays a continuous stream of float32 mono audio fed from a queue.
    Uses sounddevice.OutputStream with a callback so chunks are joined
    at sample level — no gap, click, or silence between sentences.
    """

    def __init__(self, sample_rate: int = TTS_RATE) -> None:
        self._sr      = sample_rate
        self._buf     = np.empty(0, dtype=np.float32)
        self._lock    = threading.Lock()
        self._done    = threading.Event()
        self._feeding = True
        self._stream: Optional[sd.OutputStream] = None

    def start(self) -> None:
        self._done.clear()
        self._feeding = True
        self._stream = sd.OutputStream(
            samplerate=self._sr,
            channels=1,
            dtype="float32",
            blocksize=PLAYER_BLOCKSIZE,
            callback=self._callback,
        )
        self._stream.start()

    def feed(self, audio: np.ndarray) -> None:
        with self._lock:
            self._buf = np.concatenate((self._buf, audio.ravel()))

    def mark_done(self) -> None:
        self._feeding = False

    def wait(self) -> None:
        self._done.wait()
        self._close()

    def stop(self) -> None:
        self._feeding = False
        self._done.set()
        self._close()

    def _close(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    def _callback(self, outdata: np.ndarray, frames: int, _time, _status) -> None:
        with self._lock:
            have = len(self._buf)
            if have >= frames:
                outdata[:, 0] = self._buf[:frames]
                self._buf = self._buf[frames:]
            elif have > 0:
                outdata[:have, 0] = self._buf
                outdata[have:, 0] = 0.0
                self._buf = np.empty(0, dtype=np.float32)
                if not self._feeding:
                    threading.Timer(0.05, self._done.set).start()
            else:
                outdata[:, 0] = 0.0
                if not self._feeding:
                    self._done.set()


# ── Voice Assistant ────────────────────────────────────────────────────────────
class VoiceAssistant:
    def __init__(self) -> None:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            self.cfg: dict = json.load(f)

        self._load_llm()
        self._load_tts()
        self._load_stt()
        if claude_ai.is_available():
            print("[AI] Claude API aktiv — Jarvis nutzt Claude als primäres Gehirn")
        else:
            print("[AI] Kein ANTHROPIC_API_KEY — nutze lokales LLM (Claude via ~/.jarvis_secrets.json aktivierbar)")

        self.vad = webrtcvad.Vad(3)
        self._audio_q: queue.Queue[bytes] = queue.Queue()
        self.history: list[dict] = []
        self.system_prompt: str = self.cfg["llm"].get(
            "prompt_behavior",
            "You are Jarvis, a helpful and concise voice assistant. "
            "Your name is Jarvis. The user's name is Felix. "
            "Address the user naturally as 'Sir' or 'Felix' when it fits. "
            "If asked for your name, say your name is Jarvis. "
            "Keep answers brief and conversational. No bullet points or markdown.",
        )
        self._stop_speak = threading.Event()
        skill_manager.load_all()
        self._text_queue: queue.Queue = queue.Queue()
        self._turn_lock = threading.Lock()
        ws_server.set_chat_callback(self._text_queue.put)
        # Start chat processing thread
        threading.Thread(target=self._chat_loop, daemon=True, name="chat-input").start()

    # ── Loading ───────────────────────────────────────────────────────────────

    def _load_llm(self) -> None:
        from huggingface_hub import hf_hub_download, try_to_load_from_cache
        from llama_cpp import Llama

        c = self.cfg["llm"]
        repo_id  = c["repo_id"]
        filename = c["filename"]
        print(f"[LLM] Loading {repo_id}  ({filename}) …")

        cached = try_to_load_from_cache(repo_id=repo_id, filename=filename)
        if cached and Path(cached).is_file():
            model_path = cached
            print("[LLM] Found in local cache — skipping network.")
        else:
            # try_to_load_from_cache missed it — try local_files_only before going to the network
            try:
                model_path = hf_hub_download(
                    repo_id=repo_id, filename=filename, local_files_only=True
                )
                print("[LLM] Found in HF cache (local_files_only) — skipping network.")
            except Exception:
                print("[LLM] Not cached — downloading from HuggingFace …")
                model_path = hf_hub_download(repo_id=repo_id, filename=filename)

        self._llm = Llama(
            model_path=str(model_path),
            n_gpu_layers=c.get("n_gpu_layers", -1),
            n_ctx=c.get("n_ctx", 4096),
            verbose=False,
        )
        self._llm_cfg = c
        print("[LLM] Ready  (Metal GPU layers active)")

    def _load_tts(self) -> None:
        """Use macOS 'say' command for TTS — native German voices, no downloads."""
        c = self.cfg["tts"]
        self._voice: str    = c.get("voice", "Markus")
        self._speed: float  = float(c.get("speed", 1.0))
        self._tts_lang: str = c.get("language", "de")

        # Verify 'say' is available (macOS)
        if subprocess.run(["which", "say"], capture_output=True).returncode != 0:
            raise RuntimeError("macOS 'say' command not found — requires macOS")

        # Check that the chosen voice exists
        try:
            voices_out = subprocess.run(
                ["say", "-v", "?"], capture_output=True, text=True, timeout=5
            ).stdout
            voices_available = [line.split()[0] for line in voices_out.splitlines() if line]
            if self._voice not in voices_available:
                german_voices = [v for v in voices_available
                                 if any(g in voices_out for g in [f"{v}  ", f"{v}\t"])
                                 and "de_" in voices_out.split(v, 1)[-1][:60]]
                # Pick first available German voice as fallback
                german_fallback = next(
                    (v for v in voices_available
                     if any(name in v for name in ["Markus", "Anna", "Helena", "Petra", "Yannick"])),
                    "Markus"
                )
                print(f"[TTS] Voice '{self._voice}' nicht verfügbar — nutze '{german_fallback}'")
                self._voice = german_fallback
        except Exception:
            pass

        print(f"[TTS] Ready  (macOS say, voice: {self._voice})")

    def _load_stt(self) -> None:
        from faster_whisper import WhisperModel

        c    = self.cfg["stt"]
        size = c.get("model_size", "base")
        print(f"[STT] Loading faster-whisper '{size}' …")
        try:
            # Always try local cache first — avoids HuggingFace network call when offline.
            self._stt = WhisperModel(
                size, device="cpu", compute_type="int8", local_files_only=True
            )
        except Exception:
            # Model not in local cache yet — download it (requires internet).
            print(f"[STT] Model not cached — downloading faster-whisper '{size}' …")
            self._stt = WhisperModel(
                size, device="cpu", compute_type="int8", local_files_only=False
            )
        self._lang: str = c.get("language", "en")
        print("[STT] Ready")

    # ── Audio helpers ─────────────────────────────────────────────────────────

    def _drain_q(self) -> None:
        """Discard stale frames left in the audio queue."""
        while not self._audio_q.empty():
            try:
                self._audio_q.get_nowait()
            except queue.Empty:
                break

    def record_audio(self) -> bytes:
        """
        Record a full user utterance.
        Uses adaptive silence: short commands cut off at 600 ms,
        longer speech (> 2.5 s) gets 950 ms — so you can finish long sentences.
        """
        while ws_server.is_muted():
            ws_server.set_state("idle")
            time.sleep(0.1)

        self._drain_q()
        ws_server.set_state("listening")
        print("🎤  Listening …", flush=True)
        buf        = b""
        silence_ms = 0
        speech_ms  = 0
        speaking   = False

        def _cb(indata: np.ndarray, *_) -> None:
            self._audio_q.put(bytes(indata))

        with sd.RawInputStream(
            samplerate=SAMPLE_RATE,
            blocksize=FRAME_SIZE,
            dtype="int16",
            channels=1,
            callback=_cb,
        ):
            while True:
                if ws_server.is_muted():
                    return b""
                frame = self._audio_q.get()
                if self.vad.is_speech(frame, SAMPLE_RATE):
                    buf       += frame
                    silence_ms = 0
                    speaking   = True
                    speech_ms += FRAME_MS
                elif speaking:
                    buf        += frame
                    silence_ms += FRAME_MS
                    cutoff = (
                        SILENCE_CUTOFF_LONG_MS
                        if speech_ms >= LONG_SPEECH_THRESHOLD_MS
                        else SILENCE_CUTOFF_SHORT_MS
                    )
                    if silence_ms > cutoff:
                        break
        return buf

    # ── STT ───────────────────────────────────────────────────────────────────

    def transcribe(self, audio_bytes: bytes) -> str:
        audio = np.frombuffer(audio_bytes, dtype="int16").astype("float32") / 32_768.0
        segments, _ = self._stt.transcribe(
            audio,
            language=self._lang,
            beam_size=5,
            temperature=0,                      # deterministic, no random sampling
            condition_on_previous_text=False,   # no hallucination from prior context
            vad_filter=True,
            vad_parameters={
                "min_silence_duration_ms": 300,
                "speech_pad_ms": 200,           # keep a bit of audio around speech edges
            },
        )
        return " ".join(s.text.strip() for s in segments).strip()

    # ── TTS (macOS say) ───────────────────────────────────────────────────────

    def _say(self, text: str) -> None:
        """Speak text via macOS 'say' — blocks until finished."""
        if not text:
            return
        rate = int(200 * self._speed)   # words per minute
        result = subprocess.run(
            ["say", "-v", self._voice, "-r", str(rate), text],
            check=False, capture_output=True,
        )
        if result.returncode != 0:
            # Voice not installed — fall back to system default voice
            subprocess.run(["say", "-r", str(rate), text], check=False)

    def speak_direct(self, text: str) -> None:
        """Speak text immediately — no LLM involved."""
        ws_server.set_state("speaking")
        try:
            self._say(text)
        finally:
            ws_server.set_state("idle")

    def stop_speaking(self) -> None:
        self._stop_speak.set()

    # ── System commands ───────────────────────────────────────────────────────

    # Spoken folder names → filesystem paths
    _FINDER_FOLDERS: dict[str, str] = {
        "downloads":    "~/Downloads",
        "download":     "~/Downloads",
        "desktop":      "~/Desktop",
        "documents":    "~/Documents",
        "document":     "~/Documents",
        "home":         "~",
        "pictures":     "~/Pictures",
        "picture":      "~/Pictures",
        "movies":       "~/Movies",
        "music":        "~/Music",
        "applications": "/Applications",
    }

    # Common spoken names → exact macOS .app names
    _APP_ALIASES: dict[str, str] = {
        "safari":               "Safari",
        "chrome":               "Google Chrome",
        "google chrome":        "Google Chrome",
        "firefox":              "Firefox",
        "spotify":              "Spotify",
        "discord":              "Discord",
        "slack":                "Slack",
        "whatsapp":             "WhatsApp",
        "telegram":             "Telegram",
        "notes":                "Notes",
        "calendar":             "Calendar",
        "finder":               "Finder",
        "terminal":             "Terminal",
        "xcode":                "Xcode",
        "vs code":              "Visual Studio Code",
        "vscode":               "Visual Studio Code",
        "visual studio code":   "Visual Studio Code",
        "cursor":               "Cursor",
        "mail":                 "Mail",
        "messages":             "Messages",
        "facetime":             "FaceTime",
        "maps":                 "Maps",
        "photos":               "Photos",
        "music":                "Music",
        "podcasts":             "Podcasts",
        "system preferences":   "System Preferences",
        "system settings":      "System Settings",
        "activity monitor":     "Activity Monitor",
        "calculator":           "Calculator",
        "preview":              "Preview",
        "arc":                  "Arc",
        "figma":                "Figma",
        "notion":               "Notion",
        "zoom":                 "Zoom",
        "ChatGPT":               "ChatGPT",
        "Claude":                "Claude",
    }

    def _resolve_app_name(self, raw: str) -> str:
        """Clean up transcription noise and map spoken names to exact app names."""
        clean = re.sub(r"[^\w\s]", "", raw).strip().lower()
        clean = re.sub(r"^(?:the|a|an)\s+", "", clean)   # strip leading articles
        if clean in self._APP_ALIASES:
            return self._APP_ALIASES[clean]
        return clean.title()

    # Words that signal the captured text is NOT an app name
    _NON_APP_FIRST_WORDS = {
        "up", "down", "in", "out", "on", "off", "to", "with", "about",
        "for", "new", "my", "your", "this", "that", "some", "all", "more",
        "less", "much", "another", "any", "every", "it", "him", "her",
        "them", "us", "me", "both", "few", "many",
    }

    def _is_app_command(self, raw: str) -> bool:
        """
        Return True only if the captured text genuinely looks like an app name.
        Guards against false positives like 'open up about...' or 'close enough'.
        """
        clean = re.sub(r"[^\w\s]", "", raw).strip().lower()
        clean = re.sub(r"^(?:the|a|an)\s+", "", clean)   # strip leading articles
        if clean in self._APP_ALIASES:
            return True
        words = clean.split()
        # Only allow 1–2 word names whose first word isn't a common non-app word
        return (
            1 <= len(words) <= 2
            and bool(words)
            and words[0] not in self._NON_APP_FIRST_WORDS
        )

    def _applescript(self, script: str) -> str:
        result = subprocess.run(
            ["osascript", "-e", script], capture_output=True, text=True
        )
        return result.stdout.strip()

    # ── Clipboard helpers ─────────────────────────────────────────────────────

    # Phrases that signal "process my clipboard with the LLM"
    _CLIPBOARD_TRIGGERS = (
        "improve this", "fix this", "rewrite this", "correct this",
        "proofread this", "summarize this", "summarize the text",
        "translate this", "make this shorter", "make this longer",
        "make this more formal", "make this casual", "simplify this",
        "explain this",
    )

    def _try_augment_clipboard(self, text: str) -> tuple[str, bool]:
        """
        If the utterance is a clipboard command, read the clipboard and
        append its content to the prompt so the LLM can act on it.
        Returns (augmented_text, is_clipboard_command).
        """
        t = text.lower()
        if not any(trigger in t for trigger in self._CLIPBOARD_TRIGGERS):
            return text, False
        clipboard = subprocess.run(
            ["pbpaste"], capture_output=True, text=True
        ).stdout.strip()
        if not clipboard:
            return text + "\n(Note: clipboard is empty)", False
        return f"{text}\n\nClipboard content:\n{clipboard}", True

    def _copy_to_clipboard(self, text: str) -> None:
        subprocess.run(["pbcopy"], input=text.encode(), check=False)

    def _timer_callback(self, seconds: int, label: str) -> None:
        time.sleep(seconds)
        msg = f"Dein Timer für {label} ist abgelaufen."
        print(f"\n⏰  {msg}", flush=True)
        subprocess.run(
            ["osascript", "-e",
             f'display notification "Timer complete!" with title "Jarvis" subtitle "{label}"'],
            check=False,
        )
        self.speak_direct(msg)

    def _generate_skill_code(self, description: str) -> str:
        prompt = (
            f"Generate a Python skill module for Jarvis voice assistant.\n"
            f"The user wants Jarvis to: {description}\n\n"
            f"Use EXACTLY this structure:\n"
            f"SKILL_NAME = \"short name\"\n"
            f"TRIGGERS = [\"keyword1\", \"keyword2\"]  # German+English keywords\n\n"
            f"def execute(user_input: str) -> str:\n"
            f"    import subprocess\n"
            f"    # Use osascript for macOS apps, subprocess for CLI\n"
            f"    # Return German response ending with 'Sir.'\n"
            f"    pass\n\n"
            f"Rules: only Python code, no markdown, use AppleScript for macOS apps, "
            f"German responses, import inside execute(), return None if not applicable."
        )
        resp = self._llm.create_chat_completion(
            messages=[
                {"role": "system", "content": "You are a Python code generator. Output only valid Python code, no markdown fences, no explanations."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=600,
            temperature=0.15,
            stop=["<|eot_id|>"],
            stream=False,
        )
        return resp["choices"][0]["message"]["content"]

    def _handle_system_command(self, text: str) -> Optional[str]:
        """
        Check whether `text` is a local system command.
        If yes: execute it and return the spoken response string.
        If no:  return None  (caller should send to LLM).
        """
        t = text.lower().strip()

        # ── Skills: check all learned skills first ────────────────────────────
        skill_resp = skill_manager.try_execute(text)
        if skill_resp is not None:
            return skill_resp

        # ── Self-learning: VERY specific phrasing only ────────────────────────
        # Must be explicit: "lern wie du X kannst", "bring dir bei", "erstelle skill"
        if re.search(
            r"\b(?:lern\s+(?:doch\s+)?wie\s+du|bring\s+dir\s+bei|erstelle\s+(?:einen\s+)?(?:neuen\s+)?skill|neue\s+fähigkeit\s+(?:erstellen|lernen))\b",
            t,
        ):
            print(f"[SKILL] Learning request detected: {text}")
            self.speak_direct("Verstanden. Ich generiere die neue Fähigkeit. Einen Moment bitte.")
            try:
                code = self._generate_skill_code(text)
                name_match = re.search(r"\b(?:lern|learn)\w*\s+(?:wie\s+(?:du|ich)\s+)?(.+?)(?:\s+kann(?:st)?|$)", t)
                skill_name = name_match.group(1).strip() if name_match else text[:30]
                success = skill_manager.save_and_load(skill_name, code)
                if success:
                    return f"Erledigt. Ich beherrsche jetzt '{skill_name}'. Probier's aus."
                return "Ich konnte diese Fähigkeit nicht erlernen. Beschreib es bitte genauer."
            except Exception as e:
                print(f"[SKILL] Learning failed: {e}")
                return "Beim Erlernen gab es ein Problem. Versuch es nochmal."

        # ── List skills ───────────────────────────────────────────────────────
        if re.search(r"\b(?:welche fähigkeiten|was kannst du|what can you|liste skills|list skills|deine fähigkeiten)\b", t):
            skills = skill_manager.list_skills()
            if skills:
                return f"Ich beherrsche folgende Fähigkeiten, Sir: {', '.join(skills)}."
            return "Ich habe noch keine erlernten Fähigkeiten. Sag 'Jarvis, lern wie du ... kannst' um mir etwas beizubringen."

        # ── Date & time ───────────────────────────────────────────────────────
        if re.search(r"\b(?:wie\s+(?:spät|viel\s+uhr)|uhrzeit|was\s+für\s+eine\s+zeit|time|what\s+time\s+is\s+it)\b", t):
            now = time.strftime("%H:%M")
            return f"Es ist {now} Uhr."

        if re.search(r"\b(?:welches\s+datum|welcher\s+tag|was\s+für\s+ein\s+tag|today'?s?\s+date)\b", t):
            today = time.strftime("%A, %-d. %B")
            return f"Heute ist {today}."

        # ── System info ───────────────────────────────────────────────────────
        if re.search(r"\b(?:wie\s+viel\s+(?:ram|arbeitsspeicher|speicher)|freier\s+speicher|memory\s+(?:usage|left|free))\b", t):
            try:
                vm      = subprocess.run(["vm_stat"], capture_output=True, text=True).stdout
                ps_m    = re.search(r"page size of (\d+) bytes", vm)
                page_sz = int(ps_m.group(1)) if ps_m else 16_384
                free    = int(re.search(r"Pages free:\s+(\d+)", vm).group(1))
                inact   = int(re.search(r"Pages inactive:\s+(\d+)", vm).group(1))
                avail   = round((free + inact) * page_sz / 1024 ** 3, 1)
                return f"Ungefähr {avail} Gigabyte Arbeitsspeicher verfügbar."
            except Exception:
                return "Ich konnte den Speicherstatus gerade nicht auslesen."

        if re.search(r"\b(?:cpu|prozessor(?:\s+auslastung)?)\b", t):
            try:
                top = subprocess.run(
                    ["top", "-l", "1", "-n", "0", "-s", "0"],
                    capture_output=True, text=True, timeout=6,
                ).stdout
                m2 = re.search(r"CPU usage:\s+([\d.]+)%\s+user,\s+([\d.]+)%\s+sys", top)
                if m2:
                    used = round(float(m2.group(1)) + float(m2.group(2)), 1)
                    return f"Die CPU liegt gerade bei {used} Prozent."
            except Exception:
                pass
            return "Ich konnte die CPU-Auslastung nicht lesen."

        if re.search(r"\b(?:wie\s+viel\s+(?:speicherplatz|festplatte)|freier\s+(?:speicherplatz|platz)|storage\s+left)\b", t):
            try:
                df    = subprocess.run(["df", "-h", "/"], capture_output=True, text=True).stdout.splitlines()
                parts = df[1].split()
                avail, pct = parts[3], parts[4]
                return f"{avail} frei, {pct} belegt."
            except Exception:
                return "Ich konnte den Festplattenstatus nicht lesen."

        # ── Volume query ──────────────────────────────────────────────────────
        if re.search(r"\b(?:wie\s+(?:laut|ist\s+die\s+lautstärke)|aktuelle\s+lautstärke)\b", t):
            vol   = self._applescript("output volume of (get volume settings)")
            muted = self._applescript("output muted of (get volume settings)")
            if muted == "true":
                return "Die Lautstärke ist stummgeschaltet."
            return f"Die Lautstärke ist auf {vol} Prozent."

        # ── Active app ────────────────────────────────────────────────────────
        if re.search(r"\b(?:was\s+mache?\s+ich\s+gerade|welche\s+app\s+(?:ist\s+offen|läuft)|was\s+ist\s+(?:offen|aktiv))\b", t):
            app = self._applescript(
                'tell application "System Events" to get name of first application process whose frontmost is true'
            )
            return f"Du bist gerade in {app}."

        # ── Maps navigation ───────────────────────────────────────────────────
        m = re.search(
            r"\b(?:navigier(?:e)?|route|bring\s+mich|zeig\s+mir\s+den\s+weg|navigation)\s+(?:zu|nach)\s+(.+)",
            t,
        )
        if not m:
            m = re.search(r"\bwie\s+komme?\s+ich\s+(?:zu|nach)\s+(.+)", t)
        if m:
            raw_dest = re.sub(r"[?.!,]+$", "", m.group(1).strip())
            encoded  = urllib.parse.quote(raw_dest)
            subprocess.run(["open", f"maps://?daddr={encoded}"], check=False)
            return f"Öffne Maps mit Route nach {raw_dest}."

        # ── Finder folders ────────────────────────────────────────────────────
        m = re.match(r"^(?:öffne?|zeig(?:e)?\s+mir)\s+(.+?)(?:\s+ordner)?$", t)
        if m:
            folder_key = m.group(1).strip().lower()
            if folder_key in self._FINDER_FOLDERS:
                subprocess.run(["open", self._FINDER_FOLDERS[folder_key]], check=False)
                return f"Öffne deinen {folder_key.title()}-Ordner."

        # ── Volume ────────────────────────────────────────────────────────────
        m = re.search(r"\b(?:lautstärke|volume)\s+(?:auf\s+)?(\d{1,3})\b", t)
        if m:
            vol = min(100, max(0, int(m.group(1))))
            self._applescript(f"set volume output volume {vol}")
            return f"Lautstärke auf {vol} Prozent."

        if re.search(r"\b(?:stumm\s+aus|nicht\s+mehr\s+stumm|unmute)\b", t):
            self._applescript("set volume output muted false")
            return "Stummschaltung aus."

        if re.search(r"\b(?:stumm|leise\s+stellen|mute)\b", t):
            self._applescript("set volume output muted true")
            return "Stummgeschaltet."

        if re.search(r"\b(?:lauter|mach\s+lauter|erhöh\s+die\s+lautstärke)\b", t):
            cur = self._applescript("output volume of (get volume settings)")
            new_vol = min(100, int(cur or 50) + 15)
            self._applescript(f"set volume output volume {new_vol}")
            return f"Lautstärke auf {new_vol} Prozent."

        if re.search(r"\b(?:leiser|mach\s+leiser|reduzier\s+die\s+lautstärke)\b", t):
            cur = self._applescript("output volume of (get volume settings)")
            new_vol = max(0, int(cur or 50) - 15)
            self._applescript(f"set volume output volume {new_vol}")
            return f"Lautstärke auf {new_vol} Prozent."

        # ── Screenshot ────────────────────────────────────────────────────────
        if re.search(r"\b(?:mach\s+(?:einen\s+)?screenshot|bildschirmfoto|screenshot\s+machen)\b", t):
            ts   = time.strftime("%Y%m%d_%H%M%S")
            path = Path.home() / "Desktop" / f"screenshot_{ts}.png"
            subprocess.run(["screencapture", "-x", str(path)], check=False)
            return "Screenshot auf dem Desktop gespeichert."

        # ── Timer ─────────────────────────────────────────────────────────────
        m = re.search(
            r"\b(?:timer|stell(?:e)?\s+(?:einen\s+)?timer)\s+(?:für\s+|auf\s+)?(\d+)\s*(sekunde|minute|stunde)n?\b", t
        )
        if m:
            amount = int(m.group(1))
            unit   = m.group(2)
            seconds = amount * {"sekunde": 1, "minute": 60, "stunde": 3600}[unit]
            label   = f"{amount} {unit}{'n' if amount != 1 else ''}"
            threading.Thread(
                target=self._timer_callback, args=(seconds, label), daemon=True
            ).start()
            return f"Timer läuft für {label}."

        # ── Reminder ──────────────────────────────────────────────────────────
        m = re.search(
            r"\berinner(?:e)?\s+mich\s+in\s+(\d+)\s*(sekunde|minute|stunde)n?\b", t
        )
        if m:
            amount  = int(m.group(1))
            unit    = m.group(2)
            seconds = amount * {"sekunde": 1, "minute": 60, "stunde": 3600}[unit]
            label   = f"{amount} {unit}{'n' if amount != 1 else ''}"
            threading.Thread(
                target=self._timer_callback, args=(seconds, label), daemon=True
            ).start()
            return f"Ich erinnere dich in {label}."

        # ── Open app ──────────────────────────────────────────────────────────
        m = re.search(
            r"^(?:öffne?|starte?|mach\s+auf)\s+(.+?)(?:\s+(?:app|application))?\s*$", t
        )
        if m and self._is_app_command(m.group(1)):
            app_name = self._resolve_app_name(m.group(1))
            res = subprocess.run(["open", "-a", app_name], capture_output=True)
            if res.returncode == 0:
                return f"Öffne {app_name}."
            return f"Ich konnte keine App namens {app_name} finden."

        # ── Quit app ──────────────────────────────────────────────────────────
        m = re.search(
            r"^(?:schließe?|beende?|mach\s+zu)\s+(.+?)(?:\s+(?:app|application))?\s*$", t
        )
        if m and self._is_app_command(m.group(1)):
            app_name = self._resolve_app_name(m.group(1))
            self._applescript(f'tell application "{app_name}" to quit')
            return f"Schließe {app_name}."

        # ── Orb demo ──────────────────────────────────────────────────────────
        if re.search(
            r"\b(?:zeig\s+mir\s+was|beeindruck\s+mich|mach\s+was\s+cool(?:es)?|party\s+modus)\b",
            t,
        ):
            ws_server.send_event({"action": "demo"})
            return "Pass auf."

        return None

    # ── Spinner ───────────────────────────────────────────────────────────────

    @staticmethod
    def _spinner(stop: threading.Event) -> None:
        frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        i = 0
        while not stop.is_set():
            sys.stdout.write(f"\r  Thinking {frames[i % len(frames)]}")
            sys.stdout.flush()
            i += 1
            time.sleep(0.1)
        sys.stdout.write("\r" + " " * 20 + "\r")
        sys.stdout.flush()

    # ── Turn (LLM pipeline) ───────────────────────────────────────────────────

    def _messages(self) -> list[dict]:
        max_pairs = self._llm_cfg.get("history_turns", 10)
        recent    = self.history[-(max_pairs * 2):]
        mem_ctx   = memory.summary_for_system_prompt()
        sys_prompt = self.system_prompt
        if mem_ctx:
            sys_prompt = f"{sys_prompt}\n\n[Langzeitgedächtnis: {mem_ctx}]"
        return [{"role": "system", "content": sys_prompt}] + recent

    def stream_sentences(self, user_text: str, web_context: str = ""):
        """Stream sentences from Claude (primary) or local LLM (fallback)."""
        prompt = user_text
        if web_context:
            prompt = (
                f"{user_text}\n\n"
                f"[Aktuelle Web-Suchergebnisse:\n{web_context}\n"
                f"Nutze diese Infos um aktuell und präzise zu antworten.]"
            )

        buf  = ""
        full = ""

        def _yield_buf(b: str):
            """Flush buffer by sentence/clause boundaries."""
            nonlocal buf
            parts = SENTENCE_RE.split(b)
            if len(parts) > 1:
                for sentence in parts[:-1]:
                    c = _clean(sentence)
                    if c:
                        yield c
                buf = parts[-1]
                return
            if len(b.split()) >= MIN_CLAUSE_WORDS:
                clauses = CLAUSE_RE.split(b)
                if len(clauses) > 1:
                    for clause in clauses[:-1]:
                        c = _clean(clause)
                        if c:
                            yield c
                    buf = clauses[-1]

        # ── Claude API (smart, fast) ──────────────────────────────────────────
        if claude_ai.is_available():
            mem_ctx = memory.summary_for_system_prompt()
            self.history.append({"role": "user", "content": user_text})
            for delta in claude_ai.stream_response(
                user_text=prompt,
                system_prompt=self.system_prompt,
                memory_context=mem_ctx,
                history=self.history[:-1],   # exclude the turn we just appended
                max_tokens=self._llm_cfg.get("max_new_tokens", 512),
            ):
                buf  += delta
                full += delta
                yield from _yield_buf(buf)
            if buf.strip():
                c = _clean(buf)
                if c:
                    yield c
                    full = full  # already accumulated
            self.history.append({"role": "assistant", "content": _clean(full)})
            return

        # ── Local LLM fallback ────────────────────────────────────────────────
        self.history.append({"role": "user", "content": user_text})
        messages = self._messages()
        if web_context:
            messages[-1] = {"role": "user", "content": prompt}

        stream = self._llm.create_chat_completion(
            messages=messages,
            max_tokens=self._llm_cfg.get("max_new_tokens", 256),
            temperature=self._llm_cfg.get("temperature", 0.7),
            top_p=self._llm_cfg.get("top_p", 0.9),
            stop=["<|eot_id|>", "\nUser:", "\nYou:"],
            stream=True,
        )

        for chunk in stream:
            delta: str = chunk["choices"][0]["delta"].get("content", "") or ""
            buf  += delta
            full += delta
            yield from _yield_buf(buf)

        if buf.strip():
            c = _clean(buf)
            if c:
                yield c

        self.history.append({"role": "assistant", "content": _clean(full)})

    def handle_turn(self, user_input: str, voice_mode: bool = True) -> None:
        """LLM pipeline: stream sentences → TTS speak each chunk."""
        self._stop_speak.clear()
        ws_server.set_state("thinking")

        # Web search: runs synchronously before LLM so results are ready immediately
        web_ctx = ""
        if web_search.needs_search(user_input):
            print("[Web] Searching…", flush=True)
            result = web_search.search(user_input)
            if result:
                web_ctx = result
                print(f"[Web] Got {len(result)} chars of results", flush=True)

        # Online AI only for text chat (too slow for voice — causes 15s+ thinking delay)
        if not voice_mode and online_ai.should_use_online(user_input):
            print("[OnlineAI] Using Pollinations AI…", flush=True)
            mem_ctx = memory.summary_for_system_prompt()
            answer = online_ai.ask(
                question=user_input,
                system_prompt=self.system_prompt,
                memory_context=mem_ctx,
                web_context=web_ctx,
                history=self.history,
            )
            if answer:
                self.history.append({"role": "user", "content": user_input})
                self.history.append({"role": "assistant", "content": answer})
                ws_server.set_state("speaking")
                self.speak_direct(answer)
                print(f"Jarvis: {answer}\n", flush=True)
                return

        sentence_q: queue.Queue[Optional[str]] = queue.Queue()
        first_audio_ready = threading.Event()
        display_parts: list[str] = []
        display_lock = threading.Lock()

        def _llm() -> None:
            for chunk in self.stream_sentences(user_input, web_context=web_ctx):
                sentence_q.put(chunk)
            sentence_q.put(None)

        def _tts() -> None:
            first = True
            while True:
                chunk = sentence_q.get()
                if chunk is None:
                    break
                if self._stop_speak.is_set():
                    break
                with display_lock:
                    display_parts.append(chunk)
                if first:
                    ws_server.set_state("speaking")
                    first_audio_ready.set()
                    first = False
                self._say(chunk)

        llm_t = threading.Thread(target=_llm, daemon=True)
        tts_t = threading.Thread(target=_tts, daemon=True)

        stop_spin = threading.Event()
        spin_t    = threading.Thread(
            target=self._spinner, args=(stop_spin,), daemon=True
        )
        spin_t.start()
        llm_t.start()
        tts_t.start()

        first_audio_ready.wait(timeout=15)
        stop_spin.set()
        spin_t.join()

        tts_t.join()
        with display_lock:
            response_text = " ".join(display_parts)
        sys.stdout.write(f"Jarvis: {response_text}\n")
        sys.stdout.flush()

        llm_t.join()
        ws_server.set_state("idle")

    def _chat_loop(self) -> None:
        """Process text messages sent from the browser chat panel."""
        while True:
            text = self._text_queue.get()
            if not text:
                continue
            print(f"[Chat] {text}")
            ws_server.broadcast_chat("user", text)
            with self._turn_lock:
                skill_result = skill_manager.try_execute(text)
                if skill_result:
                    ws_server.broadcast_chat("assistant", skill_result)
                    self.speak_direct(skill_result)
                else:
                    sys_response = self._handle_system_command(text)
                    if sys_response:
                        ws_server.broadcast_chat("assistant", sys_response)
                        self.speak_direct(sys_response)
                    else:
                        self.handle_turn(text)
                        if self.history:
                            last = self.history[-1].get("content", "")
                            if last:
                                ws_server.broadcast_chat("assistant", last)

    # ── Main loop ─────────────────────────────────────────────────────────────

    def run(self) -> None:
        print("\n" + "═" * 58)
        print("  🟢  Voice assistant ready — just speak!")
        print("  Open http://localhost:3000 to see the UI")
        print("  Press Ctrl+C to quit")
        print("═" * 58 + "\n")

        while True:
            try:
                if ws_server.is_muted():
                    ws_server.set_state("idle")
                    time.sleep(0.1)
                    continue

                audio = self.record_audio()
                if not audio:
                    continue

            except KeyboardInterrupt:
                print("\nGoodbye, Sir.")
                ws_server.set_state("idle")
                break

            user_input = self.transcribe(audio)
            if not user_input:
                print("  (Didn't catch that — try again)\n")
                continue

            print(f"You: {user_input}")

            # Clipboard augmentation (before system-command check)
            augmented_input, is_clipboard = self._try_augment_clipboard(user_input)

            # System command (direct execution) or LLM
            sys_response = self._handle_system_command(user_input)
            if sys_response:
                print(f"System: {sys_response}")
                self.speak_direct(sys_response)
            else:
                ws_server.broadcast_chat("user", user_input)
                with self._turn_lock:
                    self.handle_turn(augmented_input)
                if self.history:
                    last = self.history[-1].get("content", "")
                    if last:
                        ws_server.broadcast_chat("assistant", last)
                # Copy LLM response back to clipboard when requested
                if is_clipboard and self.history:
                    last = self.history[-1].get("content", "")
                    if last:
                        self._copy_to_clipboard(last)
                        print("📋  Response copied to clipboard.", flush=True)

            print()


if __name__ == "__main__":
    # HTTP/WebSocket sofort — bevor schwere ML-Imports in VoiceAssistant laufen.
    ws_server.start()
    assistant = VoiceAssistant()
    assistant.run()
