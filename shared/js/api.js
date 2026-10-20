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
  status() { return this.#get("/api/status"); }
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
