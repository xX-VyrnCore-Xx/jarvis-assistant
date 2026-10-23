import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { getVersion } from "@tauri-apps/api/app";
import { Jarvis, ApiError, deviceId } from "@shared/api.js";
import { el, fmtDate, fmtTokens, fmtUptime, markdown, nowLocalInput, pct } from "@shared/format.js";
import { icon } from "@shared/icons.js";
import { Speaker } from "@shared/speech.js";
import { createCodeStudio } from "@shared/codeview.js";
import { dictationSupported, recordUtterance } from "@shared/dictate.js";
import { openStream } from "@shared/stream.js";
import { initVoice, installVoice, onVoiceChange, removeVoice, synth, toBase64, voice } from "./voice.js";
import { clearToken, loadToken, saveToken } from "./secrets.js";
import { runWizard } from "./wizard.js";

// URL pubblico del server (non è un segreto); il token personale sta nel Gestore credenziali
const DEFAULT_URL = "https://jarvis-ai-841t.onrender.com";
const SESSION = "desktop";
const isTauri = "__TAURI_INTERNALS__" in window;
const SENSITIVE = {
  pc_move: (a) => `Spostare/rinominare "${a.src}" in "${a.dst}"?`,
  pc_power: (a) => `Eseguire "${a.mode}" del PC (tra 30 secondi)?`,
};
const CHIPS = [
  ["Token disponibili", "Quanti token mi restano questo mese?"],
  ["Che ore sono", "Che ore sono?"],
  ["Agenda", "Cosa ho in agenda nei prossimi giorni?"],
  ["Email non lette", "Ho email non lette importanti?"],
];
const VIEWS = [
  ["chat", "Conversazione", "chat"],
  ["code", "Codice", "code"],
  ["tokens", "Token", "gauge"],
  ["brain", "Cervello", "sparkle"],
  ["notifications", "Notifiche", "bell"],
  ["reminders", "Promemoria", "clock"],
  ["pc", "Controllo PC", "monitor"],
  ["settings", "Impostazioni", "sliders"],
];

const cfg = { url: (localStorage.getItem("jarvis.url") || DEFAULT_URL).replace(/\/+$/, ""), token: "", where: "local" };
const api = new Jarvis({ url: () => cfg.url, token: () => cfg.token });
const speaker = new Speaker({ tts: (t) => synth(t) });
const voiceOn = () => localStorage.getItem("jarvis.speak") !== "0";
const S = { update: null, view: "chat", status: null, tokens: null, tokensErr: "", pending: [], reminders: [], tasks: [], notes: [], brain: { q: "", results: null, docs: null, stats: null, doc: null }, live: "off", online: false, ws: false, pcLog: [], busy: false };

const $app = document.getElementById("app");
let rail, viewBox, side, chatLog, chatInput, chatView;
let ws, wsRetry = 0, wsPing, closeStream;

// ------------------------------------------------------------------ utilità
function toast(text, bad = false) {
  const t = document.getElementById("toast");
  t.textContent = text;
  t.className = `show${bad ? " bad" : ""}`;
  clearTimeout(toast.t);
  toast.t = setTimeout(() => (t.className = ""), 4200);
}
const errText = (e) => (e instanceof ApiError ? e.message : String(e));
const local = (action, args = {}) => invoke("run_action", { action, args });

function logPc(text, ok = true) {
  S.pcLog.unshift({ at: new Date(), text, ok });
  S.pcLog.length = Math.min(S.pcLog.length, 30);
  if (S.view === "pc") renderView();
}

// ------------------------------------------------------------------ struttura
function shell() {
  rail = el("nav", { id: "rail", "aria-label": "Sezioni" });
  viewBox = el("section", { id: "view" });
  side = el("aside", { id: "side" });
  $app.replaceChildren(rail, el("main", { id: "main" }, viewBox), side);
  renderRail();
  renderSide();
}

function renderRail() {
  rail.replaceChildren(
    el("div", { class: "brand", title: "JARVIS" }, el("span", { class: "core" })),
    ...VIEWS.map(([id, label, ic]) => {
      const badge = id === "notifications" ? S.notes.filter((n) => !n.read).length : 0;
      return el("button", { class: `rail-btn${S.view === id ? " on" : ""}`, title: label, "aria-label": label, onclick: () => setView(id) }, icon(ic, 22), badge ? el("i", { class: "badge" }, badge > 9 ? "9+" : String(badge)) : null);
    }),
  );
}

function setView(v) {
  S.view = v;
  renderRail();
  renderView();
  if (v === "tokens") loadTokens();
  if (v === "reminders") { loadReminders(); loadTasks(); }
  if (v === "notifications") loadNotes();
  if (v === "brain") loadBrain();
  if (v === "code") codeStudio().refresh();
}

function renderView() {
  viewBox.className = `view-${S.view}`;
  if (S.view === "chat") return viewBox.replaceChildren(buildChat());
  if (S.view === "code") return viewBox.replaceChildren(buildCode());
  if (S.view === "tokens") return viewBox.replaceChildren(buildTokens());
  if (S.view === "reminders") return viewBox.replaceChildren(buildReminders());
  if (S.view === "notifications") return viewBox.replaceChildren(buildNotes());
  if (S.view === "brain") return viewBox.replaceChildren(buildBrain());
  if (S.view === "pc") return viewBox.replaceChildren(buildPc());
  return viewBox.replaceChildren(buildSettings());
}

const panelHead = (title, sub, ...actions) =>
  el("header", { class: "panel-head" }, el("div", {}, el("h1", {}, title), sub ? el("p", {}, sub) : null), el("div", { class: "actions" }, ...actions));

// ------------------------------------------------------------------ pannello laterale
function gauge(p, big, small) {
  const R = 54, C = 2 * Math.PI * R;
  const svgNS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(svgNS, "svg");
  svg.setAttribute("viewBox", "0 0 140 140");
  const mk = (cls, attrs) => { const c = document.createElementNS(svgNS, "circle"); c.setAttribute("class", cls); for (const [k, v] of Object.entries(attrs)) c.setAttribute(k, v); return c; };
  svg.append(mk("g-spin", { cx: 70, cy: 70, r: 66 }), mk("g-track", { cx: 70, cy: 70, r: R }), mk("g-bar", { cx: 70, cy: 70, r: R, "stroke-dasharray": `${(C * p) / 100} ${C}`, transform: "rotate(-90 70 70)" }));
  return el("div", { class: "gauge" }, svg, el("div", { class: "g-text" }, el("strong", {}, big), el("span", {}, small)));
}

