import { Jarvis, ApiError, deviceId } from "@shared/api.js";
import { el, fmtDate, fmtTokens, fmtUptime, markdown, pct } from "@shared/format.js";
import { icon } from "@shared/icons.js";
import { Speaker } from "@shared/speech.js";
import { openStream } from "@shared/stream.js";
import { appVersion, dictationAvailable, haptic, hideSplash, onBack, openExternal, paintSystemBars, platform, startDictation, stopDictation } from "./native.js";
import { initPush, teardownPush } from "./push.js";
import { checkPin, cryptoOk, makePin, open as openSealed, seal } from "./secure.js";
import { showLock } from "./lock.js";
import { NUMBER_RE, phone, phoneAvailable } from "./phone.js";

// URL pubblico del server (non è un segreto); il token personale resta nella memoria privata dell'app
const DEFAULT_URL = "https://jarvis-ai-841t.onrender.com";
const SESSION = "mobile";
const TABS = [["chat", "Chat", "chat"], ["brain", "Cervello", "sparkle"], ["tokens", "Token", "gauge"], ["reminders", "Promemoria", "clock"], ["more", "Altro", "sliders"]];
const QUICK = [
  ["Agenda", "calendar", "Cosa ho in agenda oggi e domani?"],
  ["Email", "mail", "Ho email non lette importanti?"],
  ["Meteo", "cloud", "Che tempo fa oggi e domani?"],
  ["Token", "gauge", "Quanti token mi restano questo mese?"],
];
const CHIPS = [...QUICK.map(([l,, t]) => [l, t]), ["Ora", "Che ore sono?"]];

const store = {
  get(k, d = "") { try { return localStorage.getItem(k) ?? d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch { /* memoria non disponibile */ } },
  del(k) { try { localStorage.removeItem(k); } catch { /* ignora */ } },
};
const cfg = { url: (store.get("jarvis.url") || DEFAULT_URL).replace(/\/+$/, ""), token: "" };

/** Il token sta sul telefono solo cifrato (chiave non esportabile). Al primo avvio dopo l'aggiornamento il vecchio token in chiaro viene cifrato e cancellato. */
async function loadToken() {
  const enc = store.get("jarvis.token.enc");
  if (enc) cfg.token = await openSealed(enc);
  const legacy = store.get("jarvis.token");
  if (!cfg.token && legacy) cfg.token = legacy;
  if (legacy) await saveToken(cfg.token);
}
async function saveToken(t) {
  if (!t) { store.del("jarvis.token.enc"); store.del("jarvis.token"); return; }
  const sealed = await seal(t);
  if (sealed) { store.set("jarvis.token.enc", sealed); store.del("jarvis.token"); } else store.set("jarvis.token", t);  // senza WebCrypto (solo browser di prova) resta com'era
}
const api = new Jarvis({ url: () => cfg.url, token: () => cfg.token });
const speaker = new Speaker({ tts: (t) => api.tts(t) });
const voiceOn = () => store.get("jarvis.speak") !== "0";
const S = { skill: null, update: null, prefs: null, models: null, usage: null, appVer: "", brain: { q: "", results: null, docs: null, stats: null, busy: false }, tab: "chat", status: null, checked: false, tokens: null, tokensErr: "", tokensAt: null, reminders: [], remindersLoaded: false, notes: [], pending: [], online: false, live: "off", backup: null, phone: null, busy: false, mic: false, canMic: false, sheets: [] };

const $app = document.getElementById("m-app");
let top, content, tabs, log, input, sendBtn, micBtn, downBtn, chatView, hello, chips;
let timers = [];
let closeStream = null;

const errText = (e) => (e instanceof ApiError ? e.message : String(e));
const greeting = () => { const h = new Date().getHours(); return h < 5 ? "Buonanotte" : h < 13 ? "Buongiorno" : h < 18 ? "Buon pomeriggio" : "Buonasera"; };
const clock = (d = new Date()) => d.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });

function toast(text, bad = false, action = null) {
  const t = document.getElementById("m-toast");
  t.replaceChildren(...[el("span", {}, text), action ? el("button", { onclick: () => { t.className = ""; action.fn(); } }, action.label) : null].filter(Boolean));  // replaceChildren(null) scriverebbe «null»
  t.className = `show${bad ? " bad" : ""}${action ? " act" : ""}`;
  clearTimeout(toast.t); toast.t = setTimeout(() => (t.className = ""), action ? 5200 : 3800);
}

// ---------------------------------------------------------------- tema
function applyTheme() {
  const pref = store.get("jarvis.theme", "auto");
  const light = pref === "light" || (pref === "auto" && matchMedia("(prefers-color-scheme: light)").matches);
  document.documentElement.dataset.theme = light ? "light" : "dark";
  paintSystemBars(!light, light ? "#fbf7f2" : "#0d0b14");
}
matchMedia("(prefers-color-scheme: light)").addEventListener?.("change", applyTheme);

// ---------------------------------------------------------------- logo animato
const NS = "http://www.w3.org/2000/svg";
function orb() {
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 100 100");
  svg.setAttribute("class", "orb");
  svg.setAttribute("aria-hidden", "true");
  const add = (parent, tag, attrs) => { const n = document.createElementNS(NS, tag); for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v); parent.append(n); return n; };
  const defs = add(svg, "defs", {});
  const g = add(defs, "linearGradient", { id: "og", x1: "0", y1: "0", x2: "1", y2: "1" });
  add(g, "stop", { offset: "0", "stop-color": "#ffc15e" }); add(g, "stop", { offset: "1", "stop-color": "#ff6a4a" });
  const cg = add(defs, "radialGradient", { id: "cg" });
  add(cg, "stop", { offset: "0", "stop-color": "#fff3d6" }); add(cg, "stop", { offset: ".45", "stop-color": "#ffc15e" }); add(cg, "stop", { offset: "1", "stop-color": "#ff6a4a" });
  // tre anelli a segmenti (come l'icona dell'app) e un nucleo luminoso
  for (const [cls, r, w, dash, rot] of [["r1", 44, 5.2, "176 100", -70], ["r2", 32, 3.6, "", 0], ["r3", 21, 4, "70 62", 130]]) {
    const grp = add(svg, "g", { class: cls });
    add(grp, "circle", { cx: 50, cy: 50, r, fill: "none", stroke: "url(#og)", "stroke-width": w, "stroke-linecap": "round", ...(dash ? { "stroke-dasharray": dash } : {}), transform: `rotate(${rot} 50 50)` });
  }
  const core = add(svg, "g", { class: "core" });
  add(core, "circle", { cx: 50, cy: 50, r: 8.5, fill: "url(#cg)" });
  add(core, "circle", { cx: 47, cy: 47, r: 2.2, fill: "#fff", opacity: ".6" });
  return svg;
}
function setOrb(state) {
  document.querySelectorAll(".orb").forEach((o) => { o.classList.toggle("thinking", state === "thinking"); o.classList.toggle("speaking", state === "speaking"); });
}
speaker.onState = (on) => setOrb(on ? "speaking" : S.busy ? "thinking" : "");

// ---------------------------------------------------------------- struttura
function shell() {
  top = el("header", { class: "m-top" });
  content = el("main", { id: "m-view" });
  tabs = el("nav", { class: "m-tabs", "aria-label": "Sezioni" });
  $app.replaceChildren(el("div", { class: "m-col" }, top, content), tabs);
  // la barra superiore prende rilievo (ombra + vetro più denso) solo quando il contenuto scorre sotto di essa
  $app.addEventListener("scroll", (e) => { const t = e.target; if (t instanceof HTMLElement && t.scrollHeight > t.clientHeight) top.classList.toggle("scrolled", t.scrollTop > 6); }, { capture: true, passive: true });
  // scorri a sinistra/destra sul contenuto per passare alla sezione accanto (non su campi di testo, righe scorrevoli o fogli aperti)
  let sx = 0, sy = 0, t0 = 0, ok = false;
  content.addEventListener("touchstart", (e) => {
    ok = e.touches.length === 1 && !S.sheets.length && !S.locked && !e.target.closest("input,textarea,.swipe,.m-chips,pre,table,.m-seg,.m-sheet");
    sx = e.touches[0].clientX; sy = e.touches[0].clientY; t0 = Date.now();
  }, { passive: true });
  content.addEventListener("touchend", (e) => {
    if (!ok) return;
    const dx = e.changedTouches[0].clientX - sx, dy = e.changedTouches[0].clientY - sy;
    if (Math.abs(dx) < 90 || Math.abs(dx) < 2.2 * Math.abs(dy) || Date.now() - t0 > 650) return;
    const j = TABS.findIndex(([id]) => id === S.tab) + (dx < 0 ? 1 : -1);
    if (TABS[j]) { haptic(); setTab(TABS[j][0]); }
  }, { passive: true });
  renderTop(); renderTabs();
}

const unread = () => S.notes.filter((n) => !n.read).length;

const LINK_TEXT = { live: "Collegato in tempo reale", connecting: "Mi collego…", off: "Senza collegamento" };
/** live = flusso aperto; connecting = sta provando; off = server o rete non raggiungibili. */
const linkState = () => (S.live === "on" ? "live" : S.checked && !S.online ? "off" : S.live === "connecting" || !S.checked ? "connecting" : "off");

function renderTop() {
  const t = S.status?.tokens;
  const low = t && t.documented_monthly_tokens && t.remaining_tokens / t.documented_monthly_tokens < 0.15;
  const offline = cfg.token && S.checked && !S.online;
  top.replaceChildren(
    el("div", { class: "m-title" }, orb(), el("div", {}, el("h1", {}, "JARVIS", cfg.token ? el("i", { class: `m-link ${linkState()}`, role: "img", "aria-label": LINK_TEXT[linkState()] }) : null), el("p", {}, `${greeting()}, signore`))),
    el("div", { class: "m-right" },
      t ? el("button", { class: `m-pill${low ? " low" : ""}`, onclick: () => setTab("tokens"), "aria-label": "Token disponibili" }, icon("gauge", 15), fmtTokens(t.remaining_tokens)) : null,
      el("button", { class: "m-bell", onclick: openNotes, "aria-label": "Notifiche" }, icon("bell", 21), unread() ? el("i", {}, unread() > 9 ? "9+" : String(unread())) : null)),
  );
  document.getElementById("m-offline")?.remove();
  document.getElementById("m-update")?.remove();
  if (updateVisible()) {
    top.insertAdjacentElement("afterend", el("div", { id: "m-update", class: "m-update", role: "button", tabindex: "0", onclick: openUpdate },
      icon("down", 18), el("span", {}, `Nuova versione ${S.update.latest}`, S.update.size ? el("small", {}, ` · ${(S.update.size / 1048576).toFixed(1)} MB`) : null), el("b", {}, "Aggiorna"),
      el("button", { class: "m-x", "aria-label": "Nascondi per un giorno", onclick: (e) => { e.stopPropagation(); store.set("jarvis.updhide", JSON.stringify({ v: S.update.latest, t: Date.now() })); renderTop(); haptic(); } }, icon("x", 15))));
  }
  if (offline) {
    const msg = el("span", { class: "off-msg" });
    top.insertAdjacentElement("afterend", el("div", { id: "m-offline", class: "m-offline", role: "status" }, icon("offline", 17),
      el("div", { class: "off-text" }, msg), el("button", { class: "m-ghost", style: "margin-left:auto;min-height:30px;padding:0 10px", onclick: () => { retryNow(); toast("Controllo il server…"); } }, "Riprova")));
    paintOffline(msg);
  } else stopOfflineTicker();
}

