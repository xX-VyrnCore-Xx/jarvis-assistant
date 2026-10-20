// Notifiche in tempo reale: flusso SSE dal server, con riconnessione automatica.
// Si usa fetch (non EventSource) perché serve l'intestazione Authorization.

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/**
 * @param {{url: () => string, token: () => string}} cfg
 * @param {{onNotification: (n: object) => void, onState?: (s: "on"|"off"|"auth") => void}} h
 * @returns {() => void} funzione che chiude il flusso
 */
export function openStream(cfg, { onNotification, onRead = () => {}, onState = () => {} }) {
  let stopped = false;
  let ctrl;
  let retry = 0;

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
    } catch { /* messaggio malformato: ignorato */ }
  };

  (async () => {
    while (!stopped) {
      ctrl = new AbortController();
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
          buf += value;
          let i;
          while ((i = buf.indexOf("\n\n")) >= 0) { dispatch(buf.slice(0, i)); buf = buf.slice(i + 2); }
        }
      } catch { /* rete assente o server in avvio: si riprova */ }
      if (stopped) return;
      onState("off");
      await sleep(Math.min(30_000, 1000 * 2 ** retry++));
    }
  })();

  return () => { stopped = true; ctrl?.abort(); };
}
