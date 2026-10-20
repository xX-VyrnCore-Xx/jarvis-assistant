// Il token personale sta nel Gestore credenziali di Windows (via Rust), non in chiaro nel disco dell'app.
// Fuori da Tauri (browser di prova) si ripiega su localStorage.
import { invoke } from "@tauri-apps/api/core";

const LEGACY = "jarvis.token";

export async function loadToken() {
  try {
    const v = await invoke("secret_get");
    if (v) return { token: v, where: "keyring" };
    const old = localStorage.getItem(LEGACY);
    if (old) { // migra un token salvato da una versione precedente
      await invoke("secret_set", { value: old });
      localStorage.removeItem(LEGACY);
      return { token: old, where: "keyring" };
    }
    return { token: "", where: "keyring" };
  } catch {
    return { token: localStorage.getItem(LEGACY) || "", where: "local" };
  }
}

export async function saveToken(token) {
  try {
    await invoke("secret_set", { value: token });
    localStorage.removeItem(LEGACY);
    return "keyring";
  } catch {
    localStorage.setItem(LEGACY, token);
    return "local";
  }
}

export async function clearToken() {
  try { await invoke("secret_delete"); } catch { /* assente */ }
  localStorage.removeItem(LEGACY);
}