// il server gratuito si addormenta: dopo un'assenza ci mette fino a un minuto a svegliarsi. L'app riprova da sola, con un conto alla rovescia.
let offlineTicker = 0, offlineSince = 0, nextTry = 0;
const RETRY_STEPS = [6, 10, 15, 20, 30];
let retries = 0;
function stopOfflineTicker() { clearInterval(offlineTicker); offlineTicker = 0; offlineSince = 0; retries = 0; }
function paintOffline(msg) {
  if (!offlineTicker) {
    offlineSince = Date.now(); nextTry = Date.now() + RETRY_STEPS[0] * 1000;
    offlineTicker = setInterval(() => {
      if (document.hidden) return;
      if (Date.now() >= nextTry) { retries++; nextTry = Date.now() + RETRY_STEPS[Math.min(retries, RETRY_STEPS.length - 1)] * 1000; refreshStatus(); }
      const m = document.querySelector("#m-offline .off-msg"); if (m) paintOffline(m);
    }, 1000);
  }
  const waking = Date.now() - offlineSince < 90_000;
  const left = Math.max(0, Math.ceil((nextTry - Date.now()) / 1000));
  msg.textContent = (waking ? "Il server si sta svegliando (può volerci un minuto) o manca la rete." : "Server non raggiungibile.") + ` Riprovo tra ${left} s.`;
}
function retryNow() { retries = 0; nextTry = Date.now() + RETRY_STEPS[0] * 1000; refreshStatus(); closeStream?.poke?.(); }
window.addEventListener("online", () => { if (cfg.token && !S.locked && !document.hidden) retryNow(); });

function renderTabs() {
  const badge = { reminders: S.reminders.filter((r) => new Date(r.due_at) - Date.now() < 86_400_000).length };
  if (!tabs.querySelector(".m-lens")) {  // costruita una volta sola: la «lente» sotto la scheda attiva scivola con la molla
    tabs.replaceChildren(el("span", { class: "m-lens", "aria-hidden": "true" }, el("i")),
      ...TABS.map(([id, label, ic]) => el("button", { class: "m-tab", dataset: { tab: id }, "aria-label": label, onclick: () => { haptic(); setTab(id); } },
        el("span", { class: "m-tab-ic" }, icon(ic, 24)), el("small", {}, label))));
  }
  tabs.style.setProperty("--i", String(Math.max(0, TABS.findIndex(([id]) => id === S.tab))));
  tabs.querySelectorAll(".m-tab").forEach((b) => {
    const on = b.dataset.tab === S.tab;
    b.classList.toggle("on", on);
    if (on) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current");
    const n = badge[b.dataset.tab] || 0;
    let dot = b.querySelector(".dot");
    if (n) { if (!dot) { dot = el("span", { class: "dot" }); b.append(dot); } dot.textContent = String(n); } else dot?.remove();
  });
}

function setTab(id) {
  const from = TABS.findIndex(([t]) => t === S.tab), to = TABS.findIndex(([t]) => t === id);
  if (content && from !== to) {  // la sezione entra scorrendo dalla parte da cui si è toccato
    content.dataset.dir = to > from ? "r" : "l";
    clearTimeout(setTab.t); setTab.t = setTimeout(() => delete content.dataset.dir, 520);
  }
  S.tab = id;
  renderTabs(); renderTab();
  if (id === "brain") loadBrain();
  if (id === "tokens") loadTokens();
  if (id === "reminders") loadReminders();
  if (id === "more") { loadBackup(); loadPhone(); }
}

function renderTab() {
  content.className = `tab-${S.tab}`;
  const v = { chat: buildChat, brain: buildBrain, tokens: buildTokens, reminders: buildReminders, more: buildMore }[S.tab]();
  content.replaceChildren(v);
  if (S.tab === "chat") requestAnimationFrame(() => { log.scrollTop = log.scrollHeight; });
}

/** Trascina verso il basso dalla cima per aggiornare. */
function pullToRefresh(page, run) {
  const bar = el("div", { class: "ptr" }, "Rilascia per aggiornare");
  page.prepend(bar);
  let y0 = null;
  page.addEventListener("touchstart", (e) => { y0 = page.scrollTop <= 0 ? e.touches[0].clientY : null; }, { passive: true });
  page.addEventListener("touchmove", (e) => { if (y0 != null) bar.classList.toggle("on", e.touches[0].clientY - y0 > 70); }, { passive: true });
  page.addEventListener("touchend", () => { if (bar.classList.contains("on")) { haptic("medium"); run(); } bar.classList.remove("on"); y0 = null; });
}

// ---------------------------------------------------------------- chat
function nearBottom() { return log.scrollHeight - log.scrollTop - log.clientHeight < 160; }

function bubble(role, text, { fresh = true } = {}) {
  hello?.remove(); hello = null;
  chips.style.display = "";
  const prev = log.lastElementChild;
  const same = prev && prev.classList.contains(role) && role !== "sys";
  const stick = nearBottom();
  const meta = role === "sys" ? null : el("div", { class: "m-meta" }, fresh ? el("span", {}, clock()) : null,
    role === "bot" ? [
      el("button", { "aria-label": "Copia", onclick: () => { navigator.clipboard?.writeText(text).then(() => toast("Copiato")).catch(() => toast("Copia non riuscita", true)); haptic(); } }, icon("copy", 15)),
      el("button", { "aria-label": "Ascolta", onclick: () => { haptic(); speaker.speaking ? speaker.stop() : speaker.speak(text); } }, icon("volume", 16)),
    ] : null);
  const node = el("div", { class: `m-msg ${role}${same ? " same" : ""}` }, el("div", { class: "m-bubble" }, role === "bot" ? markdown(text) : el("p", {}, text)), meta);
  log.append(node);
  if (stick || role === "user") log.scrollTop = log.scrollHeight;
  return node;
}

function showHello() {
  chips.style.display = "none";
  hello = el("div", { class: "m-hello" }, orb(),
    el("h2", {}, `${greeting()}, signore`),
    el("p", {}, cfg.token ? "Come posso esserle utile?" : "Vai su Altro e inserisci il token personale per iniziare."),
    cfg.token ? el("div", { class: "m-quick" }, QUICK.map(([label, ic, text]) =>
      el("button", { onclick: () => send(text) }, el("span", { class: "qi" }, icon(ic, 19)), label))) : null);
  log.append(hello);
}

function buildChat() {
  if (chatView) return chatView;
  log = el("div", { class: "m-log", "aria-live": "polite" });
  input = el("textarea", { id: "m-input", rows: 1, placeholder: "Scrivi a JARVIS…", "aria-label": "Messaggio", enterkeyhint: "send" });
  sendBtn = el("button", { class: "m-circle m-send", "aria-label": "Invia", disabled: true, onclick: () => send() }, icon("send", 21));
  micBtn = el("button", { class: "m-circle m-mic", "aria-label": "Detta", onclick: toggleMic, style: S.canMic ? "" : "display:none" }, icon("mic", 22));
  downBtn = el("button", { class: "m-down", "aria-label": "Vai in fondo", onclick: () => log.scrollTo({ top: log.scrollHeight, behavior: "smooth" }) }, icon("down", 20));
  input.addEventListener("input", () => { input.style.height = "auto"; input.style.height = `${Math.min(input.scrollHeight, 130)}px`; sendBtn.disabled = !input.value.trim(); });
  log.addEventListener("scroll", () => downBtn.classList.toggle("show", !nearBottom()), { passive: true });
  chips = el("div", { class: "m-chips" }, CHIPS.map(([l, t]) => el("button", { onclick: () => send(t) }, l)));
  chatView = el("div", { class: "m-chat" }, log, downBtn, chips, el("div", { id: "m-skillchip" }), el("div", { class: "m-composer" }, micBtn, input, sendBtn));
  showHello();
  return chatView;
}

function renderSkillChip() {
  const box = document.getElementById("m-skillchip");
  if (!box) return;
  box.replaceChildren(...(S.skill ? [el("div", { class: "m-skill-on" }, icon("sparkle", 16), el("span", {}, `Competenza: ${S.skill.title}`),
    el("button", { "aria-label": "Rimuovi la competenza", onclick: () => { S.skill = null; renderSkillChip(); } }, "✕"))] : []));
}

async function toggleMic() {
  haptic("medium");
  if (S.mic) { await stopDictation(); S.mic = false; micBtn.classList.remove("on"); return; }
  try {
    S.mic = true; micBtn.classList.add("on");
    await startDictation((t) => { input.value = t; input.dispatchEvent(new Event("input")); }, () => { S.mic = false; micBtn.classList.remove("on"); input.focus(); });
  } catch (e) { S.mic = false; micBtn.classList.remove("on"); toast(errText(e), true); }
}

async function send(text) {
  const msg = (text ?? input.value).trim();
  if (!msg || S.busy) return;
  if (!cfg.token) return setTab("more");
  haptic();
  if (S.tab !== "chat") setTab("chat");
  if (text === undefined) { input.value = ""; input.style.height = "auto"; sendBtn.disabled = true; }
  if (S.mic) { await stopDictation(); S.mic = false; micBtn.classList.remove("on"); }
  bubble("user", msg);
  S.busy = true; setOrb("thinking");
  const label = el("span", { class: "m-status" });
  const typing = el("div", { class: "m-msg bot" }, el("div", { class: "m-bubble typing" }, el("i"), el("i"), el("i"), label));
  log.append(typing); log.scrollTop = log.scrollHeight;
  const skill = S.skill?.name || "";
  S.skill = null; renderSkillChip();
  let live = null, acc = "", raf = 0;
  const paint = () => { raf = 0; const stick = nearBottom(); live.firstChild.replaceChildren(markdown(acc)); if (stick) log.scrollTop = log.scrollHeight; };
  try {
    const reply = await api.chatStream(msg, SESSION, {
      model: store.get("jarvis.model"), skill,
      onStatus: (t) => { label.textContent = t; },
      onDelta: (t) => {
        if (!live) { typing.remove(); live = el("div", { class: "m-msg bot" }, el("div", { class: "m-bubble" })); log.append(live); }
        acc += t;
        if (!raf) raf = requestAnimationFrame(paint);
      },
    });
    cancelAnimationFrame(raf); typing.remove(); live?.remove();
    bubble("bot", reply);
    haptic("light");
    if (voiceOn() && S.status?.voice) speaker.speak(reply);
    refreshStatus();
  } catch (e) { cancelAnimationFrame(raf); typing.remove(); live?.remove(); bubble("sys", errText(e)); }
  finally { S.busy = false; if (!speaker.speaking) setOrb(""); }
}

async function loadHistory() {
  try {
    const rows = await api.history(SESSION, 30);
    S.histSig = `${rows.length}|${rows.at(-1)?.content?.length ?? 0}|${rows.at(-1)?.role ?? ""}`;
    buildChat(); log.replaceChildren(); hello = null;
    if (!rows.length) return showHello();
    rows.forEach((r) => bubble(r.role === "user" ? "user" : "bot", r.content, { fresh: false }));
    log.scrollTop = log.scrollHeight;
  } catch { /* offline: resta la schermata di benvenuto */ }
}

/** Un altro dispositivo ha scritto: aggiorna solo la conversazione (senza toccare ciò che stai scrivendo) se è cambiata. */
async function syncHistory() {
  if (S.busy || !log) return;
  try {
    const rows = await api.history(SESSION, 30);
    const sig = `${rows.length}|${rows.at(-1)?.content?.length ?? 0}|${rows.at(-1)?.role ?? ""}`;
    if (sig === S.histSig) return;
    S.histSig = sig;
    const stick = nearBottom();
    log.replaceChildren(); hello = null;
    if (!rows.length) return showHello();
    rows.forEach((r) => bubble(r.role === "user" ? "user" : "bot", r.content, { fresh: false }));
    if (stick) log.scrollTop = log.scrollHeight;
  } catch { /* offline: si riprova al prossimo avviso */ }
}

// ---------------------------------------------------------------- secondo cervello
const SRC = { note: "nota", memory: "ricordo", journal: "diario", web: "web", file: "file", drive: "drive", gmail: "email", chat: "chat" };

async function loadBrain() {
  if (!cfg.token) return;
  try { [S.brain.docs, S.brain.stats] = await Promise.all([api.brainDocs(30), api.brainStats()]); } catch (e) { if (e.status !== 404) toast(errText(e), true); S.brain.docs = S.brain.docs || []; }
  if (S.tab === "brain") renderTab();
}

