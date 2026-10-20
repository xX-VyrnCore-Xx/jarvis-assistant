import { invoke } from "@tauri-apps/api/core";

const $ = (id) => document.getElementById(id);
const log = $("log");
const SENSITIVE = {
  pc_move: (a) => `Spostare/rinominare "${a.src}" in "${a.dst}"?`,
  pc_power: (a) => `Eseguire "${a.mode}" del PC (tra 30 secondi)?`,
};

const cfg = {
  get url() { return (localStorage.getItem("jarvis.url") || "").replace(/\/+$/, ""); },
  get token() { return localStorage.getItem("jarvis.token") || ""; },
  set(url, token) { localStorage.setItem("jarvis.url", url.trim()); localStorage.setItem("jarvis.token", token.trim()); },
};

function add(kind, text) {
  const el = document.createElement("div");
  el.className = `msg ${kind}`;
  el.textContent = text; // mai innerHTML: il testo arriva da un LLM
  log.append(el);
  log.scrollTop = log.scrollHeight;
  return el;
}

async function ask(message) {
  const r = await fetch(`${cfg.url}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${cfg.token}` },
    body: JSON.stringify({ message, session_id: "desktop" }),
    signal: AbortSignal.timeout(120_000), // include il risveglio del piano Render Free
  });
  if (r.status === 401) throw new Error("Token non valido: controlla le impostazioni.");
  if (!r.ok) throw new Error(`Errore del server (${r.status}).`);
  return (await r.json()).reply;
}

$("composer").addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = $("input").value.trim();
  if (!text) return;
  if (!cfg.url || !cfg.token) return $("settings").showModal();
  $("input").value = "";
  add("user", text);
  const wait = add("sys", "JARVIS sta pensando…");
  try {
    add("bot", await ask(text));
  } catch (err) {
    add("sys", err.name === "TimeoutError" ? "Il server non ha risposto in tempo." : err.message);
  }
  wait.remove();
});

// ---- impostazioni
$("btn-settings").addEventListener("click", () => {
  $("cfg-url").value = cfg.url;
  $("cfg-token").value = cfg.token;
  $("settings").showModal();
});
$("settings").addEventListener("close", () => {
  if ($("settings").returnValue === "ok") {
    cfg.set($("cfg-url").value, $("cfg-token").value);
    connect();
  }
});

// ---- conferma azioni sensibili
function confirmAction(text) {
  return new Promise((resolve) => {
    $("confirm-text").textContent = text;
    $("confirm").addEventListener("close", () => resolve($("confirm").returnValue === "yes"), { once: true });
    $("confirm").showModal();
    invoke("show_window").catch(() => {});
  });
}

// ---- canale WebSocket col server (comandi sul PC + notifiche)
let ws, retry = 0, ping;
function connect() {
  clearInterval(ping);
  ws?.close();
  if (!cfg.url || !cfg.token) return;
  ws = new WebSocket(cfg.url.replace(/^http/, "ws") + "/ws/pc");
  ws.onopen = () => ws.send(JSON.stringify({ token: cfg.token }));
  ws.onmessage = async (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "ready") {
      retry = 0;
      $("dot").classList.add("on");
      ping = setInterval(() => ws.readyState === 1 && ws.send('{"type":"ping"}'), 25_000);
    } else if (msg.type === "notify") {
      add("bot", msg.text);
      invoke("notify", { title: "JARVIS", body: msg.text }).catch(() => {});
    } else if (msg.type === "command") {
      ws.send(JSON.stringify({ type: "result", id: msg.id, output: await runCommand(msg.action, msg.args || {}) }));
    }
  };
  ws.onclose = () => {
    clearInterval(ping);
    $("dot").classList.remove("on");
    setTimeout(connect, Math.min(30_000, 1000 * 2 ** retry++));
  };
}

async function runCommand(action, args) {
  const describe = SENSITIVE[action];
  if (describe && !(await confirmAction(describe(args)))) return "Azione rifiutata dall'utente.";
  try {
    return await invoke("run_action", { action, args });
  } catch (e) {
    return `Errore: ${e}`;
  }
}

add("sys", cfg.url ? "Pronto, signore." : "Apri ⚙ e inserisci URL del server e token.");
connect();
