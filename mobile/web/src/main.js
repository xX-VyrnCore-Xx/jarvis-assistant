import { Jarvis, ApiError } from "@shared/api.js";
import { el, fmtDate, fmtTokens, fmtUptime, markdown, pct } from "@shared/format.js";
import { icon } from "@shared/icons.js";
import { Speaker } from "@shared/speech.js";
import { openStream } from "@shared/stream.js";
import { dictationAvailable, haptic, hideSplash, onBack, paintSystemBars, startDictation, stopDictation } from "./native.js";
import { initPush, teardownPush } from "./push.js";

// URL pubblico del server (non è un segreto); il token personale resta nella memoria privata dell'app
const DEFAULT_URL = "https://jarvis-ai-841t.onrender.com";
const SESSION = "mobile";
const TABS = [["chat", "Chat", "chat"], ["tokens", "Token", "gauge"], ["reminders", "Promemoria", "clock"], ["more", "Altro", "sliders"]];
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
const cfg = { url: (store.get("jarvis.url") || DEFAULT_URL).replace(/\/+$/, ""), token: store.get("jarvis.token") };
const api = new Jarvis({ url: () => cfg.url, token: () => cfg.token });
const speaker = new Speaker({ tts: (t) => api.tts(t) });
const voiceOn = () => store.get("jarvis.speak") !== "0";
const S = { tab: "chat", status: null, checked: false, tokens: null, tokensErr: "", tokensAt: null, reminders: [], remindersLoaded: false, notes: [], pending: [], online: false, busy: false, mic: false, canMic: false, sheets: [] };

const $app = document.getElementById("m-app");
let top, content, tabs, log, input, sendBtn, micBtn, downBtn, chatView, hello, chips;
let timers = [];
let closeStream = null;

const errText = (e) => (e instanceof ApiError ? e.message : String(e));
const greeting = () => { const h = new Date().getHours(); return h < 5 ? "Buonanotte" : h < 13 ? "Buongiorno" : h < 18 ? "Buon pomeriggio" : "Buonasera"; };
const clock = (d = new Date()) => d.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });

function toast(text, bad = false, action = null) {
  const t = document.getElementById("m-toast");
  t.replaceChildren(el("span", {}, text), action ? el("button", { onclick: () => { t.className = ""; action.fn(); } }, action.label) : null);
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
  add(g, "stop", { offset: "0", "stop-color": "#ffc15e" }); add(g, "stop", { offset: "1", "stop-color": "#ff6f4d" });
  for (const [cls, r, w] of [["r1", 44, 5], ["r2", 32, 4], ["r3", 21, 3.4]]) {
    const grp = add(svg, "g", { class: cls });
    add(grp, "circle", { cx: 50, cy: 50, r, fill: "none", stroke: "url(#og)", "stroke-width": w, class: cls === "r3" ? "dash" : "" });
  }
  add(svg, "circle", { cx: 50, cy: 50, r: 7, fill: "url(#og)" });
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
  $app.replaceChildren(top, content, tabs);
  renderTop(); renderTabs();
}

const unread = () => S.notes.filter((n) => !n.read).length;

function renderTop() {
  const t = S.status?.tokens;
  const low = t && t.documented_monthly_tokens && t.remaining_tokens / t.documented_monthly_tokens < 0.15;
  const offline = cfg.token && S.checked && !S.online;
  top.replaceChildren(
    el("div", { class: "m-title" }, orb(), el("div", {}, el("h1", {}, "JARVIS"), el("p", {}, `${greeting()}, signore`))),
    el("div", { class: "m-right" },
      t ? el("button", { class: `m-pill${low ? " low" : ""}`, onclick: () => setTab("tokens"), "aria-label": "Token disponibili" }, icon("gauge", 15), fmtTokens(t.remaining_tokens)) : null,
      el("button", { class: "m-bell", onclick: openNotes, "aria-label": "Notifiche" }, icon("bell", 21), unread() ? el("i", {}, unread() > 9 ? "9+" : String(unread())) : null)),
  );
  document.getElementById("m-offline")?.remove();
  if (offline) {
    top.insertAdjacentElement("afterend", el("div", { id: "m-offline", class: "m-offline", role: "status" }, icon("offline", 17),
      "Server non raggiungibile: si sta svegliando o manca la rete.", el("button", { class: "m-ghost", style: "margin-left:auto;min-height:30px;padding:0 10px", onclick: () => { refreshStatus(); toast("Controllo il server…"); } }, "Riprova")));
  }
}

