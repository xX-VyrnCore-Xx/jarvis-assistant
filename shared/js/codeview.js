// Sezione Codice: uno spazio di lavoro solo per programmare, con JARVIS al massimo (prompt da ingegnere, tutte le competenze di programmazione,
// strumenti code_* sempre pronti, piano del lavoro, revisione, CI). Condivisa da app Android e Windows: tutto arriva da /api/code/* e /code/chat/stream.
import "./codeview.css";
import { el, markdown } from "./format.js";
import { icon } from "./icons.js";
import { Typewriter } from "./typewriter.js";

const FEATURED = ["revisione-codice", "debug-sistematico", "test-e-qualita", "architettura-software", "refactoring-e-codice-legacy", "sicurezza-applicativa",
  "ottimizzazione-prestazioni", "git-e-devops", "python-pro", "javascript-typescript", "sql-database", "ci-cd-github-actions"];

const QUICK = [
  ["Nuovo repository", "Privato, con scheletro e CI", "@create"],
  ["Progetto con JARVIS", "Descrivi l'idea, lui costruisce", "Voglio creare un nuovo progetto. Chiedimi cosa deve fare, scegli lo stack più adatto e crea il repository privato con scheletro, test e CI."],
  ["Riprendi un progetto", "Scegli tra i tuoi repository", null],
  ["Spiega il codice", "Mappa e architettura", "Usa la mappa del codice per spiegarmi com'è fatto il progetto: componenti, flussi principali e punti delicati."],
  ["Scrivi i test", "Copri i casi chiave", "Individua le parti senza test e scrivi i test mancanti più importanti, poi controlla la CI."],
  ["Rivedi le modifiche", "Prima del commit", "Fai una revisione critica delle modifiche non committate (code_review e diff) e correggi i problemi."],
  ["Correggi la CI", "Legge i log e ripara", "Controlla la CI; se è rossa leggi i log, trova la causa vera (senza aggirare i test) e correggila."],
  ["Trova i bug", "Casi limite e concorrenza", "Cerca bug probabili, casi limite non gestiti e problemi di concorrenza nel codice più importante; proponi e applica le correzioni."],
  ["Sicurezza", "Audit applicativo", "Fai un audit di sicurezza del progetto (input non fidati, segreti, dipendenze, autenticazione) e correggi ciò che è sicuro correggere."],
  ["Refactor", "Più chiaro, stesso comportamento", "Proponi e applica un refactor a piccoli passi nelle parti più confuse, senza cambiare il comportamento, con i test che lo dimostrano."],
];

