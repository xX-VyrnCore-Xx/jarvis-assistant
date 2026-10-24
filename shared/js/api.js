// Client dell'API di JARVIS, condiviso da app Windows e Android.

export class ApiError extends Error {
  constructor(status, message, retryAfter) {
    super(message);
    this.status = status;
    this.retryAfter = retryAfter ? Number(retryAfter) : 0;
  }
}

const HUMAN = {
  401: "Token non valido: controllalo nelle impostazioni.",
  404: "Funzione non disponibile su questo server.",
  413: "Richiesta troppo grande.",
  422: "Dati non validi.",
  429: "Troppe richieste.",
  502: "L'intelligenza artificiale non ha risposto.",
  503: "Il server si sta avviando, riprova tra qualche secondo.",
  504: "Il server non ha risposto in tempo.",
};

/** Id casuale di questo dispositivo: il server lo restituisce negli avvisi di sincronizzazione, così non ricarica ciò che ha appena fatto lui. */
export const deviceId = (() => {
  try {
    let id = localStorage.getItem("jarvis.device");
    if (!id) { id = Math.random().toString(36).slice(2, 12); localStorage.setItem("jarvis.device", id); }
    return id;
  } catch { return Math.random().toString(36).slice(2, 12); }
})();

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const TRANSIENT = new Set([0, 502, 503, 504]);

export class Jarvis {
  /** @param {{url: () => string, token: () => string}} cfg */
  constructor(cfg) {
    this.cfg = cfg;
    this.inflight = new Map(); // letture identiche in corso: una sola richiesta, risposta condivisa
  }

