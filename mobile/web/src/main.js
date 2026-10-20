import { Jarvis, ApiError } from "@shared/api.js";
import { el, fmtDate, fmtTokens, fmtUptime, markdown, nowLocalInput, pct } from "@shared/format.js";
import { icon } from "@shared/icons.js";

// URL pubblico del server (non è un segreto); il token personale resta nella memoria privata dell'app
const DEFAULT_URL = "https://jarvis-ai-841t.onrender.com";
const SESSION = "mobile";
const TABS = [["chat", "Chat", "chat"], ["tokens", "Token", "gauge"], ["reminders", "Promemoria", "bell"], ["more", "Altro", "sliders"]];
const CHIPS = [["Token disponibili", "Quanti token mi restano questo mese?"], ["Che ore sono", "Che ore sono?"], ["Agenda", "Cosa ho in agenda nei prossimi giorni?"], ["Email", "Ho email non lette importanti?"]];

const cfg = { url: (localStorage.getItem("jarvis.url") || DEFAULT_URL).replace(/\/+$/, ""), token: localStorage.getItem("jarvis.token") || "" };
const api = new Jarvis({ url: () => cfg.url, token: () => cfg.token });
const S = { tab: "chat", status: null, tokens: null, tokensErr: "", reminders: [], pending: [], online: false, busy: false };

const $app = document.getElementById("m-app");
let top, content, tabs, log, input, chatView;
let timers = [];

const errText = (e) => (e instanceof ApiError ? e.message : String(e));
function toast(text, bad = false) {
  const t = document.getElementById("m-toast");
  t.textContent = text; t.className = `show${bad ? " bad" : ""}`;
  clearTimeout(toast.t); toast.t = setTimeout(() => (t.className = ""), 3800);
}
const greeting = () => { const h = new Date().getHours(); return h < 5 ? "Buonanotte" : h < 13 ? "Buongiorno" : h < 18 ? "Buon pomeriggio" : "Buonasera"; };

// ---------------------------------------------------------------- struttura
function shell() {
  top = el("header", { class: "m-top" });
  content = el("main", { id: "m-view" });
  tabs = el("nav", { class: "m-tabs", "aria-label": "Sezioni" });
  $app.replaceChildren(top, content, tabs);
  renderTop(); renderTabs();
}

function renderTop() {
  const t = S.status?.tokens;
  top.replaceChildren(
    el("div", { class: "m-title" }, el("span", { class: "m-logo" }), el("div", {}, el("h1", {}, "JARVIS"), el("p", {}, `${greeting()}, signore`))),
    el("div", { class: "m-right" },
      t ? el("button", { class: "m-pill", onclick: () => setTab("tokens"), "aria-label": "Token disponibili" }, icon("gauge", 15), fmtTokens(t.remaining_tokens)) : null,
      el("button", { class: `m-dot ${S.online ? "on" : ""}`, title: S.online ? "Online" : "Non raggiungibile", "aria-label": S.online ? "Online" : "Non raggiungibile", onclick: () => { refreshStatus(); toast("Controllo il server…"); } })),
  );
}

function renderTabs() {
  tabs.replaceChildren(...TABS.map(([id, label, ic]) =>
    el("button", { class: `m-tab${S.tab === id ? " on" : ""}`, dataset: { tab: id }, onclick: () => setTab(id), "aria-label": label }, el("span", { class: "m-tab-ic" }, icon(ic, 22)), el("small", {}, label))));
}

function setTab(id) {
  S.tab = id;
  renderTabs(); renderTab();
  if (id === "tokens") loadTokens();
  if (id === "reminders") loadReminders();
}

function renderTab() {
  content.className = `tab-${S.tab}`;
  const v = { chat: buildChat, tokens: buildTokens, reminders: buildReminders, more: buildMore }[S.tab]();
  content.replaceChildren(v);
}

// ---------------------------------------------------------------- chat
function bubble(role, text) {
  const node = el("div", { class: `m-msg ${role}` }, el("div", { class: "m-bubble" }, role === "bot" ? markdown(text) : el("p", {}, text)));
  log.append(node);
  log.scrollTop = log.scrollHeight;
  return node;
}

function buildChat() {
  if (chatView) return chatView;
  log = el("div", { class: "m-log", "aria-live": "polite" });
  input = el("textarea", { id: "m-input", rows: 1, placeholder: "Scrivi a JARVIS…", "aria-label": "Messaggio", enterkeyhint: "send" });
  input.addEventListener("input", () => { input.style.height = "auto"; input.style.height = `${Math.min(input.scrollHeight, 120)}px`; });
  chatView = el("div", { class: "m-chat" },
    log,
    el("div", { class: "m-chips" }, CHIPS.map(([l, t]) => el("button", { onclick: () => send(t) }, l))),
    el("div", { class: "m-composer" }, input, el("button", { class: "m-send", "aria-label": "Invia", onclick: () => send() }, icon("send", 21))));
  bubble("sys", cfg.token ? "Pronto, signore." : "Vai su Altro e inserisci il token personale per iniziare.");
  return chatView;
}