function stat(label, value, ok) {
  return el("div", { class: "stat" }, el("span", {}, label), el("b", { class: ok === undefined ? "" : ok ? "ok" : "off" }, value));
}

function renderSide() {
  const st = S.status;
  const t = st?.tokens;
  const left = t ? pct(t.remaining_tokens, t.documented_monthly_tokens) : 0;
  side.replaceChildren(...[
    el("div", { class: "side-card reactor" },
      gauge(left, t ? fmtTokens(t.remaining_tokens) : "—", "token disponibili"),
      el("p", { class: "tiny" }, t ? `su ${fmtTokens(t.documented_monthly_tokens)} · usati ${fmtTokens(t.used_tokens)}` : "in attesa dei dati"),
    ),
    el("div", { class: "side-card" },
      el("h3", {}, "Sistema"),
      stat("Server", S.online ? "online" : "non raggiungibile", S.online),
      stat("Intelligenza", st ? (st.freellm.ready ? "pronta" : "non pronta") : "—", st ? st.freellm.ready : undefined),
      stat("Questo PC", S.ws ? "collegato" : "scollegato", S.ws),
      stat("Telegram", st ? (st.telegram ? "attivo" : "spento") : "—", st ? st.telegram : undefined),
      stat("Google", st ? (st.google ? "collegato" : "non collegato") : "—", st ? st.google : undefined),
      stat("Memoria", st ? (st.memory === "supabase" ? "permanente" : "temporanea") : "—", st ? st.memory === "supabase" : undefined),
      st ? stat("Attivo da", fmtUptime(st.uptime_s)) : null,
    ),
    S.update?.available ? updateCard() : null,
    el("div", { class: "side-card hint" }, icon("shield", 16), el("span", {}, "Le azioni sensibili chiedono sempre la tua conferma.")),
  ].filter(Boolean));
}

// ------------------------------------------------------------------ chat
function addMessage(role, text) {
  const body = role === "bot" ? markdown(text) : el("p", {}, text);
  const play = role === "bot" ? el("button", { class: "speak-btn", title: "Ascolta", "aria-label": "Ascolta", onclick: () => (speaker.speaking ? speaker.stop() : speaker.speak(text)) }, icon("volume", 15)) : null;
  const node = el("div", { class: `msg ${role}` }, el("div", { class: "who" }, role === "bot" ? "J.A.R.V.I.S." : role === "user" ? "Tu" : "", play), el("div", { class: "bubble" }, body));
  chatLog.append(node);
  chatLog.scrollTop = chatLog.scrollHeight;
  return node;
}

function buildChat() {
  if (chatView) return chatView;
  chatLog = el("div", { id: "chat-log", "aria-live": "polite" });
  chatInput = el("textarea", { id: "chat-input", rows: 1, placeholder: "Scrivi a JARVIS…  (Invio per inviare, Maiusc+Invio per andare a capo)", "aria-label": "Messaggio" });
  chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  });
  chatInput.addEventListener("input", () => { chatInput.style.height = "auto"; chatInput.style.height = `${Math.min(chatInput.scrollHeight, 140)}px`; });
  chatView = el("div", { class: "chat" },
    panelHead("Conversazione", "Parla con JARVIS: usa gli stessi poteri di Telegram e della voce.",
      el("button", { class: "btn", title: "Cancella la conversazione e riparti da zero", onclick: newChat }, icon("plus", 16), "Nuova chat")),
    chatLog,
    el("div", { class: "chips" }, CHIPS.map(([label, text]) => el("button", { class: "chip", onclick: () => send(text) }, label))),
    el("div", { class: "composer" },
      micBtn = el("button", { class: "send mic", title: "Detta (si ferma da solo quando smetti di parlare)", "aria-label": "Detta", onclick: dictate }, icon("mic", 20)),
      chatInput,
      fixBtn = el("button", { class: "send fix", title: "Correggi la grammatica", "aria-label": "Correggi la grammatica", onclick: fixText }, icon("sparkle", 20)),
      el("button", { class: "send", title: "Invia", "aria-label": "Invia", onclick: () => send() }, icon("send", 20))),
  );
  addMessage("sys", cfg.token ? "Pronto, signore." : "Inserisci il token personale in Impostazioni per iniziare.");
  return chatView;
}

let newChatArmed = 0;
async function newChat(e) {
  if (S.busy) return toast("Aspetta che JARVIS finisca di rispondere");
  const btn = e?.currentTarget;
  if (Date.now() - newChatArmed > 4000) {  // conferma a due tocchi (le finestre di dialogo del browser non sono affidabili nell'app)
    newChatArmed = Date.now();
    if (btn) btn.lastChild.textContent = "Conferma: cancella tutto";
    toast("Tocca di nuovo per cancellare la conversazione (anche su Telegram e sul telefono). Ricordi e promemoria restano.");
    setTimeout(() => { if (btn?.lastChild) btn.lastChild.textContent = "Nuova chat"; }, 4000);
    return;
  }
  newChatArmed = 0;
  if (btn) btn.lastChild.textContent = "Nuova chat";
  try { await api.newChat(); S.histSig = null; chatLog.replaceChildren(); addMessage("sys", "Nuova conversazione. Pronto, signore."); }
  catch (e) { toast(errText(e), true); }
}

let micBtn, fixBtn, recAbort = null;
const recStop = {};

