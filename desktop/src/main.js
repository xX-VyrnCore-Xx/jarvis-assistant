import { invoke } from "@tauri-apps/api/core";
import { Jarvis, ApiError } from "@shared/api.js";
import { el, fmtDate, fmtTokens, fmtUptime, markdown, nowLocalInput, pct } from "@shared/format.js";
import { icon } from "@shared/icons.js";
import { openStream } from "@shared/stream.js";
import { clearToken, loadToken, saveToken } from "./secrets.js";

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
  ["tokens", "Token", "gauge"],
  ["notifications", "Notifiche", "bell"],
  ["reminders", "Promemoria", "clock"],
  ["pc", "Controllo PC", "monitor"],
  ["settings", "Impostazioni", "sliders"],
];

const cfg = { url: (localStorage.getItem("jarvis.url") || DEFAULT_URL).replace(/\/+$/, ""), token: "", where: "local" };
const api = new Jarvis({ url: () => cfg.url, token: () => cfg.token });
const S = { view: "chat", status: null, tokens: null, tokensErr: "", pending: [], reminders: [], notes: [], live: "off", online: false, ws: false, pcLog: [], busy: false };

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
  if (v === "reminders") loadReminders();
  if (v === "notifications") loadNotes();
}

function renderView() {
  viewBox.className = `view-${S.view}`;
  if (S.view === "chat") return viewBox.replaceChildren(buildChat());
  if (S.view === "tokens") return viewBox.replaceChildren(buildTokens());
  if (S.view === "reminders") return viewBox.replaceChildren(buildReminders());
  if (S.view === "notifications") return viewBox.replaceChildren(buildNotes());
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
  side.replaceChildren(
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
    el("div", { class: "side-card hint" }, icon("shield", 16), el("span", {}, "Le azioni sensibili chiedono sempre la tua conferma.")),
  );
}

// ------------------------------------------------------------------ chat
function addMessage(role, text) {
  const body = role === "bot" ? markdown(text) : el("p", {}, text);
  const node = el("div", { class: `msg ${role}` }, el("div", { class: "who" }, role === "bot" ? "J.A.R.V.I.S." : role === "user" ? "Tu" : ""), el("div", { class: "bubble" }, body));
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
    panelHead("Conversazione", "Parla con JARVIS: usa gli stessi poteri di Telegram e della voce."),
    chatLog,
    el("div", { class: "chips" }, CHIPS.map(([label, text]) => el("button", { class: "chip", onclick: () => send(text) }, label))),
    el("div", { class: "composer" }, chatInput, el("button", { class: "send", title: "Invia", "aria-label": "Invia", onclick: () => send() }, icon("send", 20))),
  );
  addMessage("sys", cfg.token ? "Pronto, signore." : "Inserisci il token personale in Impostazioni per iniziare.");
  return chatView;
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
  try {
    addMessage("bot", await api.chat(msg, SESSION));
    refreshStatus();
  } catch (e) {
    addMessage("sys", errText(e));
  } finally {
    wait.remove();
    S.busy = false;
  }
}

async function loadHistory() {
  try {
    const rows = await api.history(SESSION, 30);
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

// ------------------------------------------------------------------ notifiche
const KIND = { reminder: "clock", alert: "shield", pending: "shield", info: "bell" };

async function loadNotes() {
  if (!cfg.token) return;
  try { S.notes = await api.notifications(60); } catch (e) { toast(errText(e), true); }
  renderRail();
  if (S.view === "notifications") renderView();
}

function onNote(n) {
  if (S.notes.some((x) => x.id === n.id)) return;
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

// ------------------------------------------------------------------ promemoria
async function loadReminders() {
  if (!cfg.token) return;
  try { S.reminders = await api.reminders(); } catch (e) { toast(errText(e), true); }
  if (S.view === "reminders") renderView();
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
  return el("div", { class: "page narrow" },
    panelHead("Impostazioni", "Collegamento al tuo JARVIS."),
    el("label", { class: "field" }, "Indirizzo del server", url),
    el("label", { class: "field" }, "Token personale", token,
      el("small", {}, cfg.where === "keyring" ? "Salvato nel Gestore credenziali di Windows, cifrato dall'account." : "Salvato su questo computer (nel browser di prova).")),
    el("div", { class: "row" }, el("button", { class: "btn", onclick: test }, "Prova il collegamento"), el("button", { class: "btn primary", onclick: save }, "Salva")),
    result,
    isTauri ? el("label", { class: "check" }, autostart, "Avvia JARVIS con Windows (resta nella barra delle applicazioni)") : null,
    el("div", { class: "row" }, el("button", { class: "btn danger", onclick: async () => { await clearToken(); cfg.token = ""; token.value = ""; stop(); toast("Token rimosso da questo computer"); } }, "Rimuovi il token da questo PC")),
    el("p", { class: "tiny" }, "Scorciatoia: Alt+Spazio mostra o nasconde la finestra."),
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
  ws.onopen = () => ws.send(JSON.stringify({ token: cfg.token }));
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
  refreshStatus(); pollPending(); loadHistory(); connect(); loadNotes();
  closeStream = openStream({ url: () => cfg.url, token: () => cfg.token }, {
    onNotification: onNote,
    onState: (st) => { const was = S.live; S.live = st; if (st === "on" && was !== "on") loadNotes(); else if (S.view === "notifications") renderView(); },
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
  const { token, where } = await loadToken();
  cfg.token = token; cfg.where = where;
  shell();
  if (isTauri && !localStorage.getItem("jarvis.init")) { // al primo avvio: parte con Windows
    localStorage.setItem("jarvis.init", "1");
    invoke("autostart_set", { enabled: true }).catch(() => {});
  }
  if (!cfg.token) S.view = "settings";
  renderRail(); renderView();
  if (cfg.token) start();
})();