async function send(text) {
  const msg = (text ?? input.value).trim();
  if (!msg || S.busy) return;
  if (!cfg.token) return setTab("more");
  if (text === undefined) { input.value = ""; input.style.height = "auto"; }
  bubble("user", msg);
  S.busy = true;
  const typing = el("div", { class: "m-msg bot" }, el("div", { class: "m-bubble typing" }, el("i"), el("i"), el("i")));
  log.append(typing); log.scrollTop = log.scrollHeight;
  try { bubble("bot", await api.chat(msg, SESSION)); refreshStatus(); }
  catch (e) { bubble("sys", errText(e)); }
  finally { typing.remove(); S.busy = false; }
}

async function loadHistory() {
  try {
    const rows = await api.history(SESSION, 30);
    buildChat(); log.replaceChildren();
    rows.forEach((r) => bubble(r.role === "user" ? "user" : "bot", r.content));
    if (!rows.length) bubble("sys", "Pronto, signore.");
  } catch { /* offline */ }
}

// ---------------------------------------------------------------- token
async function loadTokens(force = false) {
  if (!cfg.token) return;
  try { S.tokens = await api.tokens(force); S.tokensErr = ""; } catch (e) { S.tokensErr = errText(e); }
  if (S.tab === "tokens") renderTab();
}

function semi(p, big, small) {
  const R = 80, L = Math.PI * R;
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 200 112");
  const arc = (cls, len) => { const path = document.createElementNS(NS, "path"); path.setAttribute("d", "M20 100 A80 80 0 0 1 180 100"); path.setAttribute("class", cls); if (len != null) path.setAttribute("stroke-dasharray", `${len} ${L}`); return path; };
  svg.append(arc("s-track"), arc("s-bar", (L * p) / 100));
  return el("div", { class: "semi" }, svg, el("div", { class: "semi-t" }, el("strong", {}, big), el("span", {}, small)));
}

function buildTokens() {
  const t = S.tokens;
  const head = el("div", { class: "m-head" }, el("h2", {}, "Token disponibili"), el("button", { class: "m-ghost", onclick: () => { loadTokens(true); toast("Aggiorno…"); } }, icon("refresh", 16), "Aggiorna"));
  if (!t) return el("div", { class: "m-page" }, head, el("div", { class: "m-empty" }, S.tokensErr || "Carico i dati…"));
  const max = Math.max(...t.providers.map((p) => p.documented || p.remaining || 0), 1);
  return el("div", { class: "m-page" }, head,
    el("div", { class: "m-card hero" },
      semi(pct(t.remaining_tokens, t.documented_monthly_tokens), fmtTokens(t.remaining_tokens), "disponibili (stima)"),
      el("div", { class: "m-kv" },
        el("div", {}, el("small", {}, "Budget"), el("b", {}, fmtTokens(t.documented_monthly_tokens))),
        el("div", {}, el("small", {}, "Usati"), el("b", {}, fmtTokens(t.used_tokens))),
        el("div", {}, el("small", {}, "Richieste"), el("b", {}, t.used_requests))),
      el("p", { class: "m-note" }, t.resets_at ? `Si azzera ${fmtDate(t.resets_at)}` : "Si azzera a inizio mese")),
    el("h3", { class: "m-sub" }, "Per provider"),
    ...t.providers.map((p) => {
      const known = p.remaining != null;
      return el("div", { class: "m-card prov" },
        el("div", { class: "prov-top" }, el("b", {}, p.platform), el("span", {}, known ? fmtTokens(p.remaining) : "n/d")),
        el("div", { class: "m-bar" }, el("i", { style: `width:${known ? Math.max(2, ((p.remaining || 0) / max) * 100) : 0}%` })),
        el("small", {}, p.source === "live" ? "quota reale" : p.source === "estimate" ? "stima dal budget mensile" : "senza budget pubblicato"));
    }),
    el("p", { class: "m-note" }, t.note));
}

// ---------------------------------------------------------------- promemoria
async function loadReminders() {
  if (!cfg.token) return;
  try { S.reminders = await api.reminders(); } catch (e) { toast(errText(e), true); }
  if (S.tab === "reminders") renderTab();
}

function openSheet(title, ...body) {
  const close = () => { sheet.classList.remove("up"); setTimeout(() => sheet.remove(), 220); };
  const sheet = el("div", { class: "m-sheet-bg", onclick: (e) => e.target === sheet && close() },
    el("div", { class: "m-sheet", role: "dialog", "aria-label": title }, el("i", { class: "grab" }), el("h3", {}, title), ...body));
  document.body.append(sheet);
  requestAnimationFrame(() => sheet.classList.add("up"));
  return { close, sheet };
}