/** @param {{api: any, toast: Function, errText: (e: any) => string, haptic?: Function}} deps */
export function createCodeStudio({ api, toast, errText, haptic = () => {} }) {
  const S = { ov: null, skill: null, busy: false, loaded: false };
  const header = el("div", { class: "cs-head" });
  const planBox = el("div");
  const skillsBox = el("div", { class: "cs-skills" });
  const log = el("div", { class: "cs-log", "aria-live": "polite" });
  const status = el("div", { class: "cs-status", role: "status" });
  const input = el("textarea", { rows: 1, placeholder: "Cosa costruiamo o correggiamo?", "aria-label": "Messaggio di coding", spellcheck: "false", autocapitalize: "off" });
  const sendBtn = el("button", { class: "cs-btn pri", "aria-label": "Invia", onclick: () => send() }, icon("send", 18));
  const root = el("div", { class: "cs" }, header, planBox, skillsBox, log, status, el("div", { class: "cs-comp" }, input, sendBtn));
  input.addEventListener("input", () => { input.style.height = "auto"; input.style.height = `${Math.min(input.scrollHeight, 160)}px`; });
  input.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing && matchMedia("(hover: hover)").matches) { e.preventDefault(); send(); } });

  const stick = () => log.scrollHeight - log.scrollTop - log.clientHeight < 80;
  const down = () => { log.scrollTop = log.scrollHeight; };

  function decorate(node) {  // pulsante «Copia» su ogni blocco di codice
    node.querySelectorAll("pre").forEach((pre) => {
      if (pre.querySelector(".cs-copy")) return;
      pre.prepend(el("button", { class: "cs-copy", onclick: () => navigator.clipboard?.writeText(pre.querySelector("code")?.textContent || "").then(() => toast("Codice copiato")).catch(() => toast("Copia non riuscita", true)) }, "Copia"));
    });
    return node;
  }
  function bubble(role, text) {
    const b = el("div", { class: `cs-msg ${role}` }, role === "bot" ? decorate(markdown(text)) : text);
    log.append(b);
    return b;
  }

  // ---------------------------------------------------------------- progetto, piano, competenze
  function drawHeader() {
    const ov = S.ov, ses = ov?.session;
    header.replaceChildren();
    if (!ov) return header.append(el("div", { class: "cs-status" }, "Carico lo spazio di lavoro…"));
    if (!ov.enabled) return header.append(el("div", { class: "cs-warn" }, "Il coding non è attivo: manca GITHUB_TOKEN sul server. Puoi comunque chiedere codice e revisioni a JARVIS, ma non creare repository."));
    const ch = ses?.changes, n = ch ? ch.modified.length + ch.new.length + ch.deleted.length : 0;
    header.append(el("div", { class: "cs-proj" },
      ses?.active
        ? el("div", { class: "grow" }, icon("code", 16), " ", el("b", {}, ses.repo.split("/")[1] || ses.repo), " ", el("small", {}, `${ses.branch}${ses.pr ? ` · PR #${ses.pr}` : ""} · ${ses.files} file`))
        : el("div", { class: "grow" }, icon("code", 16), " ", el("b", {}, "Nessun progetto aperto"), " ", el("small", {}, "creane uno o riprendine uno")),
      n ? el("span", { class: "cs-pill warn" }, `${n} modifiche`) : null,
      ses?.active ? el("button", { class: "cs-btn", onclick: openProject }, icon("file", 15), "Progetto") : el("button", { class: "cs-btn", onclick: pickRepo }, "Riprendi"),
      el("button", { class: "cs-btn pri", title: "Crea un nuovo repository privato su GitHub", onclick: createRepo }, icon("plus", 15), "Nuovo repo"),
      el("button", { class: "cs-btn", title: "Cancella la conversazione di coding (il progetto resta)", onclick: newChat }, icon("branch", 15), "Azzera chat")));
  }

  function drawPlan() {
    const plan = S.ov?.session?.plan || [];
    planBox.replaceChildren();
    if (!plan.length) return;
    const done = plan.filter((p) => p.done).length;
    planBox.append(el("details", { class: "cs-plan", open: done < plan.length && window.innerHeight > 760 }, el("summary", {}, icon("branch", 15), el("b", {}, "Piano"), ` ${done}/${plan.length}`, el("span", { class: "cs-bar" }, el("i", { style: `width:${Math.round(100 * done / plan.length)}%` }))),
      el("ol", {}, plan.map((p) => el("li", { class: p.done ? "done" : "" }, p.text)))));
  }

  function drawSkills() {
    const all = S.ov?.skills || [];
    skillsBox.replaceChildren();
    if (!all.length) return;
    const by = Object.fromEntries(all.map((s) => [s.name, s]));
    const feat = FEATURED.map((n) => by[n]).filter(Boolean);
    const chip = (s) => el("button", { class: `cs-chip${S.skill?.name === s.name ? " on" : ""}`, title: s.description, onclick: () => { S.skill = S.skill?.name === s.name ? null : s; haptic(); drawSkills(); } }, s.title);
    if (S.skill && !feat.includes(S.skill)) skillsBox.append(chip(S.skill));
    skillsBox.append(...feat.map(chip), el("button", { class: "cs-chip", onclick: pickSkill }, `Tutte (${all.length})`));
  }

  function sheet(title, ...body) {
    const close = () => bg.remove();
    const bg = el("div", { class: "cs-sheet-bg", onclick: (e) => e.target === bg && close() },
      el("div", { class: "cs-sheet", role: "dialog", "aria-label": title }, el("div", { class: "cs-proj" }, el("b", { class: "grow" }, title), el("button", { class: "cs-btn", onclick: close }, "Chiudi")), ...body));
    document.body.append(bg);
    return { close, root: bg.firstChild };
  }

  function pickSkill() {
    const all = S.ov?.skills || [];
    const q = el("input", { type: "search", placeholder: `Cerca tra ${all.length} competenze…`, "aria-label": "Cerca competenza", style: "padding:9px 12px;border-radius:12px;border:1px solid var(--line);background:var(--surf,var(--panel));color:var(--text)" });
    const list = el("div", { class: "cs-list cs-body" });
    const draw = () => {
      const t = q.value.trim().toLowerCase();
      list.replaceChildren(...all.filter((s) => !t || `${s.title} ${s.description} ${s.name}`.toLowerCase().includes(t)).slice(0, 80).map((s) =>
        el("button", { onclick: () => { S.skill = s; drawSkills(); sh.close(); toast(`Competenza attiva: ${s.title}`); } }, el("b", {}, s.title), el("br"), el("small", { style: "color:var(--muted)" }, s.description))));
    };
    const sh = sheet("Competenze di programmazione", q, list);
    q.addEventListener("input", draw);
    draw();
  }

  const TEMPLATES = [["", "Vuoto (solo README)"], ["python-cli", "Python · programma da terminale"], ["fastapi-api", "Python · API con FastAPI"], ["node-express-api", "Node.js · API con Express"],
    ["static-site", "Sito statico (HTML/CSS/JS)"], ["telegram-bot", "Bot di Telegram (Python)"]];
  const LICENSES = [["mit", "MIT (libera)"], ["apache", "Apache 2.0"], ["gpl", "GPL 3.0"], ["bsd", "BSD 3"], ["nessuna", "Nessuna (tutti i diritti riservati)"]];

  /** Nuovo repository PRIVATO su GitHub dalla sezione Codice: nome, descrizione, modello di partenza (con test e CI), licenza. */
  function createRepo() {
    if (!S.ov?.enabled) return toast("Il coding non è attivo sul server (manca GITHUB_TOKEN)", true);
    const field = (label, node) => el("label", { style: "display:flex;flex-direction:column;gap:4px;font-size:12.5px;color:var(--muted)" }, label, node);
    const style = "padding:9px 12px;border-radius:12px;border:1px solid var(--line);background:var(--surf,var(--panel));color:var(--text);font:inherit";
    const name = el("input", { type: "text", placeholder: "mio-progetto", maxlength: 60, autocapitalize: "off", autocomplete: "off", spellcheck: "false", "aria-label": "Nome del repository", style });
    const desc = el("input", { type: "text", placeholder: "A cosa serve (facoltativo)", maxlength: 300, "aria-label": "Descrizione", style });
    const tpl = el("select", { "aria-label": "Modello di partenza", style }, TEMPLATES.filter(([k]) => !k || !S.ov.templates || S.ov.templates.includes(k)).map(([v, l]) => el("option", { value: v }, l)));
    const lic = el("select", { "aria-label": "Licenza", style }, LICENSES.map(([v, l]) => el("option", { value: v }, l)));
    const readme = el("input", { type: "checkbox", checked: true, "aria-label": "Crea il README" });
    const note = el("div", { class: "cs-status" }, "Il repository sarà PRIVATO: lo vedi solo tu. JARVIS ci lavora in una sandbox e committa su un ramo.");
    const go = el("button", { class: "cs-btn pri", style: "justify-content:center;min-height:42px", onclick: async () => {
      const n = name.value.trim();
      if (!/^[A-Za-z0-9][A-Za-z0-9._-]{1,59}$/.test(n)) { note.textContent = "Nome non valido: lettere, numeri, punto, trattino e underscore (2-60 caratteri, niente spazi)."; note.style.color = "var(--bad)"; return; }
      go.disabled = true; note.style.color = ""; note.textContent = "Creo il repository su GitHub…";
      try {
        await api.codeCreate({ name: n, description: desc.value.trim(), readme: readme.checked, license: lic.value, scaffold: tpl.value });
        haptic("medium"); toast(`Repository «${n}» creato: la sandbox è pronta`); sh.close(); S.loaded = false; await refresh();
        send(tpl.value ? "Il repository è pronto con lo scheletro iniziale. Spiegami com'è fatto e proponi i prossimi passi." : "Il repository è pronto. Chiedimi cosa vuoi costruire: proponi un piano.");
      } catch (e) { go.disabled = false; note.textContent = errText(e); note.style.color = "var(--bad)"; }
    } }, icon("plus", 16), "Crea repository privato");
    const sh = sheet("Nuovo repository", field("Nome", name), field("Descrizione", desc), field("Modello di partenza (con test e CI)", tpl), field("Licenza", lic),
      el("label", { style: "display:flex;gap:8px;align-items:center;font-size:13.5px" }, readme, "Crea il README"), note, go);
    setTimeout(() => name.focus(), 200);
  }

  function pickRepo() {
    const repos = S.ov?.repos || [];
    if (!repos.length) return toast("Non ci sono ancora repository creati da JARVIS: chiedigli di crearne uno");
    const list = el("div", { class: "cs-list cs-body" }, repos.map((r) => el("button", { onclick: async () => {
      sh.close(); status.textContent = `Apro ${r}…`;
      try { await api.codeResume(r.split("/").pop()); haptic("medium"); toast("Progetto aperto"); } catch (e) { toast(errText(e), true); }
      status.textContent = ""; refresh();
    } }, icon("code", 14), " ", r)));
    const sh = sheet("Riprendi un progetto", list);
  }

  async function openProject() {
    const tabs = ["File", "Modifiche", "CI"];
    const body = el("div", { class: "cs-body" });
    const bar = el("div", { class: "cs-tabs" });
    let cur = 0;
    const draw = async () => {
      bar.replaceChildren(...tabs.map((t, i) => el("button", { class: `cs-btn${i === cur ? " on" : ""}`, onclick: () => { cur = i; draw(); } }, t)));
      body.replaceChildren(el("div", { class: "cs-status" }, "Carico…"));
      try {
        if (cur === 0) {
          const { files } = await api.codeFiles();
          const ch = S.ov?.session?.changes || { modified: [], new: [] };
          body.replaceChildren(el("div", { class: "cs-files" }, files.map((f) => el("button", { class: ch.new.includes(f) ? "new" : ch.modified.includes(f) ? "mod" : "", onclick: async () => {
            try { const r = await api.codeFile(f); body.replaceChildren(el("button", { class: "cs-btn", onclick: draw }, "← File"), el("pre", { class: "cs-code" }, r.text)); } catch (e) { toast(errText(e), true); }
          } }, f))));
        } else if (cur === 1) {
          const { diff, review } = await api.codeDiff();
          const pre = el("pre", { class: "cs-code" });
          diff.split("\n").forEach((ln) => pre.append(el("span", { class: ln.startsWith("+") && !ln.startsWith("+++") ? "add" : ln.startsWith("-") && !ln.startsWith("---") ? "del" : ln.startsWith("###") ? "hdr" : "" }, `${ln}\n`)));
          body.replaceChildren(el("pre", { class: "cs-code", style: "white-space:pre-wrap;margin-bottom:8px" }, review), pre);
        } else {
          const c = await api.codeChecks();
          body.replaceChildren(el("div", { class: "cs-list" }, el("div", { class: `cs-pill ${c.state === "success" ? "ok" : c.state === "failure" ? "bad" : "warn"}`, style: "align-self:flex-start" }, `CI: ${c.state}`),
            ...(c.runs || []).map((r) => el("div", { class: "cs-msg" }, `${r.name}: ${r.status} ${r.conclusion || ""}`)), !(c.runs || []).length ? el("div", { class: "cs-status" }, "Nessuna esecuzione.") : null));
        }
      } catch (e) { body.replaceChildren(el("div", { class: "cs-warn" }, errText(e))); }
    };
    sheet(S.ov?.session?.repo || "Progetto", bar, body);
    draw();
  }

  // ---------------------------------------------------------------- conversazione
  function drawEmpty() {
    log.replaceChildren(el("div", { class: "cs-quick" }, QUICK.map(([t, d, prompt]) => el("button", { onclick: () => { haptic(); if (prompt === "@create") createRepo(); else if (prompt) send(prompt); else pickRepo(); } }, el("b", {}, t), el("small", {}, d)))));
  }

  async function loadHistory() {
    try {
      const rows = await api.codeHistory(40);
      log.replaceChildren();
      if (!rows.length) { drawEmpty(); log.scrollTop = 0; return; }
      rows.forEach((r) => bubble(r.role === "user" ? "user" : "bot", r.content));
      down();
    } catch { drawEmpty(); }
  }

  let armed = 0;
  async function newChat(e) {
    if (S.busy) return toast("Aspetta che JARVIS finisca");
    const btn = e?.currentTarget, label = btn?.lastChild;
    if (Date.now() - armed > 4000) {  // conferma a due tocchi (le finestre di dialogo non sono affidabili nelle app)
      armed = Date.now();
      if (label) label.textContent = "Conferma";
      toast("Tocca di nuovo per cancellare la conversazione di coding: il progetto e il suo codice restano");
      setTimeout(() => { if (label) label.textContent = "Azzera chat"; }, 4000);
      return;
    }
    armed = 0;
    if (label) label.textContent = "Azzera chat";
    try { await api.codeNew(); S.loaded = false; drawEmpty(); haptic("medium"); } catch (e) { toast(errText(e), true); }
  }

  async function send(text) {
    const msg = (text ?? input.value).trim();
    if (!msg || S.busy) return;
    if (text === undefined) { input.value = ""; input.style.height = "auto"; }
    if (log.querySelector(".cs-quick")) log.replaceChildren();
    bubble("user", msg);
    S.busy = true; sendBtn.disabled = true; status.textContent = "JARVIS sta lavorando…";
    const skill = S.skill?.name || "";
    S.skill = null; drawSkills();
    let live = null;
    const tw = new Typewriter((text) => {
      if (!live) live = bubble("bot", "");
      const s = stick(); live.replaceChildren(decorate(markdown(text))); if (s) down();
    });
    try {
      const reply = await api.codeChatStream(msg, {
        skill,
        onStatus: (t) => { status.textContent = t; },
        onDelta: (t) => tw.push(t),
      });
      await tw.finish(reply);
      live?.remove(); bubble("bot", reply); haptic("light");
    } catch (e) { tw.stop(); live?.remove(); bubble("sys", errText(e)); }
    finally { S.busy = false; sendBtn.disabled = false; status.textContent = ""; down(); refresh(false); }
  }

  async function refresh(withHistory = !S.loaded) {
    try { S.ov = await api.codeOverview(); } catch (e) { if (!S.ov) { header.replaceChildren(el("div", { class: "cs-warn" }, errText(e))); } }
    drawHeader(); drawPlan(); drawSkills();
    if (withHistory) { S.loaded = true; await loadHistory(); }
  }

  /** Un altro dispositivo (o il server) ha lavorato nella sezione Codice: ci si rimette in pari senza disturbare uno scambio in corso. */
  function onSync() { if (!S.busy) refresh(true); }

  drawEmpty();
  return { root, refresh, onSync, focus: () => input.focus() };
}
