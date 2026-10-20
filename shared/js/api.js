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

export class Jarvis {
  /** @param {{url: () => string, token: () => string}} cfg */
  constructor(cfg) {
    this.cfg = cfg;
  }

  async #req(path, { method = "GET", body, timeout = 30_000, auth = true } = {}) {
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
    return res.json();
  }

  health() { return this.#req("/health", { auth: false, timeout: 70_000 }); }
  chat(message, session) { return this.#req("/chat", { method: "POST", body: { message, session_id: session }, timeout: 120_000 }).then((r) => r.reply); }
  status() { return this.#req("/api/status"); }
  tokens(refresh = false) { return this.#req(`/api/tokens${refresh ? "?refresh=true" : ""}`); }
  history(session, limit = 40) { return this.#req(`/api/history?session_id=${encodeURIComponent(session)}&limit=${limit}`); }
  reminders() { return this.#req("/api/reminders"); }
  addReminder(text, when) { return this.#req("/api/reminders", { method: "POST", body: { text, when } }); }
  deleteReminder(id) { return this.#req(`/api/reminders/${id}`, { method: "DELETE" }); }
  pending() { return this.#req("/api/pending"); }
  decide(id, approve) { return this.#req(`/api/pending/${encodeURIComponent(id)}/${approve ? "approve" : "reject"}`, { method: "POST" }); }
}