let brainTimer = null;
function brainSearch(q, input) {
  S.brain.q = q;
  clearTimeout(brainTimer);
  if (q.trim().length < 2) { S.brain.results = null; return renderBrainBody(); }
  brainTimer = setTimeout(async () => {
    S.brain.busy = true; renderBrainBody();
    try { S.brain.results = await api.brainSearch(q.trim(), 10); } catch (e) { toast(errText(e), true); S.brain.results = []; }
    S.brain.busy = false; renderBrainBody(); input?.focus();
  }, 450);
}

function docCard(d, text) {
  return el("button", { class: "m-card doc", onclick: () => openDoc(d.doc_id || d.id) },
    el("div", { class: "doc-top" }, el("b", {}, d.title || "(senza titolo)"), el("span", { class: "doc-src" }, SRC[d.source] || d.source)),
    text ? el("p", {}, text) : d.summary ? el("p", {}, d.summary) : null,
    el("small", {}, [d.pinned ? "📌 " : "", fmtDate(d.created_at), ...(d.why?.length ? [` · ${d.why.join(", ")}`] : []), ...(d.tags?.length ? [` · ${d.tags.slice(0, 3).join(", ")}`] : [])].join("")));
}

function renderBrainBody() {
  const box = document.getElementById("brain-body");
  if (!box) return;
  const { results, docs, busy } = S.brain;
  box.replaceChildren(...(busy ? [el("div", { class: "skel" }), el("div", { class: "skel" })]
    : results ? (results.length ? results.map((r) => docCard(r, r.snippet)) : [el("div", { class: "m-empty" }, el("div", { class: "ico" }, icon("sparkle", 30)), "Nessun risultato.", el("small", {}, "Prova con altre parole: cerco per significato.")) ])
    : docs == null ? [el("div", { class: "skel" }), el("div", { class: "skel" })]
    : docs.length ? [el("div", { class: "m-day" }, "Recenti"), ...docs.map((d) => docCard(d))]
    : [el("div", { class: "m-empty" }, el("div", { class: "ico" }, icon("sparkle", 32)), el("b", {}, "Il tuo secondo cervello è vuoto"), "Aggiungi una nota con +, oppure scrivi a JARVIS «ricorda che…».")]));
}

function buildBrain() {
  const wrap = el("div", { class: "m-chat" });
  const page = el("div", { class: "m-page" });
  const st = S.brain.stats;
  const search = el("input", { type: "text", placeholder: "Cerca nei tuoi ricordi…", value: S.brain.q, "aria-label": "Cerca", enterkeyhint: "search", autocomplete: "off" });
  search.addEventListener("input", () => brainSearch(search.value, search));
  page.append(el("div", { class: "m-head" }, el("h2", {}, "Cervello"), st ? el("span", { class: "m-pill" }, `${st.docs} doc`) : null), search,
    st ? el("p", { class: "m-note" }, `${st.chunks} frammenti${st.vectors < st.chunks ? ` · ${st.vectors} con ricerca per significato` : ""}`) : null, el("div", { id: "brain-body" }));
  pullToRefresh(page, () => { S.brain.results = null; loadBrain(); });
  wrap.append(page, el("button", { class: "m-fab", "aria-label": "Nuova nota", onclick: () => { haptic(); newNote(); } }, icon("plus", 26)));
  setTimeout(renderBrainBody, 0);
  return wrap;
}

function newNote() {
  const title = el("input", { type: "text", placeholder: "Titolo (facoltativo)", maxlength: 200 });
  const text = el("textarea", { rows: 6, placeholder: "Scrivi o incolla qui… oppure un link da salvare", style: "width:100%;border-radius:16px;background:var(--surf2);border:1px solid var(--line);padding:13px 15px;font-size:16px;margin-bottom:12px;resize:none" });
  const tags = el("input", { type: "text", placeholder: "Tag separati da virgola", maxlength: 120 });
  const s = openSheet("Nuova nota", title, text, tags, el("button", { class: "m-primary", style: "width:100%", onclick: async () => {
    const body = text.value.trim();
    if (body.length < 3) return toast("Scrivi qualcosa", true);
    try {
      const tg = tags.value.split(",").map((t) => t.trim()).filter(Boolean);
      const r = /^https?:\/\/\S+$/.test(body) ? await api.brainAddUrl(body, tg) : await api.brainAddNote(body, title.value.trim(), tg);
      s.close(); haptic("medium"); toast(r.status === "duplicato" ? "Già presente" : "Salvato nel cervello"); S.brain.results = null; loadBrain();
    } catch (e) { toast(errText(e), true); }
  } }, "Salva"));
  setTimeout(() => text.focus(), 280);
}

async function openDoc(id) {
  let d;
  try { d = await api.brainDoc(id); } catch (e) { return toast(errText(e), true); }
  const s = openSheet(d.title || "Documento",
    el("small", { class: "m-note" }, `${SRC[d.source] || d.source} · ${fmtDate(d.created_at)}${d.tags.length ? ` · ${d.tags.join(", ")}` : ""}`),
    d.summary ? el("p", { class: "ask-t", style: "text-align:left" }, d.summary) : null,
    el("div", { class: "notes-list", style: "white-space:pre-wrap;max-height:40vh" }, d.text + (d.truncated ? "\n[…]" : "")),
    d.related?.length ? el("div", {}, el("h3", { class: "m-sub" }, "Collegati"), ...d.related.map((r) => el("button", { class: "m-ghost", style: "margin:0 6px 6px 0", onclick: () => { s.close(); openDoc(r.doc_id); } }, r.title))) : null,
    el("div", { class: "m-btns", style: "margin-top:14px" },
      el("button", { class: "m-ghost", onclick: async () => { await api.brainPin(id, !d.pinned); s.close(); toast(d.pinned ? "Staccato" : "Fissato"); loadBrain(); } }, d.pinned ? "Stacca" : "Fissa"),
      el("button", { class: "m-ghost", style: "color:var(--bad)", onclick: async () => { await api.brainDelete(id); s.close(); toast("Eliminato"); S.brain.results = null; loadBrain(); } }, "Elimina")));
}

// ---------------------------------------------------------------- token
async function loadTokens(force = false) {
  if (!cfg.token) return;
  try { S.tokens = await api.tokens(force); S.tokensErr = ""; S.tokensAt = new Date(); } catch (e) { S.tokensErr = errText(e); }
  api.usage(14).then((u) => { S.usage = u; if (S.tab === "tokens") renderTab(); }).catch(() => {});
  if (S.tab === "tokens") renderTab();
}

function semi(p, big, small) {
  const R = 80, L = Math.PI * R;
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 200 112");
  const arc = (cls, len) => { const path = document.createElementNS(NS, "path"); path.setAttribute("d", "M20 100 A80 80 0 0 1 180 100"); path.setAttribute("class", cls); if (len != null) path.setAttribute("stroke-dasharray", `${len} ${L}`); return path; };
  const bar = arc(`s-bar${p < 15 ? " low" : p < 35 ? " mid" : ""}`, 0);
  bar.style.strokeDasharray = `0 ${L}`;
  svg.append(arc("s-track"), bar);
  requestAnimationFrame(() => requestAnimationFrame(() => { bar.style.strokeDasharray = `${(L * p) / 100} ${L}`; }));  // l'arco si riempie con la molla
  return el("div", { class: "semi" }, svg, el("div", { class: "semi-t" }, el("strong", {}, big), el("span", {}, small)));
}

function forecastCard(t) {
  const f = t.forecast;
  if (!f || f.days_left == null) return null;
  const bad = f.runs_out_before_reset;
  const when = f.depletes_on ? new Date(f.depletes_on).toLocaleDateString("it-IT", { day: "numeric", month: "long" }) : "";
  return el("div", { class: `m-card forecast${bad ? " warn" : ""}` },
    el("b", {}, bad ? `Al ritmo attuale finiscono il ${when}` : "Consumo sotto controllo"),
    el("p", { class: "m-note" }, bad ? `Prima del prossimo azzeramento. Consumi circa ${fmtTokens(f.burn_per_day)} al giorno: ti restano ~${Math.floor(f.days_left)} giorni.`
      : `Circa ${fmtTokens(f.burn_per_day)} al giorno: bastano per ~${Math.floor(f.days_left)} giorni, oltre l'azzeramento.`),
    t.jarvis_today ? el("small", {}, `Oggi JARVIS ha usato ${fmtTokens((t.jarvis_today.prompt_tokens || 0) + (t.jarvis_today.completion_tokens || 0))} token in ${t.jarvis_today.requests || 0} richieste`) : null);
}

function usageCard() {
  const u = S.usage;
  if (!u?.series?.length) return null;
  const max = Math.max(...u.series.map((d) => d.tokens), 1);
  const total = u.series.reduce((a, d) => a + d.tokens, 0);
  const avg = u.series.filter((d) => d.requests).reduce((a, d, _, arr) => a + d.avg_latency_ms / arr.length, 0);
  return el("div", { class: "m-card usage" },
    el("div", { class: "prov-top" }, el("b", {}, "Consumo di JARVIS"), el("span", {}, `${fmtTokens(total)} in ${u.series.length} g`)),
    el("div", { class: "bars", role: "img", "aria-label": "Token usati al giorno" }, u.series.map((d) =>
      el("i", { title: `${d.day}: ${fmtTokens(d.tokens)}`, style: `height:${Math.max(4, (d.tokens / max) * 100)}%` }))),
    el("small", {}, `Risposta media ${avg ? `${(avg / 1000).toFixed(1)} s` : "—"} · errori ${u.series.reduce((a, d) => a + d.errors, 0)}`));
}

function buildTokens() {
  const t = S.tokens;
  const page = el("div", { class: "m-page" });
  const head = el("div", { class: "m-head" }, el("h2", {}, "Token"), el("button", { class: "m-ghost", onclick: () => { haptic(); loadTokens(true); toast("Aggiorno…"); } }, icon("refresh", 16), "Aggiorna"));
  if (!t) {
    page.append(head, S.tokensErr ? el("div", { class: "m-empty" }, el("div", { class: "ico" }, icon("offline", 30)), S.tokensErr)
      : el("div", {}, el("div", { class: "skel", style: "height:230px" }), el("div", { class: "skel" }), el("div", { class: "skel" })));
    return page;
  }
  const p = pct(t.remaining_tokens, t.documented_monthly_tokens);
  const max = Math.max(...t.providers.map((x) => x.documented || x.remaining || 0), 1);
  page.append(head,
    el("div", { class: "m-card hero" },
      semi(p, fmtTokens(t.remaining_tokens), `${Math.round(p)}% disponibile`),
      el("div", { class: "m-kv" },
        el("div", {}, el("small", {}, "Budget"), el("b", {}, fmtTokens(t.documented_monthly_tokens))),
        el("div", {}, el("small", {}, "Usati"), el("b", {}, fmtTokens(t.used_tokens))),
        el("div", {}, el("small", {}, "Richieste"), el("b", {}, t.used_requests))),
      el("p", { class: "m-note" }, `${t.resets_at ? `Si azzera ${fmtDate(t.resets_at)}` : "Si azzera a inizio mese"}${S.tokensAt ? ` · aggiornato alle ${clock(S.tokensAt)}` : ""}`)),
    ...[forecastCard(t), usageCard()].filter(Boolean),  // (append(null) scriverebbe «null» nella pagina)
    el("h3", { class: "m-sub" }, "Per provider"),
    ...t.providers.map((x) => {
      const known = x.remaining != null;
      const share = x.documented ? (x.remaining || 0) / x.documented : 1;
      return el("div", { class: "m-card prov" },
        el("div", { class: "prov-top" }, el("b", {}, x.platform, x.source === "live" ? el("span", { class: "badge-live" }, "live") : null), el("span", {}, known ? fmtTokens(x.remaining) : "n/d")),
        el("div", { class: "m-bar" }, el("i", { class: known && share < 0.15 ? "low" : "", style: `width:${known ? Math.max(2, ((x.remaining || 0) / max) * 100) : 0}%` })),
        el("small", {}, x.source === "live" ? "quota reale" : x.source === "estimate" ? "stima dal budget mensile" : "senza budget pubblicato"));
    }),
    el("p", { class: "m-note" }, t.note));
  pullToRefresh(page, () => { loadTokens(true); toast("Aggiorno…"); });
  if (S.countKey !== t.remaining_tokens && !matchMedia("(prefers-reduced-motion: reduce)").matches) {  // il numero principale sale da zero
    S.countKey = t.remaining_tokens;
    const num = page.querySelector(".semi-t strong");
    if (num) { num.textContent = fmtTokens(0); setTimeout(() => countUp(num, t.remaining_tokens), 140); }
  }
  return page;
}