/** Dettatura di qualità: registra, capisce da sola quando finisci e trascrive con Whisper sul server (con accenti e punteggiatura a posto). Un secondo clic chiude la frase. */
async function dictate() {
  if (!cfg.token) return setView("settings");
  if (recAbort) return recStop.stop?.();
  if (!dictationSupported()) return toast("Il microfono non è disponibile in questa finestra", true);
  recAbort = new AbortController(); micBtn.classList.add("on");
  try {
    const res = await recordUtterance({ signal: recAbort.signal, stopRef: recStop, onLevel: (v) => micBtn.style.setProperty("--lvl", v.toFixed(2)) });
    if (!res.blob) return toast("Non ho sentito nulla");
    chatInput.placeholder = "Trascrivo…";
    const r = await api.stt(res.blob, "quick");
    if (r.text) { chatInput.value = (chatInput.value ? `${chatInput.value} ` : "") + r.text; chatInput.dispatchEvent(new Event("input")); chatInput.focus(); }
    else toast("Non ho capito: riprova parlando più vicino al microfono");
  } catch (e) { toast(e?.status ? errText(e) : "Microfono non disponibile o permesso negato", true); }
  finally { recAbort = null; micBtn.classList.remove("on"); micBtn.style.removeProperty("--lvl"); chatInput.placeholder = "Scrivi a JARVIS…  (Invio per inviare, Maiusc+Invio per andare a capo)"; }
}

/** Correttore grammaticale (ortografia, accenti, concordanze, punteggiatura) senza cambiare il senso. */
async function fixText() {
  const orig = chatInput.value.trim();
  if (orig.length < 3) return;
  fixBtn.disabled = true;
  try {
    const r = await api.correct(orig, "full");
    if (r.text && r.text !== orig) { chatInput.value = r.text; chatInput.dispatchEvent(new Event("input")); toast("Testo corretto (Ctrl+Z per annullare)"); }
    else toast("Il testo è già corretto");
  } catch (e) { toast(errText(e), true); }
  finally { fixBtn.disabled = false; }
}

async function send(text) {
  const msg = (text ?? chatInput.value).trim();
  if (!msg || S.busy) return;
  if (!cfg.token) return setView("settings");
  if (text === undefined) { chatInput.value = ""; chatInput.style.height = "auto"; }
  addMessage("user", msg);
  S.busy = true;
  const wait = addMessage("sys", "JARVIS sta pensando…");
  wait.classList.add("thinking");
  let live = null, acc = "";
  try {
    const reply = await api.chatStream(msg, SESSION, {
      onStatus: (t) => { wait.textContent = t; },
      onDelta: (t) => {
        if (!live) { wait.remove(); live = addMessage("bot", ""); }
        acc += t;
        live.querySelector(".bubble").replaceChildren(markdown(acc));
        chatLog.scrollTop = chatLog.scrollHeight;
      },
    });
    live?.remove();
    addMessage("bot", reply);
    if (voiceOn() && voice.installed) speaker.speak(reply);
    refreshStatus();
  } catch (e) {
    addMessage("sys", errText(e));
  } finally {
    wait.remove();
    S.busy = false;
  }
}

async function loadHistory(quiet = false) {
  if (quiet && S.busy) return;
  try {
    const rows = await api.history(SESSION, 30);
    const sig = `${rows.length}|${rows.at(-1)?.content?.length ?? 0}|${rows.at(-1)?.role ?? ""}`;
    if (quiet && sig === S.histSig) return;
    S.histSig = sig;
    buildChat();
    chatLog.replaceChildren();
    if (rows.length) addMessage("sys", "Conversazione precedente");
    rows.forEach((r) => addMessage(r.role === "user" ? "user" : "bot", r.content));
    addMessage("sys", "Pronto, signore.");
  } catch { /* offline: resta il messaggio iniziale */ }
}

// ------------------------------------------------------------------ token
async function loadTokens(force = false) {
  if (!cfg.token) return;
  try { S.tokens = await api.tokens(force); S.tokensErr = ""; } catch (e) { S.tokensErr = errText(e); }
  if (S.view === "tokens") renderView();
}

function buildTokens() {
  const t = S.tokens;
  const head = panelHead("Token disponibili", "Quanto puoi ancora usare questo mese, preso da FreeLLMAPI.",
    el("button", { class: "btn", onclick: () => { loadTokens(true); toast("Aggiorno i dati…"); } }, icon("refresh", 16), "Aggiorna"));
  if (!t) return el("div", { class: "page" }, head, el("div", { class: "empty" }, S.tokensErr || "Carico i dati…"));
  const left = pct(t.remaining_tokens, t.documented_monthly_tokens);
  const max = Math.max(...t.providers.map((p) => p.documented || p.remaining || 0), 1);
  return el("div", { class: "page" }, head,
    el("div", { class: "tok-hero" },
      gauge(left, fmtTokens(t.remaining_tokens), "disponibili (stima)"),
      el("div", { class: "tok-nums" },
        stat("Budget mensile", fmtTokens(t.documented_monthly_tokens)),
        stat("Usati", `${fmtTokens(t.used_tokens)} · ${t.used_requests} richieste`),
        stat("Si azzera", t.resets_at ? fmtDate(t.resets_at) : "a inizio mese"),
        stat("Provider nel totale", `${t.providers_counted}${t.providers_unknown ? ` (+${t.providers_unknown} senza budget)` : ""}`),
      )),
    el("h2", { class: "sub" }, "Per provider"),
    el("div", { class: "prov" }, t.providers.map((p) => {
      const known = p.remaining != null;
      const w = known ? Math.max(2, ((p.remaining || 0) / max) * 100) : 0;
      return el("div", { class: "prov-row" },
        el("div", { class: "prov-name" }, p.platform, el("small", {}, p.source === "live" ? "quota reale" : p.source === "estimate" ? "stima" : "senza budget")),
        el("div", { class: "bar" }, el("i", { style: `width:${w}%` })),
        el("div", { class: "prov-val" }, known ? fmtTokens(p.remaining) : "n/d"));
    })),
    el("p", { class: "tiny note" }, t.note),
  );
}

// ------------------------------------------------------------------ aggiornamenti
// Scarica l'installer dentro l'app (avanzamento, controllo SHA-256), poi lo avvia e chiude JARVIS.
let upd = { phase: "idle", pct: 0, msg: "" };