function renderTabs() {
  const badge = { reminders: S.reminders.filter((r) => new Date(r.due_at) - Date.now() < 86_400_000).length };
  tabs.replaceChildren(...TABS.map(([id, label, ic]) =>
    el("button", { class: `m-tab${S.tab === id ? " on" : ""}`, dataset: { tab: id }, onclick: () => { haptic(); setTab(id); }, "aria-label": label },
      el("span", { class: "m-tab-ic" }, icon(ic, 23), badge[id] ? el("span", { class: "dot" }, String(badge[id])) : null), el("small", {}, label))));
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
  chatView = el("div", { class: "m-chat" }, log, downBtn, chips, el("div", { class: "m-composer" }, micBtn, input, sendBtn));
  showHello();
  return chatView;
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
  const typing = el("div", { class: "m-msg bot" }, el("div", { class: "m-bubble typing" }, el("i"), el("i"), el("i")));
  log.append(typing); log.scrollTop = log.scrollHeight;
  try {
    const reply = await api.chat(msg, SESSION);
    typing.remove();
    bubble("bot", reply);
    haptic("light");
    if (voiceOn() && S.status?.voice) speaker.speak(reply);
    refreshStatus();
  } catch (e) { typing.remove(); bubble("sys", errText(e)); }
  finally { S.busy = false; if (!speaker.speaking) setOrb(""); }
}

async function loadHistory() {
  try {
    const rows = await api.history(SESSION, 30);
    buildChat(); log.replaceChildren(); hello = null;
    if (!rows.length) return showHello();
    rows.forEach((r) => bubble(r.role === "user" ? "user" : "bot", r.content, { fresh: false }));
    log.scrollTop = log.scrollHeight;
  } catch { /* offline: resta la schermata di benvenuto */ }
}

// ---------------------------------------------------------------- token
async function loadTokens(force = false) {
  if (!cfg.token) return;
  try { S.tokens = await api.tokens(force); S.tokensErr = ""; S.tokensAt = new Date(); } catch (e) { S.tokensErr = errText(e); }
  if (S.tab === "tokens") renderTab();
}

function semi(p, big, small) {
  const R = 80, L = Math.PI * R;
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 200 112");
  const arc = (cls, len) => { const path = document.createElementNS(NS, "path"); path.setAttribute("d", "M20 100 A80 80 0 0 1 180 100"); path.setAttribute("class", cls); if (len != null) path.setAttribute("stroke-dasharray", `${len} ${L}`); return path; };
  svg.append(arc("s-track"), arc(`s-bar${p < 15 ? " low" : p < 35 ? " mid" : ""}`, (L * p) / 100));
  return el("div", { class: "semi" }, svg, el("div", { class: "semi-t" }, el("strong", {}, big), el("span", {}, small)));
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
  return page;
}

// ---------------------------------------------------------------- promemoria
async function loadReminders() {
  if (!cfg.token) return;
  try { S.reminders = await api.reminders(); S.remindersLoaded = true; } catch (e) { toast(errText(e), true); }
  renderTabs();
  if (S.tab === "reminders") renderTab();
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
  return { close, sheet };
}

const localInput = (d) => { const x = new Date(d.getTime() - d.getTimezoneOffset() * 60_000); return x.toISOString().slice(0, 16); };
const atHour = (h, plusDays = 0) => { const d = new Date(); d.setDate(d.getDate() + plusDays); d.setHours(h, 0, 0, 0); return d; };

