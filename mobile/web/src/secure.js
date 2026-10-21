// Sicurezza sul telefono: il token personale è cifrato (AES-256-GCM) con una chiave WebCrypto NON esportabile, tenuta in IndexedDB
// (nemmeno il codice dell'app può leggerla: può solo usarla), e il blocco con PIN usa PBKDF2-SHA256 con sale casuale e attese crescenti.
// Protegge da lettura del file dei dati, da backup e da curiosi; non da chi ha il telefono sbloccato e già in mano l'app aperta.

const DB = "jarvis-sec", STORE = "k";
const b64 = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf)));
const unb64 = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
const enc = new TextEncoder(), dec = new TextDecoder();

export const cryptoOk = () => !!(globalThis.crypto?.subtle && globalThis.indexedDB);

function idb() {
  return new Promise((resolve, reject) => {
    const r = indexedDB.open(DB, 1);
    r.onupgradeneeded = () => r.result.createObjectStore(STORE);
    r.onsuccess = () => resolve(r.result);
    r.onerror = () => reject(r.error);
  });
}
const req = (r) => new Promise((resolve, reject) => { r.onsuccess = () => resolve(r.result); r.onerror = () => reject(r.error); });

let keyPromise = null;
function deviceKey() {
  keyPromise ||= (async () => {
    const db = await idb();
    const get = db.transaction(STORE).objectStore(STORE).get("device");
    let key = await req(get);
    if (!key) {
      key = await crypto.subtle.generateKey({ name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"]);
      await req(db.transaction(STORE, "readwrite").objectStore(STORE).put(key, "device"));
    }
    return key;
  })();
  return keyPromise;
}

/** Testo -> "v1.<iv>.<cifrato>" in base64; null se la cifratura non è disponibile (browser di prova). */
export async function seal(text) {
  if (!cryptoOk()) return null;
  try {
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const ct = await crypto.subtle.encrypt({ name: "AES-GCM", iv, additionalData: enc.encode("jarvis-token") }, await deviceKey(), enc.encode(text));
    return `v1.${b64(iv)}.${b64(ct)}`;
  } catch { return null; }
}

export async function open(blob) {
  if (!cryptoOk() || !blob?.startsWith("v1.")) return "";
  try {
    const [, iv, ct] = blob.split(".");
    return dec.decode(await crypto.subtle.decrypt({ name: "AES-GCM", iv: unb64(iv), additionalData: enc.encode("jarvis-token") }, await deviceKey(), unb64(ct)));
  } catch { return ""; }
}

// ---------------------------------------------------------------- PIN
const ITER = 150_000;
async function derive(pin, salt) {
  const base = await crypto.subtle.importKey("raw", enc.encode(pin), "PBKDF2", false, ["deriveBits"]);
  return new Uint8Array(await crypto.subtle.deriveBits({ name: "PBKDF2", hash: "SHA-256", salt, iterations: ITER }, base, 256));
}
const same = (a, b) => a.length === b.length && a.reduce((x, v, i) => x | (v ^ b[i]), 0) === 0;  // confronto a tempo costante

export async function makePin(pin) {
  const salt = crypto.getRandomValues(new Uint8Array(16));
  return JSON.stringify({ s: b64(salt), h: b64(await derive(pin, salt)), n: ITER });
}
export async function checkPin(pin, record) {
  try { const r = JSON.parse(record); return same(await derive(pin, unb64(r.s)), unb64(r.h)); } catch { return false; }
}

/** Attesa dopo troppi errori: 5 sbagli → 30 s, poi raddoppia fino a 15 minuti. */
export function lockoutFor(fails) {
  return fails < 5 ? 0 : Math.min(900, 30 * 2 ** (fails - 5)) * 1000;
}