function updateCard() {
  const u = S.update;
  const news = (u.changes || []).flatMap((c) => c.highlights || []).slice(0, 3);
  const busy = upd.phase === "downloading";
  return el("div", { class: "side-card update" },
    el("div", { style: "display:flex;gap:8px;align-items:center" }, icon("down", 16), el("span", {}, `Nuova versione ${u.latest}${u.size ? ` · ${(u.size / 1048576).toFixed(1)} MB` : ""}`)),
    news.length ? el("ul", { class: "upd-list" }, news.map((n) => el("li", {}, n))) : null,
    busy ? el("div", { class: "upd-bar" }, el("i", { style: `width:${upd.pct}%` })) : null,
    upd.msg ? el("small", {}, upd.msg) : null,
    upd.phase === "ready"
      ? el("button", { class: "btn primary", onclick: installUpdate }, "Installa e riavvia")
      : el("button", { class: "btn primary", disabled: busy, onclick: startUpdate }, busy ? `Scarico… ${upd.pct}%` : "Scarica e aggiorna"));
}

async function startUpdate() {
  if (!isTauri) return;
  if (!/^https:\/\/github\.com\/[\w.-]+\/[\w.-]+\/releases\/download\//.test(S.update.url || "")) return toast("Indirizzo di download non attendibile", true);
  upd = { phase: "downloading", pct: 0, msg: "" }; renderSide();
  try { await invoke("update_download", { url: S.update.url, sha256: S.update.sha256 || "" }); }
  catch (e) { upd = { phase: "error", pct: 0, msg: String(e) }; renderSide(); toast(String(e), true); }
}

async function installUpdate() {
  try { await invoke("update_install"); } catch (e) { upd = { phase: "error", pct: 0, msg: String(e) }; renderSide(); toast(String(e), true); }
}

async function initUpdates() {
  if (!isTauri) return;
  await listen("update-progress", (ev) => { upd.pct = Number(ev.payload) || 0; renderSide(); });
  await listen("update-done", (ev) => {
    const { ok, error } = ev.payload || {};
    upd = ok ? { phase: "ready", pct: 100, msg: "Scaricato e verificato (SHA-256)." } : { phase: "error", pct: 0, msg: error || "Download non riuscito." };
    renderSide();
    if (!ok) toast(upd.msg, true);
  });
}

async function checkUpdate() {
  if (!cfg.token || !isTauri) return;
  try { S.update = await api.appUpdate("windows", await getVersion()); renderSide(); } catch { /* server in avvio: riprova al prossimo ciclo */ }
}

// ------------------------------------------------------------------ notifiche
const KIND = { reminder: "clock", alert: "shield", pending: "shield", update: "down", brain: "sparkle", proactive: "sparkle", info: "bell" };

async function loadNotes() {
  if (!cfg.token) return;
  try { S.notes = await api.notifications(60); } catch (e) { toast(errText(e), true); }
  renderRail();
  if (S.view === "notifications") renderView();
}

function onNote(n) {
  if (S.notes.some((x) => x.id === n.id)) return;
  if (n.kind === "update") checkUpdate();
  S.notes.unshift(n);
  renderRail();
  if (S.view === "notifications") renderView();
  if (document.hasFocus()) toast(n.title);
  else invoke("notify", { title: n.title, body: n.body }).catch(() => {});
}

async function markAllRead() {
  try { await api.markRead(null); S.notes.forEach((n) => (n.read = true)); renderRail(); renderView(); } catch (e) { toast(errText(e), true); }
}

function buildNotes() {
  const live = S.live === "on";
  return el("div", { class: "page" },
    panelHead("Notifiche", live ? "In tempo reale: collegato al server." : "Riconnessione in corso…",
      el("button", { class: "btn", onclick: async () => { try { await api.testNotification(); } catch (e) { toast(errText(e), true); } } }, icon("bell", 16), "Prova"),
      el("button", { class: "btn", onclick: markAllRead }, icon("check", 16), "Segna lette")),
    S.notes.length
      ? el("div", { class: "list" }, S.notes.map((n) => el("div", { class: `item note${n.read ? "" : " unread"}` },
        el("span", { class: "note-ic" }, icon(KIND[n.kind] || "bell", 18)),
        el("div", {}, el("b", {}, n.title), n.body ? el("p", { class: "note-body" }, n.body) : null, el("small", {}, fmtDate(n.created_at))))))
      : el("div", { class: "empty" }, "Nessuna notifica."),
  );
}

// ------------------------------------------------------------------ secondo cervello
const SRC = { note: "nota", memory: "ricordo", journal: "diario", web: "web", file: "file", drive: "drive", gmail: "email", chat: "chat" };
let brainTimer = null;

async function loadBrain() {
  if (!cfg.token) return;
  try { [S.brain.docs, S.brain.stats] = await Promise.all([api.brainDocs(50), api.brainStats()]); } catch (e) { if (e.status !== 404) toast(errText(e), true); S.brain.docs = S.brain.docs || []; }
  if (S.view === "brain") renderView();
}

async function openBrainDoc(id) {
  try { S.brain.doc = await api.brainDoc(id); } catch (e) { return toast(errText(e), true); }
  if (S.view === "brain") renderView();
}

function brainSearch(q) {
  S.brain.q = q;
  clearTimeout(brainTimer);
  if (q.trim().length < 2) { S.brain.results = null; return renderView(); }
  brainTimer = setTimeout(async () => {
    try { S.brain.results = await api.brainSearch(q.trim(), 12); } catch (e) { toast(errText(e), true); S.brain.results = []; }
    if (S.view === "brain") { renderView(); document.getElementById("brain-q")?.focus(); }
  }, 450);
}

function buildBrain() {
  const { results, docs, stats, doc } = S.brain;
  const q = el("input", { id: "brain-q", type: "text", placeholder: "Cerca nei tuoi ricordi (per significato)…", value: S.brain.q, "aria-label": "Cerca" });
  q.addEventListener("input", () => brainSearch(q.value));
  const note = el("textarea", { rows: 3, placeholder: "Nuova nota, oppure incolla un link da salvare…", "aria-label": "Nuova nota", class: "brain-note" });
  const save = async () => {
    const body = note.value.trim();
    if (body.length < 3) return toast("Scrivi qualcosa", true);
    try {
      const r = /^https?:\/\/\S+$/.test(body) ? await api.brainAddUrl(body) : await api.brainAddNote(body);
      toast(r.status === "duplicato" ? "Già presente" : "Salvato nel cervello"); note.value = ""; S.brain.results = null; loadBrain();
    } catch (e) { toast(errText(e), true); }
  };
  const row = (d, text) => el("button", { class: `item brain-item${doc && doc.id === (d.doc_id || d.id) ? " on" : ""}`, onclick: () => openBrainDoc(d.doc_id || d.id) },
    el("div", {}, el("b", {}, d.title || "(senza titolo)"), text || d.summary ? el("p", { class: "note-body" }, text || d.summary) : null,
      el("small", {}, `${SRC[d.source] || d.source} · ${fmtDate(d.created_at)}${d.why?.length ? ` · ${d.why.join(", ")}` : ""}`)));
  const list = results ? (results.length ? results.map((r) => row(r, r.snippet)) : [el("div", { class: "empty" }, "Nessun risultato: prova con altre parole.")])
    : docs == null ? [el("div", { class: "empty" }, "Carico…")] : docs.length ? docs.map((d) => row(d)) : [el("div", { class: "empty" }, "Il secondo cervello è vuoto: aggiungi una nota o scrivi a JARVIS «ricorda che…».")];
  const reader = doc ? el("aside", { class: "brain-doc" },
    el("h2", {}, doc.title || "Documento"), el("small", {}, `${SRC[doc.source] || doc.source} · ${fmtDate(doc.created_at)}${doc.tags.length ? ` · ${doc.tags.join(", ")}` : ""}`),
    doc.summary ? el("p", { class: "note-body" }, doc.summary) : null, el("pre", { class: "brain-text" }, doc.text + (doc.truncated ? "\n[…]" : "")),
    doc.related?.length ? el("div", {}, el("small", {}, "Collegati"), el("div", { class: "row" }, doc.related.map((r) => el("button", { class: "btn", onclick: () => openBrainDoc(r.doc_id) }, r.title)))) : null,
    el("div", { class: "row" },
      el("button", { class: "btn", onclick: async () => { await api.brainPin(doc.id, !doc.pinned); openBrainDoc(doc.id); loadBrain(); } }, doc.pinned ? "Stacca" : "Fissa"),
      el("button", { class: "btn danger", onclick: async () => { await api.brainDelete(doc.id); S.brain.doc = null; S.brain.results = null; toast("Eliminato"); loadBrain(); } }, "Elimina"))) : null;
  return el("div", { class: "page brain" },
    panelHead("Secondo cervello", stats ? `${stats.docs} documenti · ${stats.chunks} frammenti · ${stats.entities} entità · ${stats.model}` : "Note, ricordi, pagine e file: li ritrovi per significato."),
    el("div", { class: "form-row" }, q), el("div", { class: "form-row" }, note, el("button", { class: "btn primary", onclick: save }, icon("plus", 16), "Salva")),
    el("div", { class: "brain-cols" }, el("div", { class: "list" }, list), reader));
}

// ------------------------------------------------------------------ codice
let studioInst = null, codeBox = null;
function codeStudio() { return studioInst ||= createCodeStudio({ api, toast, errText }); }
function buildCode() {
  if (!codeBox) codeBox = el("div", { class: "page code-page" }, panelHead("Codice", "Uno spazio solo per programmare: JARVIS al massimo, con tutte le competenze di programmazione, piano, revisione e CI."), el("div", { class: "code-wrap" }, codeStudio().root));
  return codeBox;
}

// ------------------------------------------------------------------ promemoria
async function loadReminders() {
  if (!cfg.token) return;
  try { S.reminders = await api.reminders(); } catch (e) { toast(errText(e), true); }
  if (S.view === "reminders") renderView();
}

async function loadTasks() {
  if (!cfg.token) return;
  try { S.tasks = await api.tasks(); } catch (e) { toast(errText(e), true); }
  if (S.view === "reminders") renderView();
}

function tasksPanel() {
  const input = el("input", { type: "text", placeholder: "Nuova attività…", maxlength: 300, "aria-label": "Nuova attività" });
  const add = async () => {
    const text = input.value.trim(); if (!text) return;
    input.value = "";
    try { await api.addTask(text); loadTasks(); } catch (e) { toast(errText(e), true); }
  };
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") add(); });
  const act = (fn) => async () => { try { await fn(); } catch (e) { toast(errText(e), true); } loadTasks(); };
  return el("div", {}, panelHead("Attività", "Le stesse di Telegram e dell'app Android, sempre aggiornate."),
    el("div", { class: "form-row" }, input, el("button", { class: "btn primary", onclick: add }, icon("plus", 16), "Aggiungi")),
    S.tasks.length
      ? el("div", { class: "list" }, S.tasks.map((t) => el("div", { class: "item" }, el("div", {}, el("b", {}, t.text), t.list && t.list !== "attività" ? el("small", {}, t.list) : null),
        el("button", { class: "icon-btn", title: "Completa", "aria-label": "Completa", onclick: act(() => api.setTaskDone(t.id, true)) }, icon("check", 18)),
        el("button", { class: "icon-btn", title: "Elimina", "aria-label": "Elimina", onclick: act(() => api.deleteTask(t.id)) }, icon("trash", 18)))))
      : el("div", { class: "empty" }, "Nessuna attività aperta."));
}

function buildReminders() {
  const text = el("input", { type: "text", placeholder: "Cosa devo ricordarti?", maxlength: 500, "aria-label": "Testo" });
  const when = el("input", { type: "datetime-local", value: nowLocalInput(60), "aria-label": "Quando" });
  const add = async () => {
    if (!text.value.trim()) return toast("Scrivi cosa ricordare", true);
    try { await api.addReminder(text.value.trim(), when.value); toast("Promemoria creato"); loadReminders(); } catch (e) { toast(errText(e), true); }
  };
  return el("div", { class: "page" },
    panelHead("Promemoria", "Te li invio su Telegram all'ora giusta."),
    el("div", { class: "form-row" }, text, when, el("button", { class: "btn primary", onclick: add }, icon("plus", 16), "Aggiungi")),
    S.reminders.length
      ? el("div", { class: "list" }, S.reminders.map((r) => el("div", { class: "item" },
        el("div", {}, el("b", {}, r.text), el("small", {}, fmtDate(r.due_at))),
        el("button", { class: "icon-btn", title: "Elimina", "aria-label": "Elimina", onclick: async () => { try { await api.deleteReminder(r.id); loadReminders(); } catch (e) { toast(errText(e), true); } } }, icon("trash", 18)))))
      : el("div", { class: "empty" }, "Nessun promemoria attivo."),
    tasksPanel(),
  );
}

// ------------------------------------------------------------------ controllo PC
function buildPc() {
  if (!isTauri) return el("div", { class: "page" }, panelHead("Controllo PC", ""), el("div", { class: "empty" }, "Disponibile solo nell'app per Windows."));
  const act = (label, action, args) => async () => {
    try { logPc(`${label}: ${await local(action, args)}`); } catch (e) { logPc(`${label}: ${e}`, false); }
  };
  const vol = el("input", { type: "range", min: 0, max: 100, value: 40, "aria-label": "Volume" });
  const bri = el("input", { type: "range", min: 10, max: 100, value: 70, "aria-label": "Luminosità" });
  vol.addEventListener("change", act("Volume", "pc_volume", { level: Number(vol.value) }));
  bri.addEventListener("change", act("Luminosità", "pc_brightness", { level: Number(bri.value) }));
  const url = el("input", { type: "text", placeholder: "https://…", "aria-label": "Indirizzo" });
  const app = el("input", { type: "text", placeholder: "Nome app (es. notepad, calc)", "aria-label": "Applicazione" });
  return el("div", { class: "page" },
    panelHead("Controllo PC", S.ws ? "Collegato: JARVIS può agire su questo computer." : "Scollegato dal server: i comandi vocali e di Telegram non arrivano."),
    el("div", { class: "grid2" },
      el("div", { class: "card" }, el("h3", {}, icon("volume", 16), "Audio"), vol,
        el("div", { class: "row" }, el("button", { class: "btn", onclick: act("Volume", "pc_volume", { action: "mute" }) }, "Muto"), el("button", { class: "btn", onclick: act("Volume", "pc_volume", { action: "down" }) }, "−"), el("button", { class: "btn", onclick: act("Volume", "pc_volume", { action: "up" }) }, "+"))),
      el("div", { class: "card" }, el("h3", {}, icon("sun", 16), "Schermo"), bri,
        el("div", { class: "row" }, el("button", { class: "btn", onclick: act("Blocco", "pc_lock", {}) }, icon("lock", 16), "Blocca il PC"))),
      el("div", { class: "card" }, el("h3", {}, icon("globe", 16), "Apri sito"), url,
        el("div", { class: "row" }, el("button", { class: "btn primary", onclick: () => url.value && act("Sito", "pc_open_url", { url: url.value })() }, "Apri"))),
      el("div", { class: "card" }, el("h3", {}, icon("monitor", 16), "Avvia app"), app,
        el("div", { class: "row" }, el("button", { class: "btn primary", onclick: () => app.value && act("App", "pc_open_app", { name: app.value })() }, "Avvia"))),
    ),
    el("h2", { class: "sub" }, "Attività"),
    S.pcLog.length ? el("div", { class: "log" }, S.pcLog.map((l) => el("div", { class: l.ok ? "" : "bad" }, el("time", {}, l.at.toLocaleTimeString("it-IT")), l.text))) : el("div", { class: "empty" }, "Nessuna azione eseguita."),
  );
}

// ------------------------------------------------------------------ impostazioni
function buildSettings() {
  const url = el("input", { type: "text", value: cfg.url, spellcheck: "false", "aria-label": "URL del server" });
  const token = el("input", { type: "password", value: cfg.token, autocomplete: "off", "aria-label": "Token personale" });
  const result = el("p", { class: "tiny" });
  const test = async () => {
    result.textContent = "Provo…";
    const saved = { ...cfg };
    cfg.url = url.value.trim().replace(/\/+$/, ""); cfg.token = token.value.trim();
    try {
      const st = await api.status();
      result.textContent = `Collegato (v${st.version}). ${st.freellm.ready ? "Intelligenza pronta." : "Intelligenza non ancora pronta."}`;
      result.className = "tiny ok";
    } catch (e) { result.textContent = errText(e); result.className = "tiny bad"; Object.assign(cfg, saved); }
  };
  const save = async () => {
    cfg.url = url.value.trim().replace(/\/+$/, "");
    cfg.token = token.value.trim();
    localStorage.setItem("jarvis.url", cfg.url);
    cfg.where = await saveToken(cfg.token);
    toast("Impostazioni salvate");
    start();
  };
  const autostart = el("input", { type: "checkbox", id: "autostart" });
  if (isTauri) invoke("autostart_get").then((v) => (autostart.checked = !!v)).catch(() => {});
  autostart.addEventListener("change", () => invoke("autostart_set", { enabled: autostart.checked }).catch((e) => toast(String(e), true)));
  const speak = el("input", { type: "checkbox", id: "speak" });
  speak.checked = voiceOn();
  speak.addEventListener("change", () => { localStorage.setItem("jarvis.speak", speak.checked ? "1" : "0"); if (!speak.checked) speaker.stop(); });
  const vbox = el("div", { class: "voice-box" });
  const drawVoice = () => {
    const log = el("pre", { class: "voice-log" }, voice.log.slice(-12).join("\n"));
    vbox.replaceChildren(
      el("p", { class: "tiny" }, voice.installing ? "Installazione in corso: servono alcuni minuti e circa 3 GB (non chiudere JARVIS)."
        : voice.installed ? (voice.running ? "Voce di JARVIS pronta." : "Voce installata: si avvia al primo utilizzo.")
        : "La voce clonata di JARVIS (XTTS v2) gira sul tuo PC, gratis. Si scaricano circa 3 GB una volta sola."),
      voice.error ? el("p", { class: "tiny bad" }, voice.error) : null,
      el("div", { class: "row" },
        !voice.installed && !voice.installing ? el("button", { class: "btn primary", onclick: installVoice }, "Installa la voce") : null,
        voice.installed ? el("button", { class: "btn", onclick: () => speaker.speak("Buongiorno, signore. Tutti i sistemi sono operativi.") }, "Prova la voce") : null,
        voice.installed && !voice.installing ? el("button", { class: "btn danger", onclick: async () => { speaker.stop(); await removeVoice(); } }, "Rimuovi la voce") : null),
      voice.installing || voice.log.length ? log : null);
  };
  drawVoice();
  const stopVoice = onVoiceChange(() => (vbox.isConnected ? drawVoice() : stopVoice()));
  // privacy: cosa è cifrato, cosa esce dal server, voce neurale sì/no, cancellazione di chat e cache
  const pbox = el("div", { class: "field" });
  const drawPrivacy = async () => {
    if (!cfg.token) return;
    try {
      const p = await api.privacy(), enc = p.encryption || {};
      const tts = p.flows.find((f) => f.id === "tts");
      let armed = 0;
      pbox.replaceChildren(el("b", {}, "Privacy e sicurezza"),
        el("small", {}, `Cifratura dei dati: ${enc.enabled ? "attiva (AES-256-GCM)" : "SPENTA"} · dati sensibili verso i modelli: ${p.redaction === "off" ? "non mascherati" : "mascherati"}`),
        enc.shared_with_token ? el("small", { class: "bad" }, "La chiave di cifratura coincide con il token: imposta ENCRYPTION_KEY separata su Render.") : null,
        el("small", {}, "Esce dal server: " + p.flows.filter((f) => f.on).map((f) => f.label.split(" (")[0]).join(", ") + "."),
        tts ? el("label", { class: "check" }, el("input", { type: "checkbox", checked: tts.on, onchange: async (e) => { try { await api.setNeuralVoice(e.target.checked); toast(e.target.checked ? "Voce neurale attiva" : "Solo voce locale: nessun testo esce per la voce"); } catch (er) { toast(errText(er), true); } } }), "Voce neurale del server (invia il testo, senza dati personali, a Microsoft)") : null,
        el("div", { class: "row" }, el("button", { class: "btn danger", onclick: async (e) => {
          const b = e.currentTarget;
          if (Date.now() - armed > 4000) { armed = Date.now(); b.textContent = "Conferma: cancella chat e cache"; setTimeout(() => { b.textContent = "Cancella chat e cache"; }, 4000); return; }
          armed = 0;
          try { await api.wipe(); S.histSig = null; chatLog?.replaceChildren(); addMessage("sys", "Chat e cache cancellate. Ricordi e promemoria restano."); toast("Chat e cache cancellate"); } catch (er) { toast(errText(er), true); }
        } }, "Cancella chat e cache")));
    } catch { /* server non pronto */ }
  };
  drawPrivacy();
  return el("div", { class: "page narrow" },
    panelHead("Impostazioni", "Collegamento al tuo JARVIS."),
    el("label", { class: "field" }, "Indirizzo del server", url),
    el("label", { class: "field" }, "Token personale", token,
      el("small", {}, cfg.where === "keyring" ? "Salvato nel Gestore credenziali di Windows, cifrato dall'account." : "Salvato su questo computer (nel browser di prova).")),
    el("div", { class: "row" }, el("button", { class: "btn", onclick: test }, "Prova il collegamento"), el("button", { class: "btn primary", onclick: save }, "Salva")),
    result,
    el("label", { class: "check" }, speak, "Leggi le risposte con la voce di JARVIS"),
    isTauri ? vbox : null,
    pbox,
    isTauri ? el("label", { class: "check" }, autostart, "Avvia JARVIS con Windows (resta nella barra delle applicazioni)") : null,
    el("div", { class: "row" }, el("button", { class: "btn danger", onclick: async () => { await clearToken(); cfg.token = ""; token.value = ""; stop(); toast("Token rimosso da questo computer"); } }, "Rimuovi il token da questo PC")),
    el("p", { class: "tiny" }, "Scorciatoia: Alt+Spazio mostra o nasconde la finestra."),
    isTauri ? el("div", { class: "row" }, el("button", { class: "btn danger", title: "Chiude JARVIS, la voce e tutti i suoi processi", onclick: () => invoke("quit_app").catch((e) => toast(String(e), true)) }, "Esci definitivamente")) : null,
  );
}

// ------------------------------------------------------------------ conferme
let modalOpen = null;
function renderPending() {
  const first = S.pending[0];
  if (!first) { modalOpen?.remove(); modalOpen = null; return; }
  if (modalOpen?.dataset.id === first.id) return;
  modalOpen?.remove();
  const decide = async (ok) => {
    try { const r = await api.decide(first.id, ok); toast(ok ? r.result || "Approvata" : "Rifiutata"); } catch (e) { toast(errText(e), true); }
    pollPending();
  };
  modalOpen = el("div", { class: "overlay", dataset: { id: first.id } },
    el("div", { class: "dialog", role: "alertdialog", "aria-label": "Conferma richiesta" },
      el("div", { class: "dlg-icon" }, icon("shield", 28)),
      el("h2", {}, "Conferma richiesta"),
      el("p", {}, first.summary),
      el("small", {}, `Scade tra ${Math.max(1, Math.round(first.expires_in / 60))} min · JARVIS non può farlo senza il tuo consenso`),
      el("div", { class: "row end" }, el("button", { class: "btn", onclick: () => decide(false) }, "Rifiuta"), el("button", { class: "btn primary", onclick: () => decide(true) }, "Approva"))));
  document.body.append(modalOpen);
  invoke("show_window").catch(() => {});
}

function confirmLocal(text) {
  return new Promise((resolve) => {
    const done = (v) => { o.remove(); resolve(v); };
    const o = el("div", { class: "overlay" }, el("div", { class: "dialog", role: "alertdialog" },
      el("div", { class: "dlg-icon warn" }, icon("shield", 28)), el("h2", {}, "Azione sul PC"), el("p", {}, text),
      el("div", { class: "row end" }, el("button", { class: "btn", onclick: () => done(false) }, "Rifiuta"), el("button", { class: "btn danger", onclick: () => done(true) }, "Consenti"))));
    document.body.append(o);
    invoke("show_window").catch(() => {});
  });
}

// ------------------------------------------------------------------ canale col server
function connect() {
  clearInterval(wsPing);
  ws?.close();
  if (!isTauri || !cfg.token) return;
  ws = new WebSocket(`${cfg.url.replace(/^http/, "ws")}/ws/pc`);
  ws.onopen = () => ws.send(JSON.stringify({ token: cfg.token, caps: { voice: voice.installed } }));
  ws.onmessage = async (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "ready") {
      wsRetry = 0; S.ws = true; renderSide();
      wsPing = setInterval(() => ws.readyState === 1 && ws.send('{"type":"ping"}'), 25_000);
    } else if (msg.type === "notify") {
      addMessage("bot", msg.text);
      invoke("notify", { title: "JARVIS", body: msg.text }).catch(() => {});
    } else if (msg.type === "command") {
      const out = await runCommand(msg.action, msg.args || {});
      ws.send(JSON.stringify({ type: "result", id: msg.id, output: out }));
    }
  };
  ws.onclose = () => {
    clearInterval(wsPing); S.ws = false; renderSide();
    if (cfg.token) setTimeout(connect, Math.min(30_000, 1000 * 2 ** wsRetry++));
  };
}

