// Voce di JARVIS (XTTS v2) in locale: installazione, avvio del processo e sintesi. Il lavoro pesante è in Rust (src-tauri/src/voice.rs).
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";

const isTauri = "__TAURI_INTERNALS__" in window;
const listeners = new Set();
export const voice = { installed: false, installing: false, running: false, log: [], error: "" };
let run = null; // {port, token}
let starting = null;

const emit = () => listeners.forEach((f) => f(voice));
export const onVoiceChange = (f) => { listeners.add(f); return () => listeners.delete(f); };

export async function refreshVoice() {
  if (!isTauri) return voice;
  try {
    const st = await invoke("voice_status");
    Object.assign(voice, { installed: st.installed, installing: st.installing, running: st.running });
    run = st.running ? { port: st.port, token: st.token } : null;
  } catch (e) { voice.error = String(e); }
  emit();
  return voice;
}

export async function initVoice() {
  if (!isTauri) return;
  await listen("voice-progress", (ev) => {
    voice.log.push(String(ev.payload));
    if (voice.log.length > 200) voice.log.shift();
    emit();
  });
  await listen("voice-done", async (ev) => {
    voice.installing = false;
    voice.error = ev.payload ? "" : "Installazione non riuscita: guarda il registro qui sotto.";
    await refreshVoice();
    if (ev.payload) startVoice().catch(() => {});
  });
  await refreshVoice();
  if (voice.installed) startVoice().catch(() => {});
}

export async function installVoice() {
  voice.log = []; voice.error = ""; voice.installing = true; emit();
  try { await invoke("voice_install"); } catch (e) { voice.installing = false; voice.error = String(e); emit(); }
}

export async function removeVoice() {
  await invoke("voice_uninstall");
  run = null; starting = null;
  await refreshVoice();
}

/** Avvia il processo e attende che il modello sia caricato (30-60 s la prima volta). */
export function startVoice() {
  if (!voice.installed) return Promise.reject(new Error("Voce non installata"));
  if (starting) return starting;
  starting = (async () => {
    const [port, token] = await invoke("voice_start");
    run = { port, token };
    for (let i = 0; i < 120; i++) { // fino a 2 minuti
      try {
        const r = await fetch(`http://127.0.0.1:${port}/health`);
        if (r.ok) { voice.running = true; emit(); return run; }
      } catch { /* non ancora pronto */ }
      await new Promise((r) => setTimeout(r, 1000));
    }
    throw new Error("La voce non si è avviata");
  })().catch((e) => { starting = null; throw e; });
  return starting;
}

export async function synth(text) {
  const { port, token } = await startVoice();
  const r = await fetch(`http://127.0.0.1:${port}/tts`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!r.ok) throw new Error(`Voce: errore ${r.status}`);
  return r.blob();
}

export async function toBase64(blob) {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(bin);
}
