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

  async #req(path, { method = "GET", body, timeout = 30_000, auth = true, raw = false } = {}) {
    const headers = {};
    if (auth) headers.Authorization = `Bearer ${this.cfg.token()}`;
    if (body !== undefined) headers["Content-Type"] = "application/json";
    let res;
    try {
      res = await fetch(`${this.cfg.url()}${path}`, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
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
  async chatStream(message, session, { model = "", skill = "", onStatus = () => {}, onDelta = () => {}, signal } = {}) {
    let res;
    try {
      res = await fetch(`${this.cfg.url()}/chat/stream`, {
        method: "POST",
        headers: { Authorization: `Bearer ${this.cfg.token()}`, "Content-Type": "application/json", Accept: "text/event-stream" },
        body: JSON.stringify({ message, session_id: session, model: model || undefined, skill: skill || undefined }),
        signal,
      });
    } catch (e) {
      if (e.name === "AbortError") throw e;
      throw new ApiError(0, "Server non raggiungibile: si sta svegliando o manca la rete.");
    }
    if (res.status === 404) return this.chat(message, session);
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
  addReminder(text, when) { return this.#req("/api/reminders", { method: "POST", body: { text, when } }); }
  deleteReminder(id) { return this.#req(`/api/reminders/${id}`, { method: "DELETE" }); }
  pending() { return this.#get("/api/pending"); }
  decide(id, approve) { return this.#req(`/api/pending/${encodeURIComponent(id)}/${approve ? "approve" : "reject"}`, { method: "POST" }); }
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
