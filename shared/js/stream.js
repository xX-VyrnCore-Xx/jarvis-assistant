// Notifiche in tempo reale: flusso SSE dal server, con riconnessione automatica.
// Si usa fetch (non EventSource) perché serve l'intestazione Authorization.
// Il server manda un battito ogni 20 s: se per 55 s non arriva nulla la connessione è morta in silenzio (succede sulle reti mobili) e si riapre da sola.

const IDLE_MS = 55_000;

/**
 * @param {{url: () => string, token: () => string}} cfg
 * @param {{onNotification: (n: object) => void, onSync?: (m: {scope: string, origin: string}) => void, onState?: (s: "on"|"connecting"|"off"|"auth") => void}} h
 * @returns {(() => void) & {poke: () => void}} chiude il flusso; `.poke()` riprova subito (al ritorno della rete)
 */
export function openStream(cfg, { onNotification, onRead = () => {}, onSync = () => {}, onState = () => {} }) {
  let stopped = false;
  let ctrl;
  let retry = 0;
  let last = 0;
  let wake = null; // interrompe l'attesa tra un tentativo e l'altro

  const dispatch = (block) => {
    let event = "message";
    let data = "";
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data += line.slice(5).trim();
    }
    if (!data) return;
    try {
      const msg = JSON.parse(data);
      if (event === "notification") onNotification(msg);
      else if (event === "read") onRead(msg.ids);
      else if (event === "sync") onSync(msg);
    } catch { /* messaggio malformato: ignorato */ }
  };

  const pause = (ms) => new Promise((resolve) => { const t = setTimeout(resolve, ms); wake = () => { clearTimeout(t); resolve(); }; });
  const watchdog = setInterval(() => { if (ctrl && last && Date.now() - last > IDLE_MS) ctrl.abort(); }, 10_000);

  (async () => {
    while (!stopped) {
      ctrl = new AbortController();
      last = Date.now();
      onState("connecting");
      try {
        const res = await fetch(`${cfg.url()}/api/stream`, { headers: { Authorization: `Bearer ${cfg.token()}` }, signal: ctrl.signal });
        if (res.status === 401) return onState("auth");
        if (!res.ok || !res.body) throw new Error(String(res.status));
        onState("on");
        retry = 0;
        const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
        let buf = "";
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          last = Date.now();
          buf += value;
          let i;
          while ((i = buf.indexOf("\n\n")) >= 0) { dispatch(buf.slice(0, i)); buf = buf.slice(i + 2); }
        }
      } catch { /* rete assente, server in avvio o battito mancato: si riprova */ }
      last = 0;
      if (stopped) return;
      onState("off");
      await pause(Math.min(30_000, 1000 * 2 ** retry++) * (0.75 + Math.random() * 0.5)); // piccola variazione: tanti dispositivi non si ripresentano tutti insieme
    }
  })();

  const close = () => { stopped = true; clearInterval(watchdog); ctrl?.abort(); wake?.(); };
  close.poke = () => { retry = 0; if (!ctrl || ctrl.signal.aborted || !last) wake?.(); };
  return close;
}