function countUp(node, to) {
  const t0 = performance.now(), D = 950;
  const step = (now) => { const k = Math.min(1, (now - t0) / D); node.textContent = fmtTokens(Math.round(to * (1 - (1 - k) ** 3))); if (k < 1) requestAnimationFrame(step); };
  requestAnimationFrame(step);
}

// ---------------------------------------------------------------- promemoria
async function loadReminders() {
  if (!cfg.token) return;
  try { S.reminders = await api.reminders(); S.remindersLoaded = true; } catch (e) { toast(errText(e), true); }
  renderTabs();
  if (S.tab === "reminders") renderTab();
}

/** Allinea ora con il Calendario Google e mostra l'esito (o la causa dell'errore). */
async function syncNow() {
  try {
    const r = await api.syncReminders();
    if (S.status) S.status.calendar_sync = { ...r.status, linked: r.linked };
    const c = r.counts || {}, n = (c.created || 0) + (c.updated || 0) + (c.removed || 0) + (c.imported || 0);
    toast(!r.linked ? "Google non è collegato" : r.status.ok === false ? r.status.detail : n ? `Calendario allineato (${n} modifiche)` : "Calendario già allineato", r.status.ok === false);
  } catch (e) { toast(errText(e), true); }
  loadReminders();
}

function openSheet(title, ...body) {
  const entry = { close: null };
  const close = () => { sheet.classList.remove("up"); setTimeout(() => sheet.remove(), 240); S.sheets = S.sheets.filter((s) => s !== entry); };
  const sheet = el("div", { class: "m-sheet-bg", onclick: (e) => e.target === sheet && close() },
    el("div", { class: "m-sheet", role: "dialog", "aria-label": title }, el("i", { class: "grab" }), el("h3", {}, title), ...body));
  entry.close = close;
  S.sheets.push(entry);
  document.body.append(sheet);
  requestAnimationFrame(() => sheet.classList.add("up"));
  // il foglio si chiude trascinando verso il basso la maniglia o il titolo (come su iOS)
  const box = sheet.firstElementChild;
  for (const grip of [box.querySelector(".grab"), box.querySelector("h3")]) {
    if (!grip) continue;
    let y0 = null, dy = 0;
    grip.addEventListener("touchstart", (e) => { y0 = e.touches[0].clientY; dy = 0; box.classList.add("drag"); }, { passive: true });
    grip.addEventListener("touchmove", (e) => { if (y0 == null) return; dy = Math.max(0, e.touches[0].clientY - y0); box.style.transform = `translateY(${dy}px)`; sheet.style.opacity = String(1 - Math.min(0.6, dy / 420)); }, { passive: true });
    grip.addEventListener("touchend", () => { if (y0 == null) return; box.classList.remove("drag"); box.style.transform = ""; sheet.style.opacity = ""; y0 = null; if (dy > 110) { haptic(); close(); } });
  }
  return { close, sheet };
}

const localInput = (d) => { const x = new Date(d.getTime() - d.getTimezoneOffset() * 60_000); return x.toISOString().slice(0, 16); };
const atHour = (h, plusDays = 0) => { const d = new Date(); d.setDate(d.getDate() + plusDays); d.setHours(h, 0, 0, 0); return d; };

const REPEAT_OPTIONS = [["", "Una volta sola"], ["daily", "Ogni giorno"], ["weekdays", "Nei giorni feriali"], ["weekly", "Ogni settimana"], ["monthly", "Ogni mese"], ["yearly", "Ogni anno"]];
const repeatLabel = (v) => (REPEAT_OPTIONS.find(([k]) => k === v) || [])[1] || "";

function newReminder() {
  const text = el("input", { type: "text", placeholder: "Cosa devo ricordarti?", maxlength: 500, "aria-label": "Testo" });
  const when = el("input", { type: "datetime-local", value: localInput(new Date(Date.now() + 3_600_000)), "aria-label": "Quando" });
  const presets = [["Tra 15 min", () => new Date(Date.now() + 900_000)], ["Tra 1 ora", () => new Date(Date.now() + 3_600_000)],
    ["Stasera 21:00", () => (atHour(21) > new Date() ? atHour(21) : atHour(21, 1))], ["Domani 9:00", () => atHour(9, 1)]];
  const repeat = el("select", { class: "m-select", "aria-label": "Ripetizione" }, REPEAT_OPTIONS.map(([v, l]) => el("option", { value: v }, l)));
  const s = openSheet("Nuovo promemoria", text,
    el("div", { class: "m-presets" }, presets.map(([l, f]) => el("button", { onclick: () => { when.value = localInput(f()); haptic(); } }, l))), when,
    el("label", { class: "m-inline" }, el("span", {}, icon("refresh", 16), "Ripeti"), repeat),
    el("button", { class: "m-primary", style: "width:100%", onclick: async () => {
      if (!text.value.trim()) return toast("Scrivi cosa ricordare", true);
      try { await api.addReminder(text.value.trim(), when.value, repeat.value); s.close(); haptic("medium"); toast("Promemoria creato"); loadReminders(); } catch (e) { toast(errText(e), true); }
    } }, "Crea"));
  setTimeout(() => text.focus(), 280);
}

function relDue(iso) {
  const d = new Date(iso), mins = Math.round((d - Date.now()) / 60_000);
  const hm = clock(d);
  if (mins < 0) return { label: `scaduto · ${hm}`, soon: true };
  if (mins < 60) return { label: `tra ${Math.max(mins, 1)} min`, soon: true };
  const sameDay = d.toDateString() === new Date().toDateString();
  if (sameDay) return { label: `oggi ${hm} · tra ${Math.floor(mins / 60)} h`, soon: false };
  const tomorrow = new Date(Date.now() + 86_400_000).toDateString() === d.toDateString();
  return { label: tomorrow ? `domani ${hm}` : d.toLocaleDateString("it-IT", { weekday: "short", day: "numeric", month: "short" }) + ` ${hm}`, soon: false };
}

async function removeReminder(r) {
  try {
    await api.deleteReminder(r.id);
    S.reminders = S.reminders.filter((x) => x.id !== r.id);
    renderTabs(); renderTab(); haptic("medium");
    toast("Promemoria eliminato", false, { label: "Annulla", fn: async () => { try { await api.addReminder(r.text, localInput(new Date(r.due_at)), r.repeat || ""); loadReminders(); } catch (e) { toast(errText(e), true); } } });
  } catch (e) { toast(errText(e), true); renderTab(); }
}

function reminderCard(r) {
  const due = relDue(r.due_at);
  const card = el("div", { class: `m-card rem${new Date(r.due_at) < Date.now() ? " late" : due.soon ? " soon" : ""}` }, el("div", {}, el("b", {}, r.text), el("small", { class: due.soon ? "soon" : "" }, due.label), r.repeat ? el("small", { class: "rep" }, `🔁 ${repeatLabel(r.repeat)}`) : null, r.event_id ? el("small", { class: "cal" }, "📅 Calendario") : null),
    el("button", { class: "m-icon", "aria-label": "Elimina", onclick: () => removeReminder(r) }, icon("trash", 19)));
  let x0 = null, dx = 0;
  card.addEventListener("touchstart", (e) => { x0 = e.touches[0].clientX; dx = 0; card.classList.add("drag"); }, { passive: true });
  card.addEventListener("touchmove", (e) => { if (x0 == null) return; dx = Math.min(0, e.touches[0].clientX - x0); card.style.transform = `translateX(${dx}px)`; }, { passive: true });
  card.addEventListener("touchend", () => { card.classList.remove("drag"); if (dx < -110) removeReminder(r); else card.style.transform = ""; x0 = null; });
  return el("div", { class: "swipe" }, el("div", { class: "under" }, icon("trash", 22)), card);
}

function buildReminders() {
  const wrap = el("div", { class: "m-chat" });
  const page = el("div", { class: "m-page" });
  page.append(el("div", { class: "m-head" }, el("h2", {}, "Promemoria"), el("button", { class: "m-ghost", onclick: () => { haptic(); syncNow(); } }, icon("refresh", 16), "Sincronizza")));
  const cs = S.status?.calendar_sync;
  if (cs?.linked && cs.ok === false) page.append(el("div", { class: "m-warn" }, icon("bell", 18), el("div", {}, el("b", {}, "Calendario non sincronizzato"), el("small", {}, cs.detail || "Errore sconosciuto.")),
    el("button", { class: "m-ghost", onclick: () => syncNow() }, "Riprova")));
  else if (cs?.linked && cs.ok) page.append(el("p", { class: "m-note ok cal-ok" }, `📅 Calendario Google sincronizzato alle ${new Date(cs.at).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" })}`));
  else if (cs && !cs.linked && cfg.token) page.append(el("p", { class: "m-note" }, "Google non è collegato: i promemoria restano solo nell'app (collegalo da Telegram con /google)."));
  if (!S.remindersLoaded && cfg.token) page.append(el("div", { class: "skel" }), el("div", { class: "skel" }));
  else if (!S.reminders.length) page.append(el("div", { class: "m-empty" }, el("div", { class: "ico" }, icon("clock", 32)), el("b", {}, "Nessun promemoria"), "Tocca + oppure chiedilo a JARVIS: te lo ricordo all'ora giusta, qui e su Telegram."));
  else {
    const groups = new Map();
    for (const r of [...S.reminders].sort((a, b) => new Date(a.due_at) - new Date(b.due_at))) {
      const d = new Date(r.due_at), today = new Date().toDateString();
      const key = d < Date.now() ? "Scaduti" : d.toDateString() === today ? "Oggi" : d.toDateString() === new Date(Date.now() + 86_400_000).toDateString() ? "Domani" : "Più avanti";
      groups.set(key, [...(groups.get(key) || []), r]);
    }
    for (const [name, rows] of groups) page.append(el("div", { class: "m-day" }, name), ...rows.map(reminderCard));
  }
  pullToRefresh(page, loadReminders);
  wrap.append(page, el("button", { class: "m-fab", "aria-label": "Nuovo promemoria", onclick: () => { haptic(); newReminder(); } }, icon("plus", 26)));
  return wrap;
}

// ---------------------------------------------------------------- aggiornamenti dell'app
// ---------------------------------------------------------------- aggiornamenti dell'app
const WHATS_NEW = [
  ["phone", "Chiamate", "Chiama con Telefono o WhatsApp da Altro o chiedilo a JARVIS (con la tua conferma). L'app ora resta solo in verticale."],
  ["shield", "Risposta automatica", "JARVIS accetta le chiamate solo dai numeri che autorizzi e solo se lo attivi; ogni risposta resta nel registro."],
  ["sparkle", "Segreteria con voce", "Con Twilio, JARVIS risponde a voce alle chiamate inoltrate e ti riferisce il messaggio."],
  ["refresh", "Promemoria ricorrenti", "Ogni giorno, nei feriali, ogni settimana, mese o anno."],
];
const skipped = () => store.get("jarvis.skipver");
function hiddenToday(v) { try { const h = JSON.parse(store.get("jarvis.updhide", "{}")); return h.v === v && Date.now() - h.t < 864e5; } catch { return false; } }
const updateVisible = () => !!(S.update?.available && skipped() !== S.update.latest && !hiddenToday(S.update.latest));
const trustedDownload = (u) => /^https:\/\/github\.com\/[\w.-]+\/[\w.-]+\/releases\/download\/[^\s]+$/.test(u || "");

