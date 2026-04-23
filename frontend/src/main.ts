import { createOrb, type OrbState } from "./orb";
import "./style.css";

const WS_URL = `ws://${window.location.hostname}:8765`;
const API = `http://${window.location.hostname}:3000`;
const RECONNECT_INTERVAL_MS = 2_000;

const canvas      = document.getElementById("orb-canvas")       as HTMLCanvasElement;
const statusEl    = document.getElementById("status-text")       as HTMLDivElement;
const errorEl     = document.getElementById("error-text")        as HTMLDivElement;
const badgeEl     = document.getElementById("connection-badge")  as HTMLDivElement;
const badgeLabelEl= document.getElementById("connection-label")  as HTMLSpanElement;
const muteButtonEl= document.getElementById("mute-button")       as HTMLButtonElement;
const chatToggle  = document.getElementById("chat-toggle")       as HTMLButtonElement;
const chatPanel   = document.getElementById("chat-panel")        as HTMLDivElement;
const chatClose   = document.getElementById("chat-close")        as HTMLButtonElement;
const chatMessages= document.getElementById("chat-messages")     as HTMLDivElement;
const chatInput   = document.getElementById("chat-input")        as HTMLInputElement;
const chatSend    = document.getElementById("chat-send")         as HTMLButtonElement;

const orb = createOrb(canvas);

const STATE_LABELS: Record<OrbState, string> = {
  idle: "", listening: "listening...", thinking: "thinking...", speaking: "",
};

function applyState(state: OrbState): void {
  orb.setState(state);
  statusEl.textContent = STATE_LABELS[state];
  if (state === "thinking") showTyping(); else removeTyping();
}

function setMuted(muted: boolean): void {
  muteButtonEl.classList.toggle("is-muted", muted);
  muteButtonEl.setAttribute("aria-pressed", String(muted));
  muteButtonEl.textContent = muted ? "unmute" : "mute";
}

let errorTimer: ReturnType<typeof setTimeout> | null = null;
function showError(msg: string): void {
  errorEl.textContent = msg;
  errorEl.style.opacity = "1";
  if (errorTimer) clearTimeout(errorTimer);
  errorTimer = setTimeout(() => { errorEl.style.opacity = "0"; }, 4_000);
}

function setConnected(ok: boolean): void {
  badgeEl.classList.toggle("connected", ok);
  badgeEl.classList.toggle("disconnected", !ok);
  badgeLabelEl.textContent = ok ? "connected" : "reconnecting";
  muteButtonEl.disabled = !ok;
}

// ── Chat panel ────────────────────────────────────────────────────────────────
let typingEl: HTMLDivElement | null = null;

function setChatOpen(open: boolean): void {
  chatPanel.classList.toggle("is-open", open);
  chatToggle.classList.toggle("is-open", open);
  if (open) chatInput.focus();
}

chatToggle.addEventListener("click", () => setChatOpen(!chatPanel.classList.contains("is-open")));
chatClose.addEventListener("click",  () => setChatOpen(false));

function addMessage(role: "user" | "assistant", text: string): void {
  removeTyping();
  const el = document.createElement("div");
  el.className = `chat-msg ${role}`;
  el.textContent = text;
  chatMessages.appendChild(el);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function showTyping(): void {
  if (typingEl) return;
  typingEl = document.createElement("div");
  typingEl.className = "chat-msg typing";
  typingEl.innerHTML = `<div class="typing-dots"><span></span><span></span><span></span></div>`;
  chatMessages.appendChild(typingEl);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function removeTyping(): void {
  typingEl?.remove();
  typingEl = null;
}

async function sendChat(): Promise<void> {
  const text = chatInput.value.trim();
  if (!text) return;
  chatInput.value = "";
  chatSend.disabled = true;
  addMessage("user", text);
  setChatOpen(true);
  try {
    await fetch(`${API}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
  } catch {
    showError("Chat send failed");
  }
  chatSend.disabled = false;
  chatInput.focus();
}

chatSend.addEventListener("click", () => void sendChat());
chatInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void sendChat(); }
});

// ── Status & mute API ─────────────────────────────────────────────────────────
async function refreshStatus(): Promise<void> {
  try {
    const res  = await fetch(`${API}/api/status`);
    if (!res.ok) return;
    const data = (await res.json()) as { state?: string; muted?: boolean };
    if (data.state)                      applyState(data.state as OrbState);
    if (typeof data.muted === "boolean") setMuted(data.muted);
  } catch { /* backend offline */ }
}

async function toggleMuted(): Promise<void> {
  const next = muteButtonEl.getAttribute("aria-pressed") !== "true";
  try {
    const res  = await fetch(`${API}/api/mute`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ muted: next }),
    });
    if (!res.ok) throw new Error();
    const data = (await res.json()) as { muted?: boolean; state?: string };
    if (typeof data.muted === "boolean") setMuted(data.muted);
    if (data.state)                      applyState(data.state as OrbState);
  } catch { showError("mute toggle failed"); }
}

// ── WebSocket ─────────────────────────────────────────────────────────────────
let ws: WebSocket | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

function connect(): void {
  if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
  ws = new WebSocket(WS_URL);

  ws.addEventListener("open",  () => setConnected(true));
  ws.addEventListener("close", () => { setConnected(false); applyState("idle"); scheduleReconnect(); });
  ws.addEventListener("error", () => setConnected(false));

  ws.addEventListener("message", (event: MessageEvent) => {
    try {
      const data = JSON.parse(event.data as string) as {
        type?: string; state?: string; muted?: boolean; action?: string;
        role?: string; text?: string;
      };

      if (data.type === "chat" && data.role && data.text) {
        if (data.role === "user" || data.role === "assistant") {
          addMessage(data.role, data.text);
        }
        return;
      }
      if (data.action === "demo") { orb.triggerDemo(); return; }
      if (data.state)                      applyState(data.state as OrbState);
      if (typeof data.muted === "boolean") setMuted(data.muted);
    } catch { /* ignore */ }
  });
}

function scheduleReconnect(): void {
  if (reconnectTimer) return;
  reconnectTimer = setTimeout(() => { reconnectTimer = null; connect(); }, RECONNECT_INTERVAL_MS);
}

// ── Boot ──────────────────────────────────────────────────────────────────────
setConnected(false);
applyState("idle");
setMuted(false);
void refreshStatus();
connect();
muteButtonEl.addEventListener("click", () => void toggleMuted());
