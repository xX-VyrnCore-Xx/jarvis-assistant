// Schermata di blocco con tastierino numerico: sei cifre, vibrazione a ogni tocco, scossa se sbagliato, attese crescenti.
import { el } from "@shared/format.js";
import { icon } from "@shared/icons.js";
import { checkPin, lockoutFor } from "./secure.js";
import { haptic } from "./native.js";

const LEN = 6;
const KEYS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "", "0", "⌫"];

/** Mostra il blocco; risolve quando il PIN è giusto. `store` = {get,set,del} dell'app, `orb` = costruttore del logo animato. */
export function showLock({ store, record, orb }) {
  document.getElementById("m-lock")?.remove();
  return new Promise((resolve) => {
    let pin = "", busy = false;
    let fails = Number(store.get("jarvis.lockfails", "0")) || 0;
    let until = Number(store.get("jarvis.lockuntil", "0")) || 0;
    const dots = el("div", { class: "lk-dots", "aria-hidden": "true" }, ...Array.from({ length: LEN }, () => el("i")));
    const msg = el("p", { class: "lk-msg", "aria-live": "polite" }, "Inserisca il PIN");
    const paint = () => [...dots.children].forEach((d, i) => d.classList.toggle("on", i < pin.length));
    const wait = () => Math.max(0, until - Date.now());
    const tick = () => {
      const w = wait();
      if (w > 0) { msg.textContent = `Troppi tentativi: riprovi tra ${Math.ceil(w / 1000)} s`; msg.className = "lk-msg bad"; setTimeout(tick, 500); }
      else if (msg.classList.contains("bad") && !busy) { msg.textContent = "Inserisca il PIN"; msg.className = "lk-msg"; }
    };
    const press = async (k) => {
      if (busy || wait() > 0) return;
      if (k === "⌫") { pin = pin.slice(0, -1); paint(); return haptic(); }
      if (pin.length >= LEN || !k) return;
      pin += k; paint(); haptic();
      if (pin.length < LEN) return;
      busy = true;
      const ok = await checkPin(pin, record);
      if (ok) {
        store.set("jarvis.lockfails", "0"); store.set("jarvis.lockuntil", "0");
        root.classList.add("out"); haptic("medium");
        setTimeout(() => { root.remove(); resolve(); }, 380);
        return;
      }
      fails += 1; until = Date.now() + lockoutFor(fails);
      store.set("jarvis.lockfails", String(fails)); store.set("jarvis.lockuntil", String(until));
      haptic("heavy"); dots.classList.add("shake"); pin = "";
      setTimeout(() => { dots.classList.remove("shake"); paint(); busy = false; }, 420);
      msg.textContent = wait() > 0 ? "" : "PIN errato"; msg.className = "lk-msg bad"; tick();
    };
    const root = el("div", { id: "m-lock", role: "dialog", "aria-label": "App bloccata" },
      el("div", { class: "lk-top" }, orb(), el("h2", {}, "JARVIS è bloccato"), msg, dots),
      el("div", { class: "lk-pad" }, ...KEYS.map((k) => k ? el("button", { class: `lk-key${k === "⌫" ? " del" : ""}`, "aria-label": k === "⌫" ? "Cancella" : k, onclick: () => press(k) }, k === "⌫" ? icon("x", 22) : k) : el("span"))));
    document.body.append(root);
    requestAnimationFrame(() => root.classList.add("in"));
    tick();
    // tastiera fisica / emulatore
    root.tabIndex = -1; root.focus();
    root.addEventListener("keydown", (e) => { if (/^\d$/.test(e.key)) press(e.key); else if (e.key === "Backspace") press("⌫"); });
  });
}