function newReminder() {
  const text = el("input", { type: "text", placeholder: "Cosa devo ricordarti?", maxlength: 500 });
  const when = el("input", { type: "datetime-local", value: nowLocalInput(60) });
  const s = openSheet("Nuovo promemoria", text, when, el("button", { class: "m-primary", onclick: async () => {
    if (!text.value.trim()) return toast("Scrivi cosa ricordare", true);
    try { await api.addReminder(text.value.trim(), when.value); s.close(); toast("Promemoria creato"); loadReminders(); } catch (e) { toast(errText(e), true); }
  } }, "Crea"));
  setTimeout(() => text.focus(), 260);
}

function buildReminders() {
  return el("div", { class: "m-page" },
    el("div", { class: "m-head" }, el("h2", {}, "Promemoria"), el("button", { class: "m-ghost", onclick: loadReminders }, icon("refresh", 16), "Aggiorna")),
    S.reminders.length
      ? S.reminders.map((r) => el("div", { class: "m-card rem" },
        el("div", {}, el("b", {}, r.text), el("small", {}, fmtDate(r.due_at))),
        el("button", { class: "m-icon", "aria-label": "Elimina", onclick: async () => { try { await api.deleteReminder(r.id); loadReminders(); } catch (e) { toast(errText(e), true); } } }, icon("trash", 19))))
      : el("div", { class: "m-empty" }, "Nessun promemoria attivo.", el("br"), "Te li mando su Telegram all'ora giusta."),
    el("button", { class: "m-fab", "aria-label": "Nuovo promemoria", onclick: newReminder }, icon("plus", 26)));
}

// ---------------------------------------------------------------- altro
function row(label, value, ok) { return el("div", { class: "m-row" }, el("span", {}, label), el("b", { class: ok === undefined ? "" : ok ? "ok" : "off" }, value)); }

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
    localStorage.setItem("jarvis.url", cfg.url); localStorage.setItem("jarvis.token", cfg.token);
    toast("Salvato"); start();
  };
  return el("div", { class: "m-page" },
    el("div", { class: "m-head" }, el("h2", {}, "Altro")),
    el("h3", { class: "m-sub" }, "Collegamento"),
    el("div", { class: "m-card form" }, el("label", {}, "Indirizzo del server", url), el("label", {}, "Token personale", token),
      el("div", { class: "m-btns" }, el("button", { class: "m-ghost", onclick: test }, "Prova"), el("button", { class: "m-primary", onclick: save }, "Salva")), out),
    el("h3", { class: "m-sub" }, "Stato"),
    el("div", { class: "m-card" },
      row("Server", S.online ? "online" : "non raggiungibile", S.online),
      row("Intelligenza", st ? (st.freellm.ready ? "pronta" : "non pronta") : "—", st ? st.freellm.ready : undefined),
      row("PC Windows", st ? (st.pc_connected ? "collegato" : "scollegato") : "—", st ? st.pc_connected : undefined),
      row("Telegram", st ? (st.telegram ? "attivo" : "spento") : "—", st ? st.telegram : undefined),
      row("Google", st ? (st.google ? "collegato" : "non collegato") : "—", st ? st.google : undefined),
      row("Memoria", st ? (st.memory === "supabase" ? "permanente" : "temporanea") : "—", st ? st.memory === "supabase" : undefined),
      st ? row("Attivo da", fmtUptime(st.uptime_s)) : null),
    el("div", { class: "m-card safe" }, icon("shield", 20), el("p", {}, "Le azioni sensibili, come inviare un'email, richiedono sempre la tua conferma.")),
    el("button", { class: "m-danger", onclick: () => { localStorage.removeItem("jarvis.token"); cfg.token = ""; stop(); renderTab(); toast("Token rimosso da questo telefono"); } }, "Rimuovi il token da questo telefono"));
}

// ---------------------------------------------------------------- conferme
let askSheet = null;
function renderPending() {
  const p = S.pending[0];
  if (!p) { askSheet?.close(); askSheet = null; return; }
  if (askSheet?.id === p.id) return;
  askSheet?.close();
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
  renderTop();
  if (S.tab === "more") renderTab();
}
async function pollPending() { if (!cfg.token) return; try { S.pending = await api.pending(); } catch { return; } renderPending(); }
function start() {
  stop();
  if (!cfg.token) return;
  refreshStatus(); pollPending(); loadHistory();
  timers = [setInterval(refreshStatus, 30_000), setInterval(pollPending, 5_000)];
}
function stop() { timers.forEach(clearInterval); timers = []; S.status = null; S.online = false; S.pending = []; renderTop(); renderPending(); }

// risparmia batteria e dati: nulla gira con l'app in secondo piano
document.addEventListener("visibilitychange", () => { if (document.hidden) { timers.forEach(clearInterval); timers = []; } else start(); });

shell();
if (!cfg.token) S.tab = "more";
renderTabs(); renderTab();
if (cfg.token) start();