function newReminder() {
  const text = el("input", { type: "text", placeholder: "Cosa devo ricordarti?", maxlength: 500, "aria-label": "Testo" });
  const when = el("input", { type: "datetime-local", value: localInput(new Date(Date.now() + 3_600_000)), "aria-label": "Quando" });
  const presets = [["Tra 15 min", () => new Date(Date.now() + 900_000)], ["Tra 1 ora", () => new Date(Date.now() + 3_600_000)],
    ["Stasera 21:00", () => (atHour(21) > new Date() ? atHour(21) : atHour(21, 1))], ["Domani 9:00", () => atHour(9, 1)]];
  const s = openSheet("Nuovo promemoria", text,
    el("div", { class: "m-presets" }, presets.map(([l, f]) => el("button", { onclick: () => { when.value = localInput(f()); haptic(); } }, l))), when,
    el("button", { class: "m-primary", style: "width:100%", onclick: async () => {
      if (!text.value.trim()) return toast("Scrivi cosa ricordare", true);
      try { await api.addReminder(text.value.trim(), when.value); s.close(); haptic("medium"); toast("Promemoria creato"); loadReminders(); } catch (e) { toast(errText(e), true); }
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
    toast("Promemoria eliminato", false, { label: "Annulla", fn: async () => { try { await api.addReminder(r.text, localInput(new Date(r.due_at))); loadReminders(); } catch (e) { toast(errText(e), true); } } });
  } catch (e) { toast(errText(e), true); renderTab(); }
}

function reminderCard(r) {
  const due = relDue(r.due_at);
  const card = el("div", { class: "m-card rem" }, el("div", {}, el("b", {}, r.text), el("small", { class: due.soon ? "soon" : "" }, due.label)),
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
  page.append(el("div", { class: "m-head" }, el("h2", {}, "Promemoria"), el("button", { class: "m-ghost", onclick: () => { haptic(); loadReminders(); } }, icon("refresh", 16), "Aggiorna")));
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
    store.set("jarvis.url", cfg.url); store.set("jarvis.token", cfg.token);
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
    el("h3", { class: "m-sub" }, "Aspetto"),
    el("div", { class: "m-card" }, seg),
    el("h3", { class: "m-sub" }, "Voce e notifiche"),
    el("div", { class: "m-card" },
      el("label", { class: "m-row" }, el("span", {}, st?.voice ? "Leggi le risposte (voce di JARVIS)" : "Leggi le risposte (serve il PC acceso)"), speakSwitch),
      el("div", { class: "m-row" }, el("span", {}, "Prova la voce"), el("button", { class: "m-ghost", onclick: () => speaker.speak("Buongiorno, signore. Tutti i sistemi sono operativi.") }, icon("volume", 16), "Ascolta")),
      el("div", { class: "m-row" }, el("span", {}, "Notifica di prova"), el("button", { class: "m-ghost", onclick: async () => { try { await api.testNotification(); toast("Inviata"); } catch (e) { toast(errText(e), true); } } }, icon("bell", 16), "Invia"))),
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
    el("button", { class: "m-danger", onclick: () => { teardownPush(api).catch(() => {}); store.del("jarvis.token"); cfg.token = ""; stop(); renderTab(); toast("Token rimosso da questo telefono"); } }, "Rimuovi il token da questo telefono"),
    el("p", { class: "m-about" }, st ? `JARVIS · server v${st.version}` : "JARVIS"));
}

// ---------------------------------------------------------------- notifiche
const KIND = { reminder: "clock", alert: "shield", pending: "shield", info: "bell" };
let notesSheet = null;

async function loadNotes() {
  if (!cfg.token) return;
  try { S.notes = await api.notifications(40); } catch { return; }
  renderTop();
  if (notesSheet) fillNotes();
}

function onNote(n) {
  if (S.notes.some((x) => x.id === n.id)) return;
  S.notes.unshift(n);
  renderTop();
  haptic("heavy");
  if (notesSheet) fillNotes(); else toast(n.title);
}

function fillNotes() {
  const body = notesSheet.sheet.querySelector(".notes-list");
  body.replaceChildren(...(S.notes.length
    ? S.notes.map((n) => el("div", { class: `m-note-row${n.read ? "" : " unread"}` }, el("span", { class: "m-note-ic" }, icon(KIND[n.kind] || "bell", 18)),
      el("div", {}, el("b", {}, n.title), n.body ? el("p", {}, n.body) : null, el("small", {}, fmtDate(n.created_at)))))
    : [el("div", { class: "m-empty" }, el("div", { class: "ico" }, icon("bell", 30)), "Nessuna notifica.")]));
}

function openNotes() {
  if (notesSheet) return;
  const list = el("div", { class: "notes-list" });
  const s = openSheet("Notifiche", list, el("div", { class: "m-btns" },
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
    onState: (st) => { if (st === "on") loadNotes(); },
  });
  initPush(api).catch(() => {});
  timers = [setInterval(refreshStatus, 30_000), setInterval(pollPending, 5_000)];
}
function stop() { closeStream?.(); closeStream = null; timers.forEach(clearInterval); timers = []; S.status = null; S.checked = false; S.online = false; S.pending = []; renderTop(); renderPending(); }

// risparmia batteria e dati: nulla gira con l'app in secondo piano
document.addEventListener("visibilitychange", () => { if (document.hidden) { speaker.stop(); closeStream?.(); closeStream = null; timers.forEach(clearInterval); timers = []; } else start(); });

// tasto Indietro: chiude i fogli, poi torna alla chat, poi mette l'app in secondo piano
onBack(() => {
  const sheet = S.sheets[S.sheets.length - 1];
  if (sheet) { sheet.close(); return true; }
  if (S.tab !== "chat") { setTab("chat"); return true; }
  return false;
});

applyTheme();
shell();
if (!cfg.token) S.tab = "more";
renderTabs(); renderTab();
if (cfg.token) start();
dictationAvailable().then((ok) => { S.canMic = ok; if (micBtn) micBtn.style.display = ok ? "" : "none"; });
setTimeout(hideSplash, 350);