async function checkUpdate(manual = false) {
  if (!cfg.token || platform !== "android") { if (manual) toast("Gli aggiornamenti si controllano dall'app Android"); return; }
  try {
    S.appVer = S.appVer || await appVersion();
    if (!S.appVer) return;
    S.update = await api.appUpdate("android", S.appVer);
    if (manual) { store.del("jarvis.skipver"); store.del("jarvis.updhide"); toast(S.update.available ? `Disponibile la ${S.update.latest}` : "Sei già alla versione più recente"); }
    whatsNew();
  } catch (e) { if (manual) toast(errText(e), true); }
  renderTop();
  if (S.tab === "more") renderTab();
}

/** Dopo un aggiornamento (versione diversa dall'ultima vista) mostra una volta cosa è cambiato. */
function whatsNew() {
  const last = store.get("jarvis.lastver");
  if (last === S.appVer) return;
  store.set("jarvis.lastver", S.appVer);
  if (!last) return;  // prima installazione: niente
  openSheet(`Novità della ${S.appVer}`, el("div", { class: "wn" }, WHATS_NEW.map(([ic, t, d], i) => el("div", { class: "wn-row", style: `--i:${i}` }, el("span", { class: "m-note-ic" }, icon(ic, 18)), el("div", {}, el("b", {}, t), el("p", {}, d))))),
    el("div", { class: "m-btns" }, el("button", { class: "m-primary", onclick: () => S.sheets.at(-1)?.close() }, "Ottimo")));
}

function openUpdate() {
  const u = S.update;
  if (!u?.available) return toast("Nessun aggiornamento disponibile");
  const notes = (u.notes || "").replace(/(^|\n)#{1,3} Installazione[\s\S]*?(?=\n#{1,3} |$)/, "").replace(/^#{1,6}\s*(.+)$/gm, "**$1**").trim().slice(0, 900);
  const copy = () => navigator.clipboard?.writeText(u.sha256).then(() => toast("SHA-256 copiato")).catch(() => toast("Copia non riuscita", true));
  const s = openSheet("Aggiornamento disponibile",
    el("div", { class: "ver-line" }, el("span", { class: "ver" }, u.current), el("span", { class: "ver-arrow" }, icon("down", 18)), el("span", { class: "ver new" }, u.latest)),
    el("div", { class: "m-chips-row" }, u.size ? el("span", { class: "pill" }, `${(u.size / 1048576).toFixed(1)} MB`) : null, u.published_at ? el("span", { class: "pill" }, fmtDate(u.published_at)) : null,
      u.sha256 ? el("span", { class: "pill ok" }, icon("shield", 13), "SHA-256 verificabile") : null),
    notes ? el("div", { class: "upd-notes" }, markdown(notes)) : null,
    el("ol", { class: "upd-steps" }, el("li", {}, "Scarica l'APK dal sito ufficiale del progetto."), el("li", {}, "Aprilo e consenti l'installazione da questa origine."), el("li", {}, "Installa sopra l'app attuale: dati e impostazioni restano.")),
    u.sha256 ? el("button", { class: "sha", onclick: copy, "aria-label": "Copia SHA-256" }, el("small", {}, "SHA-256"), el("code", {}, `${u.sha256.slice(0, 16)}…${u.sha256.slice(-8)}`), icon("copy", 14)) : null,
    el("div", { class: "m-btns" },
      el("button", { class: "m-ghost", onclick: () => { store.set("jarvis.updhide", JSON.stringify({ v: u.latest, t: Date.now() })); s.close(); renderTop(); } }, "Più tardi"),
      el("button", { class: "m-primary", onclick: () => {
        if (!trustedDownload(u.url)) { toast("Indirizzo di download non attendibile: non lo apro.", true); return haptic("heavy"); }
        haptic("medium"); s.close(); openExternal(u.url);
      } }, "Scarica e installa")),
    el("button", { class: "m-linkbtn", onclick: () => { store.set("jarvis.skipver", u.latest); s.close(); renderTop(); renderTab(); toast(`Salto la ${u.latest}: ti avviso alla prossima`); } }, "Salta questa versione"));
}

// ---------------------------------------------------------------- competenze
async function openSkills() {
  let data;
  try { data = await api.skills(); } catch (e) { return toast(errText(e), true); }
  const list = el("div", { class: "notes-list", style: "max-height:56vh" });
  const s = openSheet("Competenze di JARVIS", el("p", { class: "m-note" }, "Si attivano da sole quando la richiesta le riguarda. Toccane una per usarla nella prossima domanda."), list);
  for (const [domain, label] of Object.entries(data.domains)) {
    const rows = data.skills.filter((x) => x.domain === domain);
    if (!rows.length) continue;
    list.append(el("h3", { class: "m-sub" }, `${label} (${rows.length})`),
      ...rows.map((x) => el("button", { class: "m-card doc", onclick: () => { S.skill = x; s.close(); setTab("chat"); renderSkillChip(); input?.focus(); haptic(); toast(`Competenza attiva: ${x.title}`); } },
        el("div", { class: "doc-top" }, el("b", {}, x.title), x.builtin ? null : el("span", { class: "doc-src" }, "tua")), el("p", {}, x.description))));
  }
}

// ---------------------------------------------------------------- impostazioni delle notifiche e del modello
const KIND_LABEL = { reminder: "Promemoria", alert: "Avvisi (token, sicurezza)", pending: "Conferme richieste", update: "Aggiornamenti app", brain: "Secondo cervello", proactive: "Suggerimenti di JARVIS (eventi, email, riepiloghi)", info: "Informazioni" };

async function openNotifySettings() {
  let p;
  try { p = await api.notifyPrefs(); } catch (e) { return toast(errText(e), true); }
  const save = async () => { try { S.prefs = await api.setNotifyPrefs(p); } catch (e) { toast(errText(e), true); } };
  const sw = (k, ch) => el("input", { type: "checkbox", class: "m-switch", "aria-label": `${KIND_LABEL[k]} ${ch}`, checked: p.kinds[k][ch], onchange: (e) => { p.kinds[k][ch] = e.target.checked; save(); haptic(); } });
  const from = el("input", { type: "time", value: p.quiet.from, onchange: (e) => { p.quiet.from = e.target.value; save(); } });
  const to = el("input", { type: "time", value: p.quiet.to, onchange: (e) => { p.quiet.to = e.target.value; save(); } });
  openSheet("Notifiche",
    el("div", { class: "notif-grid" }, el("span", {}), el("small", {}, "App"), el("small", {}, "Push"), el("small", {}, "Telegram"),
      Object.keys(KIND_LABEL).filter((k) => p.kinds[k]).flatMap((k) => [el("span", {}, KIND_LABEL[k]), sw(k, "inapp"), sw(k, "push"), sw(k, "telegram")])),
    el("div", { class: "m-row" }, el("span", {}, "Ore silenziose"), el("input", { type: "checkbox", class: "m-switch", "aria-label": "Ore silenziose", checked: p.quiet.enabled, onchange: (e) => { p.quiet.enabled = e.target.checked; save(); } })),
    el("div", { class: "m-presets" }, el("label", {}, "Dalle ", from), el("label", {}, "Alle ", to)),
    el("p", { class: "m-note" }, "Promemoria, avvisi e conferme arrivano comunque nelle ore silenziose."));
}

async function openModelPicker() {
  let list;
  try { list = await api.models(); } catch (e) { return toast(errText(e), true); }
  const cur = store.get("jarvis.model");
  const s = openSheet("Modello di intelligenza", el("p", { class: "m-note" }, "«Automatico» sceglie da solo il migliore disponibile e passa al successivo se uno è esaurito."),
    el("div", { class: "notes-list" }, list.map((m) => el("button", { class: `m-ghost model${(cur || "auto") === m.id ? " on" : ""}`, onclick: () => {
      store.set("jarvis.model", m.id === "auto" ? "" : m.id); s.close(); toast(m.id === "auto" ? "Modello automatico" : `Modello: ${m.id}`); if (S.tab === "more") renderTab();
    } }, m.id === "auto" ? "Automatico (consigliato)" : m.id))));
}

// ---------------------------------------------------------------- altro
function row(label, value, ok) { return el("div", { class: "m-row" }, el("span", {}, label), el("b", { class: ok === undefined ? "" : ok ? "ok" : "off" }, value)); }

// ---------------------------------------------------------------- sicurezza: PIN, blocco automatico, copertura nelle app recenti
const pinSet = () => !!store.get("jarvis.pin");
const autolock = () => Number(store.get("jarvis.autolock", "30"));
const privacyOn = () => store.get("jarvis.privacy", "1") !== "0";

function pinSheet(title, hint, onDone, { confirm = false } = {}) {
  const a = el("input", { type: "password", inputmode: "numeric", maxlength: "6", autocomplete: "off", placeholder: "••••••", "aria-label": "PIN" });
  const b = confirm ? el("input", { type: "password", inputmode: "numeric", maxlength: "6", autocomplete: "off", placeholder: "Ripeti il PIN", "aria-label": "Ripeti il PIN" }) : null;
  const err = el("p", { class: "m-note bad" });
  const s = openSheet(title, el("p", { class: "m-note" }, hint), el("div", { class: "m-card form pin-form" }, a, b), err,
    el("div", { class: "m-btns" }, el("button", { class: "m-ghost", onclick: () => s.close() }, "Annulla"),
      el("button", { class: "m-primary", onclick: async () => {
        if (!/^\d{6}$/.test(a.value)) { err.textContent = "Servono esattamente 6 cifre."; return haptic("heavy"); }
        if (b && a.value !== b.value) { err.textContent = "I due PIN non coincidono."; return haptic("heavy"); }
        if (await onDone(a.value, err) !== false) s.close();
      } }, "Conferma")));
  setTimeout(() => a.focus(), 350);
}

function securityCard() {
  const lockSwitch = el("input", { type: "checkbox", class: "m-switch", "aria-label": "Blocco con PIN", checked: pinSet(), onchange: (e) => {
    const box = e.target;
    if (box.checked) pinSheet("Imposta il PIN", "Sei cifre. Lo chiedo all'apertura e dopo il tempo che scegli in background. Non lascia mai il telefono.", async (pin) => {
      store.set("jarvis.pin", await makePin(pin)); store.set("jarvis.lockfails", "0"); toast("Blocco attivato"); haptic("medium"); renderTab();
    }, { confirm: true });
    else pinSheet("Disattiva il blocco", "Inserisci il PIN attuale.", async (pin, err) => {
      if (!(await checkPin(pin, store.get("jarvis.pin")))) { err.textContent = "PIN errato."; haptic("heavy"); return false; }
      store.del("jarvis.pin"); toast("Blocco disattivato"); renderTab();
    });
    box.checked = !box.checked;  // lo stato vero lo decide la schermata dopo la conferma
    haptic();
  } });
  const autoSeg = el("div", { class: "m-seg", role: "group", "aria-label": "Blocca dopo" }, [["0", "Subito"], ["30", "30 s"], ["300", "5 min"]].map(([v, l]) =>
    el("button", { class: String(autolock()) === v ? "on" : "", onclick: (e) => { store.set("jarvis.autolock", v); autoSeg.querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === e.currentTarget)); haptic(); } }, l)));
  const privSwitch = el("input", { type: "checkbox", class: "m-switch", "aria-label": "Nascondi il contenuto nelle app recenti", checked: privacyOn(),
    onchange: (e) => { store.set("jarvis.privacy", e.target.checked ? "1" : "0"); haptic(); } });
  return el("div", { class: "m-card" },
    el("label", { class: "m-row" }, el("span", {}, "Blocco con PIN"), lockSwitch),
    pinSet() ? el("div", { class: "m-row stack" }, el("span", {}, "Blocca dopo"), autoSeg) : null,
    el("label", { class: "m-row" }, el("span", {}, "Nascondi il contenuto nelle app recenti"), privSwitch),
    el("p", { class: "m-note" }, cryptoOk() ? "🔐 Il token personale è cifrato sul telefono con una chiave che l'app non può esportare." : "Cifratura del token non disponibile in questo browser."));
}