  /** Le letture (GET) riprovano da sole se il server si sta svegliando (Render Free: 30-60 s) e si fondono se identiche. */
  #get(path, opts = {}) {
    const key = `${this.cfg.url()}${path}`;
    if (this.inflight.has(key)) return this.inflight.get(key);
    const run = (async () => {
      for (let attempt = 0; ; attempt++) {
        try { return await this.#req(path, opts); } catch (e) {
          if (!(e instanceof ApiError) || !TRANSIENT.has(e.status) || attempt >= 2) throw e;
          await sleep(2500 * (attempt + 1));
        }
      }
    })().finally(() => this.inflight.delete(key));
    this.inflight.set(key, run);
    return run;
  }

  async #req(path, { method = "GET", body, timeout = 30_000, auth = true, raw = false, binary = "" } = {}) {
    const headers = { "X-Device-Id": deviceId };
    if (auth) headers.Authorization = `Bearer ${this.cfg.token()}`;
    if (body !== undefined) headers["Content-Type"] = binary || "application/json";
    let res;
    try {
      res = await fetch(`${this.cfg.url()}${path}`, {
        method,
        headers,
        body: body === undefined ? undefined : binary ? body : JSON.stringify(body),
        signal: AbortSignal.timeout(timeout),
      });
    } catch (e) {
      throw new ApiError(0, e.name === "TimeoutError" ? "Il server non ha risposto in tempo." : "Server non raggiungibile: si sta svegliando o manca la rete.");
    }
    if (!res.ok) {
      let detail = "";
      try { detail = (await res.json()).detail || ""; } catch { /* corpo non JSON */ }
      const wait = res.headers.get("retry-after");
      let msg = typeof detail === "string" && detail ? detail : HUMAN[res.status] || `Errore del server (${res.status}).`;
      if (res.status === 429 && wait) msg = `Troppe richieste: riprova tra ${wait} s.`;
      throw new ApiError(res.status, msg, wait);
    }
    return raw ? res.blob() : res.json();
  }

  health() { return this.#req("/health", { auth: false, timeout: 70_000 }); }
  chat(message, session) { return this.#req("/chat", { method: "POST", body: { message, session_id: session }, timeout: 120_000 }).then((r) => r.reply); }
  /** Risposta in streaming: onStatus(testo) durante i tool, onDelta(testo) mentre scrive. Restituisce la risposta intera. Se il server è vecchio ripiega su /chat. */
  async chatStream(message, session, { path = "/chat/stream", model = "", skill = "", voice = false, onStatus = () => {}, onDelta = () => {}, signal } = {}) {
    let res;
    try {
      res = await fetch(`${this.cfg.url()}${path}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${this.cfg.token()}`, "Content-Type": "application/json", Accept: "text/event-stream", "X-Device-Id": deviceId },
        body: JSON.stringify({ message, session_id: session, model: model || undefined, skill: skill || undefined, voice: voice || undefined }),
        signal,
      });
    } catch (e) {
      if (e.name === "AbortError") throw e;
      throw new ApiError(0, "Server non raggiungibile: si sta svegliando o manca la rete.");
    }
    if (res.status === 404 && path === "/chat/stream") return this.chat(message, session);
    if (!res.ok || !res.body) {
      let detail = "";
      try { detail = (await res.json()).detail || ""; } catch { /* non JSON */ }
      throw new ApiError(res.status, (typeof detail === "string" && detail) || HUMAN[res.status] || `Errore del server (${res.status}).`, res.headers.get("retry-after"));
    }
    const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
    let buf = "", final = "", streamed = "";
    const handle = (block) => {
      let ev = "message", data = "";
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) ev = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (!data) return;
      let text = "";
      try { text = JSON.parse(data).text || ""; } catch { return; }
      if (ev === "status") onStatus(text);
      else if (ev === "delta") { streamed += text; onDelta(text); }
      else if (ev === "done") final = text;
      else if (ev === "error") throw new ApiError(502, text || "Errore del server.");
    };
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += value;
      let i;
      while ((i = buf.indexOf("\n\n")) >= 0) { handle(buf.slice(0, i)); buf = buf.slice(i + 2); }
    }
    return final || streamed;
  }
  /** Chat della sezione Codice (conversazione a parte, prompt da ingegnere, competenze e strumenti di programmazione). */
  codeChatStream(message, opts = {}) { return this.chatStream(message, "code", { ...opts, path: "/code/chat/stream" }); }
  codeOverview() { return this.#req("/api/code/overview", { timeout: 30_000 }); }
  codeHistory(limit = 40) { return this.#get(`/api/code/history?limit=${limit}`); }
  codeNew() { return this.#req("/api/code/new", { method: "POST" }); }
  codeFiles() { return this.#req("/api/code/files"); }
  codeFile(path, start = 1) { return this.#req(`/api/code/file?path=${encodeURIComponent(path)}&start=${start}`); }
  codeDiff() { return this.#req("/api/code/diff", { timeout: 30_000 }); }
  codeChecks() { return this.#req("/api/code/checks", { timeout: 30_000 }); }
  codeCreate(p) { return this.#req("/api/code/create", { method: "POST", body: p, timeout: 120_000 }); }
  codeExec(command) { return this.#req("/api/code/exec", { method: "POST", body: { command }, timeout: 150_000 }); }
  codeCommands() { return this.#get("/api/code/commands"); }
  codeJobs() { return this.#req("/api/code/jobs"); }
  codeJob(id) { return this.#req(`/api/code/jobs/${encodeURIComponent(id)}`); }
  codeJobStart(task, repo = "") { return this.#req("/api/code/jobs", { method: "POST", body: { task, repo }, timeout: 30_000 }); }
  codeJobCancel(id) { return this.#req(`/api/code/jobs/${encodeURIComponent(id)}/cancel`, { method: "POST" }); }
  codeResume(repo) { return this.#req("/api/code/resume", { method: "POST", body: { repo }, timeout: 90_000 }); }
  /** Dettatura di qualità: manda l'audio registrato e riceve il testo (Whisper del router), già corretto se `fix` è quick/full. */
  stt(blob, fix = "quick") { return this.#req(`/api/stt?fix=${fix}`, { method: "POST", body: blob, binary: (blob.type || "audio/webm").split(";")[0], timeout: 60_000 }); }
  /** Correttore grammaticale italiano: quick = regole istantanee, full = regole + modello. */
  correct(text, level = "full") { return this.#req("/api/correct", { method: "POST", body: { text, level }, timeout: 45_000 }); }
  status() { return this.#get("/api/status"); }
  models() { return this.#get("/api/models"); }
  skills() { return this.#get("/api/skills"); }
  skill(name) { return this.#get(`/api/skills/${encodeURIComponent(name)}`); }
  usage(days = 14) { return this.#get(`/api/usage?days=${days}`); }
  serverHealth() { return this.#get("/api/health"); }
  appUpdate(platform, version) { return this.#req(`/api/app/update?platform=${platform}&version=${encodeURIComponent(version)}`, { timeout: 20_000 }); }
  notifyPrefs() { return this.#get("/api/notify/prefs"); }
  setNotifyPrefs(patch) { return this.#req("/api/notify/prefs", { method: "POST", body: patch }); }
  snooze(id, minutes) { return this.#req(`/api/notifications/${id}/snooze`, { method: "POST", body: { minutes } }); }
  clearNotifications() { return this.#req("/api/notifications?read_only=true", { method: "DELETE" }); }
  tokens(refresh = false) { return this.#get(`/api/tokens${refresh ? "?refresh=true" : ""}`); }
  history(session, limit = 40) { return this.#get(`/api/history?session_id=${encodeURIComponent(session)}&limit=${limit}`); }
  reminders() { return this.#get("/api/reminders"); }
  /** Allinea i promemoria con il Calendario Google ora; risponde sempre con l'esito (e la causa, se è andata male). */
  syncReminders() { return this.#req("/api/reminders/sync", { method: "POST", timeout: 60_000 }); }
  addReminder(text, when, repeat = "") { return this.#req("/api/reminders", { method: "POST", body: { text, when, repeat } }); }
  /** Esegue subito il backup su Hugging Face: risponde con l'esito e, se fallisce, il motivo. */
  /** Risposta dell'app a un ordine del server (es. ricerca in rubrica): arriva solo a chi la stava aspettando. */
  phoneResult(id, ok, data = null, error = "") { return this.#req("/api/phone/result", { method: "POST", body: { id, ok, data, error } }); }
  callsConfig() { return this.#req("/api/calls/config"); }
  setCallsConfig(mode, numbers, greeting = "") { return this.#req("/api/calls/config", { method: "POST", body: { mode, numbers, greeting } }); }
  runBackup() { return this.#req("/api/backup/run", { method: "POST", timeout: 150_000 }); }
  /** Cancella la conversazione corrente (di tutti i dispositivi e di Telegram) e ne inizia una nuova. */
  newChat() { return this.#req("/api/chat/new", { method: "POST" }); }
  contactsAccess() { return this.#req("/api/contacts/access"); }
  setContactsAccess(enabled) { return this.#req("/api/contacts/access", { method: "POST", body: { enabled } }); }
  privacy() { return this.#req("/api/privacy"); }
  setNeuralVoice(neural_voice) { return this.#req("/api/privacy/neural-voice", { method: "POST", body: { neural_voice } }); }
  /** «Cancella chat e cache»: conversazioni (normale e Codice), notifiche, cache e audio in memoria. Ricordi, cervello, promemoria e attività restano. */
  wipe() { return this.#req("/api/privacy/wipe", { method: "POST" }); }
  tasks() { return this.#get("/api/tasks"); }
  addTask(text, list = "attività") { return this.#req("/api/tasks", { method: "POST", body: { text, list } }); }
  setTaskDone(id, done) { return this.#req(`/api/tasks/${id}`, { method: "PATCH", body: { done } }); }
  deleteTask(id) { return this.#req(`/api/tasks/${id}`, { method: "DELETE" }); }
  deleteReminder(id) { return this.#req(`/api/reminders/${id}`, { method: "DELETE" }); }
  pending() { return this.#get("/api/pending"); }
  decide(id, approve) { return this.#req(`/api/pending/${encodeURIComponent(id)}/${approve ? "approve" : "reject"}`, { method: "POST" }); }
  voiceConfig() { return this.#req("/api/voice"); }
  setVoice(voice) { return this.#req("/api/voice", { method: "POST", body: { voice } }); }
  toolsHealth() { return this.#req("/api/tools/health"); }
  checkTools() { return this.#req("/api/tools/health", { method: "POST", timeout: 130_000 }); }
  tts(text) { return this.#req("/api/tts", { method: "POST", body: { text }, timeout: 150_000, raw: true }); }
  notifications(limit = 50) { return this.#get(`/api/notifications?limit=${limit}`); }
  markRead(ids = null) { return this.#req("/api/notifications/read", { method: "POST", body: { ids } }); }
  testNotification() { return this.#req("/api/notifications/test", { method: "POST" }); }
  registerDevice(platform, token, label = "") { return this.#req("/api/devices", { method: "POST", body: { platform, token, label } }); }
  unregisterDevice(token) { return this.#req(`/api/devices?token=${encodeURIComponent(token)}`, { method: "DELETE" }); }
  brainSearch(q, k = 8) { return this.#get(`/api/brain/search?q=${encodeURIComponent(q)}&k=${k}`); }
  brainDocs(limit = 30, source = "") { return this.#get(`/api/brain/docs?limit=${limit}${source ? `&source=${source}` : ""}`); }
  brainDoc(id) { return this.#get(`/api/brain/docs/${id}`); }
  brainStats() { return this.#get("/api/brain/stats"); }
  brainAddNote(text, title = "", tags = [], important = false) { return this.#req("/api/brain/notes", { method: "POST", body: { text, title, tags, important }, timeout: 90_000 }); }
  brainAddUrl(url, tags = []) { return this.#req("/api/brain/url", { method: "POST", body: { url, tags }, timeout: 90_000 }); }
  brainPin(id, pinned) { return this.#req(`/api/brain/docs/${id}/pin`, { method: "POST", body: { pinned } }); }
  brainDelete(id) { return this.#req(`/api/brain/docs/${id}`, { method: "DELETE" }); }
}
