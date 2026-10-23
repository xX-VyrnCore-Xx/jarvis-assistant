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
  const S = { ov: null, skill: null, busy: false, loaded: false, bg: false, jobs: [], jobsSeen: null, cmds: null };
  const header = el("div", { class: "cs-head" });
  const planBox = el("div");
  const skillsBox = el("div", { class: "cs-skills" });
  const jobsBox = el("div", { class: "cs-jobsbar" });
  const palette = el("div", { class: "cs-palette", hidden: true, role: "listbox", "aria-label": "Comandi" });
  const log = el("div", { class: "cs-log", "aria-live": "polite" });
  const status = el("div", { class: "cs-status", role: "status" });
  const input = el("textarea", { rows: 1, placeholder: "Cosa costruiamo o correggiamo?", "aria-label": "Messaggio di coding", spellcheck: "false", autocapitalize: "off" });
  const sendBtn = el("button", { class: "cs-btn pri", "aria-label": "Invia", onclick: () => send() }, icon("send", 18));
  const bgBtn = el("button", { class: "cs-btn cs-bg", "aria-label": "Esegui in background", title: "In background: JARVIS lavora da solo sul server, anche con l'app chiusa, e ti avvisa quando finisce", "aria-pressed": "false",
    onclick: () => { S.bg = !S.bg; haptic(); drawBg(); toast(S.bg ? "In background: lavora anche ad app chiusa e ti avviso a fine lavoro" : "Risposta qui, in diretta"); } }, icon("cloud", 18));
  const root = el("div", { class: "cs" }, header, planBox, skillsBox, jobsBox, log, status, palette, el("div", { class: "cs-comp" }, bgBtn, input, sendBtn));
  function drawBg() { bgBtn.classList.toggle("on", S.bg); bgBtn.setAttribute("aria-pressed", String(S.bg)); input.placeholder = S.bg ? "Cosa faccio in background?" : "Cosa costruiamo? («/» comandi)"; }
  input.addEventListener("input", () => { input.style.height = "auto"; input.style.height = `${Math.min(input.scrollHeight, 160)}px`; drawPalette(); });
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
      el("button", { class: "cs-btn", title: "Lavori in background", onclick: openJobs }, icon("cloud", 15), "Lavori", S.jobs.some(activeJob) ? el("span", { class: "cs-count" }, String(S.jobs.filter(activeJob).length)) : null),
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


  // ---------------------------------------------------------------- comandi rapidi («/»)
  const LOCAL_HELP = "Comandi: scrivi «/» per l'elenco. «/bg …» o l'icona nuvola lavorano in background e ti avvisano a fine lavoro.";
  async function loadCmds() {
    if (S.cmds) return S.cmds;
    try { S.cmds = await api.codeCommands(); } catch { S.cmds = []; }
    return S.cmds;
  }
  function drawPalette() {
    const v = input.value;
    if (!v.startsWith("/") || /\s/.test(v)) { palette.hidden = true; return; }
    loadCmds().then((cmds) => {
      if (!input.value.startsWith("/") || /\s/.test(input.value)) return;
      const q = input.value.slice(1).toLowerCase();
      const rows = cmds.filter((c) => c.name.startsWith(q)).slice(0, 8);
      palette.replaceChildren(...rows.map((c) => el("button", { role: "option", onclick: () => { haptic(); if (c.args) { input.value = `/${c.name} `; input.focus(); drawPalette(); } else { input.value = ""; send(`/${c.name}`); } } },
        el("b", {}, `/${c.name}`), el("small", {}, c.desc))));
      palette.hidden = !rows.length;
    });
  }
  /** «/review app.py» → il prompt completo del comando; null se non è un comando (o è locale). */
  async function expand(text) {
    const m = /^\/([a-z-]+)(?:\s+([\s\S]*))?$/i.exec(text);
    if (!m) return null;
    const name = m[1].toLowerCase(), args = (m[2] || "").trim();
    const cmds = await loadCmds();
    const c = cmds.find((x) => x.name === name);
    if (!c) return { error: `Comando «/${name}» sconosciuto. ${LOCAL_HELP}` };
    if (c.local) return { local: name, args };
    let bg = false, a = args;
    if (/(^|\s)(bg|background)$/i.test(a)) { bg = true; a = a.replace(/\s*(bg|background)$/i, "").trim(); }
    const filled = c.prompt.replaceAll("{args}", a ? ` ${a}` : "");
    return { prompt: (a ? filled : filled.replace(/\s+([.,:;])/g, "$1").replace(/:\s*$/, ".")).trim(), bg };
  }

  // ---------------------------------------------------------------- lavori in background
  const activeJob = (j) => j.status === "queued" || j.status === "running";
  const JOB_LABEL = { queued: "In coda", running: "In corso", done: "Finito", failed: "Non riuscito", cancelled: "Annullato", interrupted: "Interrotto" };
  const ago = (t) => { const m = Math.max(0, Math.round((Date.now() / 1000 - t) / 60)); return m < 1 ? "ora" : m < 60 ? `${m} min fa` : m < 1440 ? `${Math.round(m / 60)} h fa` : `${Math.round(m / 1440)} g fa`; };
  let jobsTimer = 0, jobsSheet = null;

  async function refreshJobs() {
    try {
      const r = await api.codeJobs();
      const prev = S.jobsSeen;
      S.jobs = r.jobs || [];
      if (prev) for (const j of S.jobs) if (prev[j.id] && activeJob({ status: prev[j.id] }) && !activeJob(j)) toast(j.status === "done" ? `Lavoro finito: ${j.title}` : `Lavoro ${JOB_LABEL[j.status].toLowerCase()}: ${j.title}`, j.status === "failed");
      S.jobsSeen = Object.fromEntries(S.jobs.map((j) => [j.id, j.status]));
    } catch { return; }
    drawJobs();
    clearInterval(jobsTimer);
    jobsTimer = S.jobs.some(activeJob) ? setInterval(() => (root.isConnected ? refreshJobs() : clearInterval(jobsTimer)), 6000) : 0;  // rete di sicurezza se un avviso in tempo reale si perde
  }
  function drawJobs() {
    const act = S.jobs.filter(activeJob);
    jobsBox.replaceChildren();
    if (act.length) {
      const j = act.find((x) => x.status === "running") || act[0];
      jobsBox.append(el("button", { class: "cs-job-now", onclick: openJobs }, el("span", { class: "cs-spin" }, icon("refresh", 15)),
        el("span", { class: "grow" }, el("b", {}, j.title), el("small", {}, j.status === "queued" ? "In coda…" : j.now || "Lavoro…")), act.length > 1 ? el("span", { class: "cs-pill" }, `+${act.length - 1}`) : null));
    }
    drawHeader();
    if (jobsSheet?.isConnected) fillJobs();
  }
  async function startJob(task, shown) {
    if (log.querySelector(".cs-quick")) log.replaceChildren();
    bubble("user", shown || task);
    try {
      const j = await api.codeJobStart(task, "");
      haptic("medium");
      bubble("sys", "☁ In background: continuo da solo sul server, anche con l'app chiusa. Ti avviso quando ho finito.");
      toast("Lavoro avviato in background");
      S.jobs = [j, ...S.jobs.filter((x) => x.id !== j.id)]; drawJobs(); refreshJobs();
    } catch (e) { bubble("sys", errText(e)); }
    down();
  }
  function jobRow(j) {
    return el("button", { class: `cs-job ${j.status}`, onclick: () => openJob(j.id) },
      el("span", { class: "dot" }), el("span", { class: "grow" }, el("b", {}, j.title), el("small", {}, `${JOB_LABEL[j.status] || j.status} · ${ago(j.created)}${j.status === "running" && j.now ? ` · ${j.now}` : ""}`)),
      j.pr ? el("span", { class: "cs-pill ok" }, `PR #${j.pr}`) : null);
  }
  let jobsList = null;
  function fillJobs() {
    jobsList.replaceChildren(...(S.jobs.length ? S.jobs.map(jobRow) : [el("div", { class: "cs-status" }, "Nessun lavoro. Attiva la nuvola accanto al messaggio, oppure scrivi «/bg» seguito da cosa fare.")]));
  }
  function openJobs() {
    jobsList = el("div", { class: "cs-list cs-body" });
    const sh = sheet("Lavori in background", el("div", { class: "cs-status" }, "JARVIS lavora sul server anche con l'app chiusa e ti avvisa a fine lavoro (notifica, push, Telegram)."), jobsList);
    jobsSheet = sh.root; fillJobs(); refreshJobs();
  }
  async function openJob(id) {
    let j;
    try { j = await api.codeJob(id); } catch (e) { return toast(errText(e), true); }
    const body = el("div", { class: "cs-body" });
    const draw = (j) => {
      const link = j.pr && j.repo ? el("a", { class: "cs-btn", href: `https://github.com/${j.repo}/pull/${j.pr}`, target: "_blank", rel: "noopener" }, "Apri PR") : null;
      body.replaceChildren(
        el("div", { class: "cs-proj" }, el("span", { class: `cs-pill ${j.status === "done" ? "ok" : j.status === "failed" || j.status === "interrupted" ? "bad" : "warn"}` }, JOB_LABEL[j.status] || j.status), el("small", {}, `${j.repo || ""} · ${ago(j.created)}`),
          activeJob(j) ? el("button", { class: "cs-btn", onclick: async () => { try { await api.codeJobCancel(j.id); toast("Lavoro annullato"); sh.close(); refreshJobs(); } catch (e) { toast(errText(e), true); } } }, "Annulla")
            : el("button", { class: "cs-btn", onclick: async () => { try { await api.codeJobStart(j.prompt || j.title); toast("Rilanciato in background"); sh.close(); refreshJobs(); } catch (e) { toast(errText(e), true); } } }, "Rilancia"), link),
        el("div", { class: "cs-msg user" }, j.prompt || j.title),
        j.steps?.length ? el("ol", { class: "cs-steps" }, j.steps.map((t) => el("li", {}, t))) : null,
        j.result ? el("div", { class: "cs-msg" }, decorate(markdown(j.result))) : el("div", { class: "cs-status" }, "In attesa del risultato…"));
    };
    const sh = sheet(j.title, body);
    draw(j);
    if (activeJob(j)) {
      const t = setInterval(async () => { if (!body.isConnected) return clearInterval(t); try { draw(await api.codeJob(id)); } catch { /* si riprova */ } }, 4000);
    }
  }

  /** Avviso leggero dal server: un lavoro in background ha fatto un passo o è finito. */
  function onJobs() { refreshJobs(); }

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
    let msg = (text ?? input.value).trim();
    if (!msg || S.busy) return;
    if (text === undefined) { input.value = ""; input.style.height = "auto"; palette.hidden = true; }
    const shown = msg;
    let bg = S.bg;
    if (msg.startsWith("/")) {
      const x = await expand(msg);
      if (x?.error) { if (log.querySelector(".cs-quick")) log.replaceChildren(); bubble("user", shown); bubble("sys", x.error); return down(); }
      if (x?.local) {
        if (x.local === "jobs") return openJobs();
        if (x.local === "new") return newChat();
        if (x.local === "help") { const cmds = await loadCmds(); return sheet("Comandi", el("div", { class: "cs-list cs-body" }, cmds.map((c) => el("div", { class: "cs-cmd" }, el("b", {}, `/${c.name}`), el("small", {}, c.desc))))); }
        if (!x.args) { toast("Scrivi cosa deve fare: «/bg aggiungi i test al parser»"); input.value = "/bg "; input.focus(); return; }
        msg = x.args; bg = true;
      } else if (x) { msg = x.prompt; bg = bg || x.bg; }
    }
    if (bg) return startJob(msg, shown);
    if (log.querySelector(".cs-quick")) log.replaceChildren();
    bubble("user", shown);
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
    drawHeader(); drawPlan(); drawSkills(); refreshJobs();
    if (withHistory) { S.loaded = true; await loadHistory(); }
  }

  /** Un altro dispositivo (o il server) ha lavorato nella sezione Codice: ci si rimette in pari senza disturbare uno scambio in corso. */
  function onSync() { if (!S.busy) refresh(true); }

  drawEmpty(); drawBg();
  return { root, refresh, onSync, onJobs, focus: () => input.focus() };
}