async function runCommand(action, args) {
  if (action === "tts") { // il server (e quindi il telefono) chiede di leggere un testo con la voce di JARVIS
    if (!voice.installed) return "Voce non installata sul PC.";
    try { return await toBase64(await synth(String(args.text || "").slice(0, 500))); } catch (e) { return `Errore: ${e}`; }
  }
  const ask = SENSITIVE[action];
  if (ask && !(await confirmLocal(ask(args)))) { logPc(`${action}: rifiutato`, false); return "Azione rifiutata dall'utente."; }
  try { const out = await local(action, args); logPc(`${action}: ${out}`); return out; } catch (e) { logPc(`${action}: ${e}`, false); return `Errore: ${e}`; }
}

// ------------------------------------------------------------------ cicli di aggiornamento
let timers = [];
async function refreshStatus() {
  if (!cfg.token) return;
  try { S.status = await api.status(); S.online = true; } catch (e) { S.online = e.status === 401 ? false : S.online; if (e.status === 0) S.online = false; if (e.status === 401) toast(errText(e), true); }
  renderSide();
}
async function pollPending() {
  if (!cfg.token) return;
  try { S.pending = await api.pending(); } catch { return; }
  renderPending();
}
function start() {
  stop();
  if (!cfg.token) return;
  refreshStatus(); pollPending(); loadHistory(); connect(); loadNotes(); checkUpdate();
  closeStream = openStream({ url: () => cfg.url, token: () => cfg.token }, {
    onNotification: onNote,
    onRead: (ids) => { S.notes.forEach((n) => { if (!ids || ids.includes(n.id)) n.read = true; }); renderRail(); if (S.view === "notifications") renderView(); },
    onSync: ({ scope, origin }) => {  // Telegram, app Android o server hanno cambiato qualcosa: ci si aggiorna subito
      if (scope === "code") { if (origin !== deviceId) studioInst?.onSync(); }
      else if (scope === "reminders") loadReminders();
      else if (scope === "tasks") loadTasks();
      else if (scope === "brain" || scope === "memories") loadBrain();
      else if (scope === "chat" && origin !== deviceId) loadHistory(true);
    },
    onState: (st) => { const was = S.live; S.live = st; if (st === "on" && was !== "on") { loadNotes(); loadReminders(); loadTasks(); loadHistory(true); } else if (S.view === "notifications") renderView(); },
  });
  timers = [setInterval(refreshStatus, 20_000), setInterval(pollPending, 4_000)];
}
function stop() {
  timers.forEach(clearInterval); timers = [];
  closeStream?.(); closeStream = null; S.live = "off";
  clearInterval(wsPing); ws?.close(); S.ws = false; S.status = null; S.online = false; S.pending = [];
  renderPending(); renderSide();
}

