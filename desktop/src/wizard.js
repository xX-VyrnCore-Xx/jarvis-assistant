// Procedura guidata del primo avvio: benvenuto → collegamento al server → preferenze → voce → fatto.
import { el } from "@shared/format.js";
import { icon } from "@shared/icons.js";

const STEPS = ["Benvenuto", "Collegamento", "Preferenze", "Voce"];

export function runWizard({ cfg, api, invoke, saveToken, errText, installVoice, speak, onDone }) {
  const state = { step: 0, tested: false, autostart: true, speak: true, voice: false, busy: false, msg: "", bad: false };
  const url = el("input", { type: "text", value: cfg.url, spellcheck: "false", "aria-label": "Indirizzo del server" });
  const token = el("input", { type: "password", value: cfg.token || "", autocomplete: "off", "aria-label": "Token personale", placeholder: "Incolla qui il tuo token" });
  const box = el("div", { class: "dialog wizard", role: "dialog", "aria-modal": "true" });
  const overlay = el("div", { class: "overlay" }, box);
  const close = () => overlay.remove();

  const test = async () => {
    state.busy = true; state.msg = "Provo il collegamento…"; state.bad = false; draw();
    const saved = { url: cfg.url, token: cfg.token };
    cfg.url = url.value.trim().replace(/\/+$/, ""); cfg.token = token.value.trim();
    try {
      const st = await api.status();
      state.tested = true; state.msg = `Collegato (v${st.version}). ${st.freellm?.ready ? "L'intelligenza è pronta." : "L'intelligenza si sta ancora avviando: puoi proseguire."}`;
    } catch (e) {
      Object.assign(cfg, saved); state.tested = false; state.bad = true;
      state.msg = e?.status === 401 ? "Token non valido: ricontrollalo (è JARVIS_API_TOKEN su Render)." : errText(e);
    }
    state.busy = false; draw();
  };
  url.addEventListener("input", () => { state.tested = false; });
  token.addEventListener("input", () => { state.tested = false; state.msg = ""; });

  const finish = async () => {
    state.busy = true; draw();
    try {
      localStorage.setItem("jarvis.url", cfg.url);
      cfg.where = await saveToken(cfg.token);
      localStorage.setItem("jarvis.speak", state.speak ? "1" : "0");
      localStorage.setItem("jarvis.wizard", "1");
      localStorage.setItem("jarvis.init", "1");
      localStorage.setItem("jarvis.voice.asked", "1");
      await invoke("autostart_set", { enabled: state.autostart }).catch(() => {});
      if (state.voice) installVoice();
    } finally { close(); onDone({ voice: state.voice }); }
  };

  const dots = () => el("div", { class: "wiz-dots", "aria-label": `Passo ${state.step + 1} di ${STEPS.length}` },
    ...STEPS.map((s, i) => el("span", { class: `wiz-dot${i === state.step ? " on" : i < state.step ? " done" : ""}`, title: s })));

  const pages = [
    () => [
      el("div", { class: "dlg-icon" }, icon("sparkle", 28)), el("h2", {}, "Benvenuto, signore"),
      el("p", {}, "Questa procedura collega JARVIS al tuo server e sceglie le preferenze. Servono meno di due minuti."),
      el("ul", { class: "wiz-list" },
        el("li", {}, "Scorciatoia ", el("b", {}, "Alt+Spazio"), ": mostra o nasconde JARVIS ovunque."),
        el("li", {}, "La X della finestra la nasconde: JARVIS resta attivo nella barra delle applicazioni."),
        el("li", {}, "Per chiuderlo del tutto: icona nella barra → ", el("b", {}, "Esci definitivamente"), ".")),
    ],
    () => [
      el("div", { class: "dlg-icon" }, icon("gauge", 28)), el("h2", {}, "Collegamento"),
      el("label", { class: "field wiz-left" }, "Indirizzo del server", url),
      el("label", { class: "field wiz-left" }, "Token personale", token,
        el("small", {}, "Lo trovi su Render come JARVIS_API_TOKEN. Resta nel Gestore credenziali di Windows, cifrato dal tuo account.")),
      el("div", { class: "row" }, el("button", { class: "btn", disabled: state.busy, onclick: test }, "Prova il collegamento")),
      state.msg ? el("p", { class: `tiny ${state.bad ? "bad" : state.tested ? "ok" : ""}`, role: "status" }, state.msg) : null,
    ],
    () => [
      el("div", { class: "dlg-icon" }, icon("bell", 28)), el("h2", {}, "Preferenze"),
      check("Avvia JARVIS con Windows (resta nella barra delle applicazioni)", state.autostart, (v) => (state.autostart = v)),
      check("Leggi le risposte con la voce di JARVIS", state.speak, (v) => (state.speak = v)),
      el("small", {}, "Le notifiche e i promemoria arrivano come avvisi di Windows. Puoi cambiare tutto dopo da Impostazioni."),
    ],
    () => [
      el("div", { class: "dlg-icon" }, icon("volume", 28)), el("h2", {}, "Voce di JARVIS"),
      el("p", {}, "Vuoi la voce clonata di JARVIS? Gira sul tuo PC, è gratuita e serve anche al telefono quando il PC è acceso."),
      el("small", {}, "Download di circa 3 GB, una volta sola, in sottofondo: nel frattempo puoi usare JARVIS."),
      check("Installa la voce adesso", state.voice, (v) => (state.voice = v)),
    ],
  ];

  function check(label, value, set) {
    const input = el("input", { type: "checkbox" });
    input.checked = value;
    input.addEventListener("change", () => set(input.checked));
    return el("label", { class: "check wiz-left" }, input, label);
  }

  function draw() {
    const last = state.step === STEPS.length - 1;
    const needsLink = state.step === 1 && !state.tested;
    box.replaceChildren(dots(), ...pages[state.step](),
      el("div", { class: "row end" },
        state.step > 0 ? el("button", { class: "btn", disabled: state.busy, onclick: () => { state.step--; state.msg = ""; draw(); } }, "Indietro") : el("button", { class: "btn", onclick: () => { localStorage.setItem("jarvis.wizard", "1"); close(); onDone({ skipped: true }); } }, "Salta"),
        last ? el("button", { class: "btn primary", disabled: state.busy, onclick: finish }, "Fine")
          : el("button", { class: "btn primary", disabled: state.busy || needsLink, title: needsLink ? "Prova prima il collegamento" : "", onclick: () => { state.step++; state.msg = ""; draw(); } }, "Avanti")));
    box.querySelector("input:not([type=checkbox]), .btn.primary")?.focus?.();
  }

  overlay.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && state.step === 1 && !state.busy && !state.tested && e.target.tagName === "INPUT") test();
  });
  document.body.append(overlay);
  draw();
  return close;
}