// ---------------------------------------------------------------- telefono e WhatsApp
async function loadPhone() {
  if (!phoneAvailable) return;
  try { S.phone = await phone.status(); } catch { return; }
  rerenderMore();
}
const phoneOk = () => !!S.phone && Object.values(S.phone.perms).every(Boolean);
const missingPerms = () => (S.phone ? Object.values(S.phone.perms).filter((v) => !v).length : 4);

function phoneCard() {
  const ph = S.phone, auto = ph?.auto;
  const allowed = auto?.allowed || [];
  const sw = el("input", { type: "checkbox", class: "m-switch", "aria-label": "Risposta automatica alle chiamate", checked: !!auto?.enabled,
    onchange: (e) => { e.target.checked ? confirmAutoAnswer(e.target) : saveAuto({ enabled: false }); } });
  return el("div", { class: "m-card" },
    row("Permessi", !ph ? "…" : phoneOk() ? "concessi" : `mancano ${missingPerms()}`, !ph ? undefined : phoneOk()),
    !phoneOk() ? el("div", { class: "m-row" }, el("span", {}, "Servono per chiamare, leggere i contatti e rispondere"), el("button", { class: "m-ghost", onclick: async () => { try { S.phone = await phone.requestPermissions(); } catch (e) { toast(errText(e), true); } rerenderMore(); } }, "Concedi")) : null,
    el("div", { class: "m-row" }, el("span", {}, "Chiama con Telefono o WhatsApp"), el("button", { class: "m-ghost", onclick: () => openCallSheet() }, icon("phone", 16), "Chiama")),
    el("label", { class: "m-row" }, el("span", {}, "Rispondi da solo ai numeri autorizzati"), sw),
    el("div", { class: "m-row" }, el("span", {}, allowed.length ? `Numeri autorizzati: ${allowed.length}` : "Nessun numero autorizzato"), el("button", { class: "m-ghost", onclick: openAllowSheet }, icon("sliders", 16), "Gestisci")),
    el("div", { class: "m-row" }, el("span", {}, "Registro delle chiamate gestite"), el("button", { class: "m-ghost", onclick: openPhoneLog }, "Apri")),
    el("div", { class: "m-row" }, el("span", {}, "Segreteria con voce e intelligenza artificiale"), el("button", { class: "m-ghost", onclick: openVoiceLine }, icon("sparkle", 16), "Imposta")),
    el("p", { class: "m-note" }, "JARVIS risponde (accetta la chiamata, con il viva voce se vuoi) solo se la funzione è attiva e il numero è nell'elenco. Non può parlare al posto tuo: Android non lo permette alle app. Le chiamate WhatsApp non si possono accettare da un'app."));
}

async function saveAuto(patch) {
  const cur = S.phone?.auto || { enabled: false, allowed: [], delay: 3, speaker: false };
  try { S.phone = await phone.setAuto({ ...cur, ...patch }); haptic(); } catch (e) { toast(e?.message || errText(e), true); }
  rerenderMore();
}

/** L'attivazione non è un semplice interruttore: spiega cosa succede e chiede un consenso esplicito. */
function confirmAutoAnswer(box) {
  if (!(S.phone?.auto?.allowed || []).length) { box.checked = false; toast("Prima aggiungi almeno un numero autorizzato", true); return openAllowSheet(); }
  if (!S.phone.perms.answer || !S.phone.perms.state) { box.checked = false; toast("Concedi prima i permessi del telefono", true); return; }
  box.checked = false;
  const s = openSheet("Rispondere da solo?", el("div", { class: "ask" }, icon("shield", 30)),
    el("p", { class: "ask-t" }, `JARVIS accetterà le chiamate telefoniche in arrivo solo da ${S.phone.auto.allowed.length} numer${S.phone.auto.allowed.length === 1 ? "o" : "i"} che hai autorizzato, dopo alcuni secondi di squillo. Le altre chiamate non vengono toccate.`),
    el("small", { class: "m-note" }, "Puoi disattivarlo in qualsiasi momento da qui. Ogni risposta resta nel registro."),
    el("div", { class: "m-btns" }, el("button", { class: "m-ghost", onclick: () => s.close() }, "Annulla"), el("button", { class: "m-primary", onclick: () => { s.close(); saveAuto({ enabled: true }); } }, "Autorizza")));
}

function openAllowSheet() {
  const q = el("input", { type: "text", placeholder: "Cerca nei contatti o scrivi un numero", "aria-label": "Contatto o numero", autocapitalize: "off" });
  const results = el("div", { class: "pick-list" });
  const list = el("div", { class: "pick-list" });
  const s = openSheet("Numeri autorizzati", q, results, el("h3", { class: "m-sub" }, "Autorizzati"), list);
  const draw = () => {
    const cur = S.phone?.auto?.allowed || [];
    list.replaceChildren(...(cur.length ? cur.map((a) => el("div", { class: "pick-row" }, el("span", {}, el("b", {}, a.name || a.number), a.name ? el("small", {}, a.number) : null),
      el("button", { class: "m-icon", "aria-label": "Rimuovi", onclick: async () => { await saveAuto({ allowed: cur.filter((x) => x !== a), enabled: cur.length > 1 && S.phone.auto.enabled }); draw(); } }, icon("trash", 18))))
      : [el("p", { class: "m-note" }, "Nessuno: JARVIS non risponderà a nessuna chiamata.")]));
  };
  const add = async (name, number) => {
    const cur = S.phone?.auto?.allowed || [];
    if (cur.some((a) => a.number.replace(/\D/g, "").slice(-9) === number.replace(/\D/g, "").slice(-9))) return toast("Già autorizzato");
    await saveAuto({ allowed: [...cur, { name, number }] }); q.value = ""; results.replaceChildren(); draw(); toast(`${name || number} autorizzato`);
  };
  let timer = 0;
  q.addEventListener("input", () => {
    clearTimeout(timer); const v = q.value.trim();
    if (NUMBER_RE.test(v)) return results.replaceChildren(el("button", { class: "pick-row", onclick: () => add("", v) }, el("span", {}, el("b", {}, v), el("small", {}, "Aggiungi questo numero")), icon("plus", 18)));
    if (v.length < 2) return results.replaceChildren();
    timer = setTimeout(async () => {
      try {
        const found = await phone.findContacts(v);
        results.replaceChildren(...(found.length ? found.flatMap((c) => c.numbers.map((n) => el("button", { class: "pick-row", onclick: () => add(c.name, n) }, el("span", {}, el("b", {}, c.name), el("small", {}, n)), icon("plus", 18))))
          : [el("p", { class: "m-note" }, "Nessun contatto trovato.")]));
      } catch (e) { results.replaceChildren(el("p", { class: "m-note bad" }, e?.message || "Concedi il permesso Contatti")); }
    }, 250);
  });
  draw();
}

function openCallSheet(prefill = "", meta = {}) {
  const q = el("input", { type: "text", placeholder: "Nome in rubrica o numero", "aria-label": "Chi chiamare", value: prefill, autocapitalize: "off" });
  const video = el("input", { type: "checkbox", class: "m-switch", "aria-label": "Videochiamata", checked: !!meta.video });
  const results = el("div", { class: "pick-list" });
  const go = async (way, name, number) => {
    try {
      if (way === "whatsapp") { const r = await phone.whatsapp({ number, name, video: video.checked }); toast(r.method === "chat" ? "Chat WhatsApp aperta: tocca l'icona del telefono" : `Chiamo ${name || number} su WhatsApp…`); }
      else { await phone.dial(number); toast(`Chiamo ${name || number}…`); }
      s.close(); haptic("medium");
    } catch (e) { toast(e?.message || "Chiamata non riuscita", true); }
  };
  const rowFor = (name, number) => el("div", { class: "pick-row" }, el("span", {}, el("b", {}, name || number), name ? el("small", {}, number) : null),
    el("div", { class: "pick-act" }, el("button", { class: "m-ghost", onclick: () => go("phone", name, number) }, icon("phone", 15), "Telefono"), el("button", { class: "m-ghost", onclick: () => go("whatsapp", name, number) }, "WhatsApp")));
  const s = openSheet("Chiama", q, el("label", { class: "m-inline" }, el("span", {}, "Videochiamata (WhatsApp)"), video), results);
  const search = async () => {
    const v = q.value.trim();
    if (NUMBER_RE.test(v)) return results.replaceChildren(rowFor("", v));
    if (v.length < 2) return results.replaceChildren();
    try {
      const found = await phone.findContacts(v);
      results.replaceChildren(...(found.length ? found.flatMap((c) => c.numbers.map((n) => rowFor(c.name, n))) : [el("div", {}, el("p", { class: "m-note" }, "Nessun contatto con questo nome."), meta.via === "whatsapp" ? el("button", { class: "m-ghost", onclick: () => go("whatsapp", v, "") }, "Prova con WhatsApp") : null)]));
    } catch (e) { results.replaceChildren(el("p", { class: "m-note bad" }, e?.message || "Concedi il permesso Contatti")); }
  };
  let timer = 0;
  q.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(search, 250); });
  if (prefill) search(); else setTimeout(() => q.focus(), 280);
}

/** Segreteria telefonica con voce (Twilio): JARVIS risponde alle chiamate inoltrate a un numero Twilio, parla e riferisce il messaggio. */
async function openVoiceLine() {
  let cfg;
  try { cfg = await api.callsConfig(); } catch (e) { return toast(errText(e), true); }
  const mode = el("select", { class: "m-select", "aria-label": "Modalità" }, [["off", "Spenta"], ["allowed", "Solo numeri autorizzati"], ["all", "Tutti i chiamanti"]].map(([v, l]) => el("option", { value: v, selected: cfg.mode === v }, l)));
  const greet = el("input", { type: "text", maxlength: 300, placeholder: "Saluto (facoltativo)", value: cfg.greeting || "", "aria-label": "Saluto" });
  const copy = (text) => async () => { try { await navigator.clipboard.writeText(text); toast("Copiato"); } catch { toast(text); } };
  const s = openSheet("Segreteria con voce", cfg.enabled ? el("p", { class: "m-note ok" }, "Collegata: manca solo l'inoltro dal tuo telefono.") : el("p", { class: "m-note bad" }, "Non attiva: su Render imposta TWILIO_AUTH_TOKEN (il token del tuo account Twilio)."),
    el("label", { class: "m-inline" }, el("span", {}, "Rispondi a"), mode), greet,
    el("p", { class: "m-note" }, "Con «Solo numeri autorizzati» usa l'elenco della risposta automatica. JARVIS non ha accesso a nulla di privato durante la chiamata: prende solo un messaggio e te lo riferisce."),
    el("div", { class: "m-row" }, el("span", {}, "Indirizzo della voce (Twilio)"), el("button", { class: "m-ghost", onclick: copy(cfg.voice_url) }, "Copia")),
    el("div", { class: "m-row" }, el("span", {}, "Indirizzo dello stato (Twilio)"), el("button", { class: "m-ghost", onclick: copy(cfg.status_url) }, "Copia")),
    el("p", { class: "m-note" }, "Su Twilio, nel numero scelto, metti questi due indirizzi (metodo POST) in «A call comes in» e «Call status changes». Poi inoltra al numero Twilio le chiamate senza risposta: da tastiera **61*NUMERO# (inoltro se non rispondi)."),
    el("button", { class: "m-primary", style: "width:100%", onclick: async () => {
      try { await api.setCallsConfig(mode.value, S.phone?.auto?.allowed || [], greet.value.trim()); s.close(); toast(mode.value === "off" ? "Segreteria spenta" : "Segreteria impostata"); haptic("medium"); } catch (e) { toast(errText(e), true); }
    } }, "Salva"));
}