// ------------------------------------------------------------------ avvio
(async () => {
  initUpdates();
  const { token, where } = await loadToken();
  cfg.token = token; cfg.where = where;
  shell();
  const firstRun = isTauri && !cfg.token && !localStorage.getItem("jarvis.wizard"); // installazione nuova: procedura guidata
  if (isTauri && !localStorage.getItem("jarvis.init") && !firstRun) { // chi aggiorna da una versione precedente: parte con Windows come prima
    localStorage.setItem("jarvis.init", "1");
    invoke("autostart_set", { enabled: true }).catch(() => {});
  }
  if (isTauri && cfg.token) localStorage.setItem("jarvis.wizard", "1");
  if (!cfg.token) S.view = "settings";
  renderRail(); renderView();
  if (cfg.token) start();
  await initVoice();
  if (firstRun) {
    runWizard({ cfg, api, invoke, saveToken, errText, installVoice, onDone: (r) => { renderRail(); renderView(); if (cfg.token) start(); if (r.voice) setView("settings"); } });
  }
  onVoiceChange(() => { if (ws?.readyState === 1) ws.send(JSON.stringify({ type: "caps", voice: voice.installed })); });
  if (isTauri && !firstRun && !voice.installed && !voice.installing && !localStorage.getItem("jarvis.voice.asked")) {
    localStorage.setItem("jarvis.voice.asked", "1");
    const o = el("div", { class: "overlay" }, el("div", { class: "dialog", role: "dialog" },
      el("div", { class: "dlg-icon" }, icon("volume", 28)), el("h2", {}, "Voce di JARVIS"),
      el("p", {}, "Vuoi installare la voce clonata di JARVIS? Gira sul tuo PC, è gratuita e serve anche al telefono quando il PC è acceso."),
      el("small", {}, "Download di circa 3 GB, una volta sola. Puoi farlo anche dopo da Impostazioni."),
      el("div", { class: "row end" }, el("button", { class: "btn", onclick: () => o.remove() }, "Più tardi"),
        el("button", { class: "btn primary", onclick: () => { o.remove(); installVoice(); setView("settings"); } }, "Installa"))));
    document.body.append(o);
  }
})();