async function openPhoneLog() {
  let rows = [];
  try { rows = await phone.log(); } catch (e) { toast(errText(e), true); }
  const body = rows.length ? rows.map((r) => el("div", { class: "m-row" }, el("span", {}, r.e), el("small", {}, new Date(r.t).toLocaleString("it-IT", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }))))
    : [el("p", { class: "m-note" }, "Ancora nessuna chiamata gestita.")];
  const s = openSheet("Registro del telefono", ...body, rows.length ? el("button", { class: "m-ghost", style: "width:100%;margin-top:10px", onclick: async () => { await phone.log(true); s.close(); toast("Registro svuotato"); } }, "Svuota") : null);
}

async function loadBackup() {
  if (!cfg.token) return;
  try { S.backup = (await api.serverHealth()).backup || {}; } catch { return; }
  rerenderMore();
}
/** Ridisegna «Altro» senza far tornare in cima la pagina. */
function rerenderMore() {
  if (S.tab !== "more") return;
  const y = content.querySelector(".m-page")?.scrollTop || 0;
  renderTab();
  const page = content.querySelector(".m-page"); if (page) page.scrollTop = y;
}
function backupCard() {
  const b = S.backup;
  const when = b?.at ? new Date(b.at).toLocaleString("it-IT", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "";
  const btn = el("button", { class: "m-ghost", onclick: async (e) => {
    const me = e.currentTarget; me.disabled = true; me.textContent = "Salvo…";
    try {
      const r = await api.runBackup(); S.backup = { ok: r.ok, at: new Date().toISOString(), detail: r.detail };
      toast(r.ok ? "Backup completato" : r.detail, !r.ok); haptic(r.ok ? "medium" : "heavy");
    } catch (er) { toast(errText(er), true); }
    rerenderMore();
  } }, icon("down", 16), "Esegui ora");
  return el("div", { class: "m-card" },
    row("Backup su Hugging Face", !b || !b.at ? "—" : b.ok ? `ok · ${when}` : `non riuscito · ${when}`, !b || !b.at ? undefined : b.ok),
    b && b.at && b.detail ? el("p", { class: `m-note ${b.ok ? "" : "bad"}` }, b.detail) : null,
    el("div", { class: "m-row" }, el("span", {}, "Cifrato · ogni notte"), btn));
}

function buildMore() {
  const st = S.status;
  const url = el("input", { type: "text", value: cfg.url, spellcheck: "false", autocapitalize: "off", "aria-label": "Indirizzo del server" });
  const token = el("input", { type: "password", value: cfg.token, autocomplete: "off", "aria-label": "Token personale" });
  const out = el("p", { class: "m-note" });
  const test = async () => {
    const saved = { ...cfg }; cfg.url = url.value.trim().replace(/\/+$/, ""); cfg.token = token.value.trim();
    out.textContent = "Provo…"; out.className = "m-note";
    try { const s = await api.status(); out.textContent = `Collegato (v${s.version})`; out.className = "m-note ok"; }
    catch (e) { out.textContent = errText(e); out.className = "m-note bad"; Object.assign(cfg, saved); }
  };
  const save = () => {
    cfg.url = url.value.trim().replace(/\/+$/, ""); cfg.token = token.value.trim();
    store.set("jarvis.url", cfg.url); saveToken(cfg.token);
    toast("Salvato"); start();
  };
  const pref = store.get("jarvis.theme", "auto");
  const seg = el("div", { class: "m-seg", role: "group", "aria-label": "Tema" }, [["auto", "Auto"], ["dark", "Scuro"], ["light", "Chiaro"]].map(([v, l]) =>
    el("button", { class: pref === v ? "on" : "", onclick: (e) => { store.set("jarvis.theme", v); applyTheme(); seg.querySelectorAll("button").forEach((b) => b.classList.toggle("on", b === e.currentTarget)); haptic(); } }, l)));
  const speakSwitch = el("input", { type: "checkbox", class: "m-switch", "aria-label": "Voce di JARVIS", checked: voiceOn(),
    onchange: (e) => { store.set("jarvis.speak", e.target.checked ? "1" : "0"); if (!e.target.checked) speaker.stop(); haptic(); } });
  return el("div", { class: "m-page" },
    el("div", { class: "m-head" }, el("h2", {}, "Altro")),
    el("h3", { class: "m-sub" }, "Collegamento"),
    el("div", { class: "m-card form" }, el("label", {}, "Indirizzo del server", url), el("label", {}, "Token personale", token),
      el("div", { class: "m-btns" }, el("button", { class: "m-ghost", onclick: test }, "Prova"), el("button", { class: "m-primary", onclick: save }, "Salva")), out),
    el("h3", { class: "m-sub" }, "Sicurezza"),
    securityCard(),
    el("h3", { class: "m-sub" }, "Aspetto"),
    el("div", { class: "m-card" }, seg),
    el("h3", { class: "m-sub" }, "Aggiornamenti"),
    el("div", { class: "m-card" },
      row("Versione app", S.appVer || (platform === "android" ? "—" : "solo Android")),
      S.update?.available ? el("div", { class: "m-row" }, el("span", {}, `Disponibile ${S.update.latest}`), el("button", { class: "m-primary", onclick: openUpdate }, "Aggiorna"))
        : el("div", { class: "m-row" }, el("span", {}, S.update ? "Sei aggiornato" : "Controlla le novità"), el("button", { class: "m-ghost", onclick: () => checkUpdate(true) }, icon("refresh", 16), "Controlla"))),
    el("h3", { class: "m-sub" }, "Intelligenza"),
    el("div", { class: "m-card" }, el("div", { class: "m-row" }, el("span", {}, "Modello"), el("button", { class: "m-ghost", onclick: openModelPicker }, store.get("jarvis.model") || "Automatico")),
      el("div", { class: "m-row" }, el("span", {}, "Competenze (codice, finanza, marketing…)"), el("button", { class: "m-ghost", onclick: openSkills }, icon("sparkle", 16), "Sfoglia"))),
    el("h3", { class: "m-sub" }, "Voce e notifiche"),
    el("div", { class: "m-card" },
      el("label", { class: "m-row" }, el("span", {}, st?.voice ? "Leggi le risposte (voce di JARVIS)" : "Leggi le risposte (serve il PC acceso)"), speakSwitch),
      el("div", { class: "m-row" }, el("span", {}, "Prova la voce"), el("button", { class: "m-ghost", onclick: () => speaker.speak("Buongiorno, signore. Tutti i sistemi sono operativi.") }, icon("volume", 16), "Ascolta")),
      el("div", { class: "m-row" }, el("span", {}, "Canali e ore silenziose"), el("button", { class: "m-ghost", onclick: openNotifySettings }, icon("sliders", 16), "Imposta")),
      el("div", { class: "m-row" }, el("span", {}, "Notifica di prova"), el("button", { class: "m-ghost", onclick: async () => { try { await api.testNotification(); toast("Inviata"); } catch (e) { toast(errText(e), true); } } }, icon("bell", 16), "Invia"))),
    phoneAvailable ? [el("h3", { class: "m-sub" }, "Telefono"), phoneCard()] : null,
    el("h3", { class: "m-sub" }, "Salvataggi"),
    backupCard(),
    el("h3", { class: "m-sub" }, "Stato"),
    el("div", { class: "m-card" },
      row("Server", S.online ? "online" : "non raggiungibile", S.online),
      row("Intelligenza", st ? (st.freellm.ready ? "pronta" : "non pronta") : "—", st ? st.freellm.ready : undefined),
      row("PC Windows", st ? (st.pc_connected ? "collegato" : "scollegato") : "—", st ? st.pc_connected : undefined),
      row("Telegram", st ? (st.telegram ? "attivo" : "spento") : "—", st ? st.telegram : undefined),
      row("Google", st ? (st.google ? "collegato" : "non collegato") : "—", st ? st.google : undefined),
      row("Memoria", st ? (st.memory === "supabase" ? "permanente" : "temporanea") : "—", st ? st.memory === "supabase" : undefined),
      st ? row("Attivo da", fmtUptime(st.uptime_s)) : null),
    el("div", { class: "m-card safe" }, icon("shield", 20), el("p", {}, "Le azioni sensibili, come inviare un'email o eliminare un evento, richiedono sempre la tua conferma.")),
    el("button", { class: "m-danger", onclick: () => { teardownPush(api).catch(() => {}); saveToken(""); cfg.token = ""; stop(); renderTab(); toast("Token rimosso da questo telefono"); } }, "Rimuovi il token da questo telefono"),
    el("p", { class: "m-about" }, st ? `JARVIS · server v${st.version}` : "JARVIS"));
}

// ---------------------------------------------------------------- notifiche
const KIND = { call: "phone", reminder: "clock", alert: "shield", pending: "shield", update: "down", brain: "sparkle", proactive: "sparkle", info: "bell" };
const ROUTE_TAB = { chat: "chat", brain: "brain", tokens: "tokens", reminders: "reminders", more: "more" };
let notesSheet = null;

async function loadNotes() {
  if (!cfg.token) return;
  try { S.notes = await api.notifications(40); } catch { return; }
  renderTop();
  offerPendingCall();
  if (notesSheet) fillNotes();
}

const HAPTIC = { alert: "heavy", pending: "heavy", reminder: "medium" };
let headsTimer = 0;

/** Avviso in cima allo schermo mentre l'app è aperta: scende con la molla, si tocca per aprire la sezione, si scaccia con un gesto verso l'alto. */
function headsUp(n) {
  document.getElementById("m-heads")?.remove(); clearTimeout(headsTimer);
  const go = () => { box.remove(); const tab = ROUTE_TAB[n.meta?.route]; if (n.kind === "update") openUpdate(); else if (tab) setTab(tab); else openNotes(); };
  const act = (m) => async (e) => {
    e.stopPropagation();
    try { await api.snooze(n.id, m); n.read = true; box.classList.add("gone"); setTimeout(() => box.remove(), 250); haptic(); toast(m ? `Te lo ricordo tra ${m >= 60 ? `${m / 60} h` : `${m} min`}` : "Fatto"); renderTop(); } catch (er) { toast(errText(er), true); }
  };
  const box = el("div", { id: "m-heads", class: `heads k-${n.kind}`, role: "alert", onclick: go },
    el("span", { class: "m-note-ic" }, icon(KIND[n.kind] || "bell", 20)),
    el("div", {}, el("b", {}, n.title), n.body ? el("p", {}, n.body) : null,
      n.kind === "reminder" ? el("div", { class: "heads-act" }, el("button", { onclick: act(10) }, "+10 min"), el("button", { onclick: act(60) }, "+1 ora"), el("button", { class: "ok", onclick: act(0) }, "Fatto")) : null),
    el("small", {}, "adesso"));
  let y0 = null, dy = 0;
  box.addEventListener("touchstart", (e) => { y0 = e.touches[0].clientY; dy = 0; }, { passive: true });
  box.addEventListener("touchmove", (e) => { if (y0 == null) return; dy = Math.min(0, e.touches[0].clientY - y0); box.style.transform = `translateY(${dy}px)`; box.style.opacity = String(1 + dy / 120); }, { passive: true });
  box.addEventListener("touchend", () => { if (dy < -40) { box.classList.add("gone"); setTimeout(() => box.remove(), 250); } else { box.style.transform = ""; box.style.opacity = ""; } y0 = null; });
  document.body.append(box);
  requestAnimationFrame(() => box.classList.add("in"));
  headsTimer = setTimeout(() => { box.classList.add("gone"); setTimeout(() => box.remove(), 300); }, n.kind === "alert" || n.kind === "pending" ? 9000 : n.kind === "reminder" ? 12000 : 5500);
}

// ---------------------------------------------------------------- chiamate
const callDone = () => store.get("jarvis.call.done");
/** Esegue un ordine di chiamata approvato dall'utente (chiesto a JARVIS in chat o su Telegram). I contatti si cercano sul telefono. */
async function runCall(meta, id) {
  if (!phoneAvailable) return toast("Le chiamate funzionano solo nell'app Android", true);
  if (id) store.set("jarvis.call.done", String(id));
  const who = String(meta.contact || "").trim();
  if (!who) return;
  const direct = NUMBER_RE.test(who);
  try {
    let number = direct ? who : "", name = direct ? "" : who;
    if (!direct) {
      let found = [];
      try { found = await phone.findContacts(who); } catch { /* senza permesso Contatti si apre la scelta a mano */ }
      const numbers = found.flatMap((c) => c.numbers.map((n) => ({ name: c.name, number: n })));
      if (numbers.length === 1) { number = numbers[0].number; name = numbers[0].name; }
      else if (meta.via === "whatsapp" && !numbers.length) { /* WhatsApp può cercare per nome tra i suoi contatti */ }
      else return openCallSheet(who, meta);
    }
    if (meta.via === "whatsapp") {
      const r = await phone.whatsapp({ number, name, video: !!meta.video });
      toast(r.method === "chat" ? "Chat WhatsApp aperta: tocca l'icona del telefono" : `Chiamo ${name || number} su WhatsApp…`);
    } else { await phone.dial(number); toast(`Chiamo ${name || number}…`); }
    haptic("medium");
  } catch (e) { toast(e?.message || "Chiamata non riuscita", true); }
}
/** L'ordine è arrivato mentre l'app era chiusa: lo si mostra e si parte solo con un tocco (Android non permette di chiamare da sfondo). */
function offerPendingCall() {
  const n = S.notes.find((x) => x.kind === "call" && !x.read && String(x.id) !== callDone() && Date.now() - new Date(x.created_at) < 120_000);
  if (!n || S.sheets.length) return;
  store.set("jarvis.call.done", String(n.id));
  const m = n.meta || {};
  const s = openSheet("Chiamata richiesta", el("div", { class: "ask" }, icon("phone", 30)), el("p", { class: "ask-t" }, n.body || `Chiamare ${m.contact}`),
    el("div", { class: "m-btns" }, el("button", { class: "m-ghost", onclick: () => s.close() }, "Annulla"), el("button", { class: "m-primary", onclick: () => { s.close(); runCall(m, n.id); } }, "Chiama")));
}

function onNote(n) {
  if (n.kind === "call" && document.visibilityState === "visible" && String(n.id) !== callDone()) { S.notes.unshift(n); renderTop(); runCall(n.meta || {}, n.id); return; }
  if (S.notes.some((x) => x.id === n.id)) return;
  if (n.kind === "update") checkUpdate();
  S.notes.unshift(n);
  renderTop();
  haptic(HAPTIC[n.kind] || "light");
  const bell = top?.querySelector(".m-bell");
  if (bell) { bell.classList.remove("ring"); void bell.offsetWidth; bell.classList.add("ring"); }
  if (notesSheet) fillNotes(); else headsUp(n);
}

const NOTE_FILTERS = [["all", "Tutte"], ["unread", "Non lette"], ["reminder", "Promemoria"], ["alert", "Avvisi"], ["proactive", "Suggerimenti"], ["update", "Aggiornamenti"]];
const dayLabel = (iso) => {
  const d = new Date(iso), now = new Date();
  return d.toDateString() === now.toDateString() ? "Oggi" : d.toDateString() === new Date(Date.now() - 864e5).toDateString() ? "Ieri" : d.toLocaleDateString("it-IT", { weekday: "long", day: "numeric", month: "long" });
};

function fillNotes() {
  const body = notesSheet.sheet.querySelector(".notes-list");
  const f = S.noteFilter || "all";
  notesSheet.sheet.querySelectorAll(".note-chips button").forEach((b) => b.classList.toggle("on", b.dataset.f === f));
  const rows = S.notes.filter((n) => f === "all" || (f === "unread" ? !n.read : f === "alert" ? ["alert", "pending"].includes(n.kind) : f === "proactive" ? ["proactive", "brain", "info"].includes(n.kind) : n.kind === f));
  if (!rows.length) return body.replaceChildren(el("div", { class: "m-empty" }, el("div", { class: "ico" }, icon("bell", 30)), f === "all" ? "Nessuna notifica." : "Nessuna notifica in questa categoria."));
  const out = []; let day = "";
  rows.forEach((n, i) => {
    const d = dayLabel(n.created_at);
    if (d !== day) { day = d; out.push(el("h3", { class: "m-sub note-day" }, d)); }
    const tab = ROUTE_TAB[n.meta?.route];
    out.push(el("div", { class: `m-note-row k-${n.kind}${n.read ? "" : " unread"}`, style: `--i:${Math.min(i, 12)}`,
      onclick: (e) => { if (e.target.closest("button")) return; if (n.kind === "update") { notesSheet?.close(); openUpdate(); } else if (tab) { notesSheet?.close(); setTab(tab); } } },
      el("span", { class: "m-note-ic" }, icon(KIND[n.kind] || "bell", 18)),
      el("div", {}, el("div", { class: "nt" }, el("b", {}, n.title), el("small", {}, clock(new Date(n.created_at)))), n.body ? el("p", {}, n.body) : null, noteActions(n))));
  });
  body.replaceChildren(...out);
}

function noteActions(n) {
  if (n.kind === "reminder" && !n.read) {
    const go = (m) => async () => { try { await api.snooze(n.id, m); n.read = true; toast(m ? `Te lo ricordo tra ${m >= 60 ? `${m / 60} h` : `${m} min`}` : "Fatto"); renderTop(); fillNotes(); } catch (e) { toast(errText(e), true); } };
    return el("div", { class: "m-presets note-act" }, el("button", { onclick: go(10) }, "+10 min"), el("button", { onclick: go(60) }, "+1 ora"), el("button", { onclick: go(0) }, "Fatto"));
  }
  if (n.kind === "update") return el("div", { class: "m-presets note-act" }, el("button", { onclick: () => { notesSheet?.close(); openUpdate(); } }, "Aggiorna"));
  return null;
}

function openNotes() {
  if (notesSheet) return;
  const list = el("div", { class: "notes-list" });
  const chipsRow = el("div", { class: "note-chips m-chips" }, NOTE_FILTERS.map(([v, l]) => el("button", { "data-f": v, onclick: () => { S.noteFilter = v; haptic(); fillNotes(); } }, l)));
  const s = openSheet("Notifiche", chipsRow, list, el("div", { class: "m-btns" },
    el("button", { class: "m-ghost", onclick: async () => { try { await api.testNotification(); } catch (e) { toast(errText(e), true); } } }, "Prova"),
    el("button", { class: "m-primary", onclick: async () => { try { await api.markRead(null); S.notes.forEach((n) => (n.read = true)); renderTop(); fillNotes(); } catch (e) { toast(errText(e), true); } } }, "Segna lette")));
  const close = s.close;
  notesSheet = { ...s, close: () => { close(); notesSheet = null; } };
  s.sheet.addEventListener("click", (e) => { if (e.target === s.sheet) notesSheet = null; });
  S.sheets[S.sheets.length - 1].close = notesSheet.close;
  fillNotes();
  if (unread()) { api.markRead(null).then(() => setTimeout(() => { S.notes.forEach((n) => (n.read = true)); renderTop(); }, 1500)).catch(() => {}); }
}

// ---------------------------------------------------------------- conferme
let askSheet = null;
function renderPending() {
  const p = S.pending[0];
  if (!p) { askSheet?.close(); askSheet = null; return; }
  if (askSheet?.id === p.id) return;
  askSheet?.close();
  haptic("heavy");
  const decide = async (ok) => { try { const r = await api.decide(p.id, ok); toast(ok ? r.result || "Approvata" : "Rifiutata"); } catch (e) { toast(errText(e), true); } pollPending(); };
  const s = openSheet("Conferma richiesta", el("div", { class: "ask" }, icon("shield", 30)), el("p", { class: "ask-t" }, p.summary),
    el("small", { class: "m-note" }, `Scade tra ${Math.max(1, Math.round(p.expires_in / 60))} min · JARVIS non può farlo senza di te`),
    el("div", { class: "m-btns" }, el("button", { class: "m-ghost", onclick: () => decide(false) }, "Rifiuta"), el("button", { class: "m-primary", onclick: () => decide(true) }, "Approva")));
  askSheet = { ...s, id: p.id };
}

// ---------------------------------------------------------------- cicli
async function refreshStatus() {
  if (!cfg.token) return;
  try { S.status = await api.status(); S.online = true; } catch (e) { S.online = false; if (e.status === 401) toast(errText(e), true); }
  S.checked = true;
  renderTop();
  if (S.tab === "more") renderTab();
}
async function pollPending() { if (!cfg.token) return; try { S.pending = await api.pending(); } catch { return; } renderPending(); }
function start() {
  stop();
  if (!cfg.token) return;
  refreshStatus(); pollPending(); loadHistory(); loadNotes(); loadReminders();
  closeStream = openStream({ url: () => cfg.url, token: () => cfg.token }, {
    onNotification: onNote,
    onRead: (ids) => { S.notes.forEach((n) => { if (!ids || ids.includes(n.id)) n.read = true; }); renderTop(); if (notesSheet) fillNotes(); },
    onSync: ({ scope, origin }) => {  // un altro dispositivo (o il server) ha cambiato qualcosa: ci si aggiorna subito
      if (scope === "reminders") loadReminders();
      else if (scope === "brain") { S.brain.docs = null; S.brain.stats = null; if (S.tab === "brain") loadBrain(); }
      else if (scope === "chat" && origin !== deviceId) syncHistory();
    },
    onState: (st) => {
      const was = S.live; S.live = st; renderTop();
      if (st === "on") { if (was !== "on") { S.online = true; S.checked = true; renderTop(); loadNotes(); loadReminders(); syncHistory(); } }
      else if (st === "auth") toast("Token non valido: controllalo in Altro.", true);
    },
  });
  initPush(api, (route) => { if (ROUTE_TAB[route]) setTab(ROUTE_TAB[route]); }).catch(() => {});
  checkUpdate();
  timers = [setInterval(refreshStatus, 30_000), setInterval(pollPending, 5_000), setInterval(checkUpdate, 6 * 3600_000)];
}
function stop() { closeStream?.(); closeStream = null; timers.forEach(clearInterval); timers = []; S.status = null; S.checked = false; S.online = false; S.pending = []; renderTop(); renderPending(); }

// risparmia batteria e dati: nulla gira con l'app in secondo piano; con il blocco attivo, dopo il tempo scelto serve il PIN
let hiddenAt = 0;
async function lockIfNeeded(force = false) {
  const rec = store.get("jarvis.pin");
  if (!rec || S.locked) return;
  if (!force && Date.now() - hiddenAt < autolock() * 1000) return;
  S.locked = true; stop();
  await showLock({ store, record: rec, orb });
  S.locked = false;
}
document.addEventListener("visibilitychange", async () => {
  if (document.hidden) {
    hiddenAt = Date.now();
    document.body.classList.toggle("privacy", privacyOn());  // copre il contenuto nella schermata delle app recenti
    speaker.stop(); closeStream?.(); closeStream = null; timers.forEach(clearInterval); timers = [];
  } else {
    document.body.classList.remove("privacy");
    await lockIfNeeded();
    if (!S.locked) start();
  }
});

// tasto Indietro: chiude i fogli, poi torna alla chat, poi mette l'app in secondo piano
onBack(() => {
  if (S.locked) return true;
  const sheet = S.sheets[S.sheets.length - 1];
  if (sheet) { sheet.close(); return true; }
  if (S.tab !== "chat") { setTab("chat"); return true; }
  return false;
});

applyTheme();
shell();
renderTabs(); renderTab();
(async () => {
  await loadToken();
  if (!cfg.token) S.tab = "more";
  renderTabs(); renderTab();
  await lockIfNeeded(true);  // all'apertura, con il PIN attivo, si parte bloccati
  if (cfg.token) start();
  dictationAvailable().then((ok) => { S.canMic = ok; if (micBtn) micBtn.style.display = ok ? "" : "none"; });
})();
setTimeout(hideSplash, 350);
