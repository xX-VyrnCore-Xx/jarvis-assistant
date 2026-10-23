// Scrittura progressiva: il testo si vede comparire mentre JARVIS «scrive», anche quando il server o un provider consegna tutto insieme.
// Non resta mai molto indietro (si adatta alla quantità di testo in attesa) e, a risposta finita, si completa in poco più di mezzo secondo.

export class Typewriter {
  /** @param {(text: string) => void} render chiamata con il testo scoperto finora */
  constructor(render, { cps = 90 } = {}) {
    this.render = render;
    this.cps = cps;
    this.target = "";
    this.shown = 0;
    this.burst = false;
    this.ending = false;
    this.raf = 0;
    this.last = 0;
    this._done = null;
  }

  /** Aggiunge testo da scoprire. Un blocco grande tutto insieme (provider che non fa streaming) si scopre in 2-3 secondi. */
  push(text) {
    if (!text) return;
    if (text.length >= 80) this.burst = true;
    this.target += text;
    this._kick();
  }

  /** Allinea il testo finale (se diverso da quello ricevuto a pezzi) e lo completa. Risolve quando tutto è visibile. */
  finish(finalText) {
    if (typeof finalText === "string" && finalText !== this.target) {
      if (!finalText.startsWith(this.target.slice(0, this.shown))) this.shown = 0;  // il finale non coincide con ciò che si vede: si riparte
      if (finalText.length - this.target.length >= 80) this.burst = true;
      this.target = finalText;
    }
    this.ending = true;
    if (this.shown >= this.target.length) { this._paint(); return Promise.resolve(); }
    this._kick();
    return new Promise((r) => { this._done = r; });
  }

  stop() {
    cancelAnimationFrame(this.raf);
    this.raf = 0;
    this._done?.();
    this._done = null;
  }

  _kick() {
    if (!this.raf) { this.last = performance.now(); this.raf = requestAnimationFrame((t) => this._tick(t)); }
  }

  _paint() {
    let n = this.shown;
    const c = this.target.charCodeAt(n - 1);
    if (c >= 0xd800 && c <= 0xdbff) n--;  // mai a metà di una coppia surrogata (emoji)
    this.render(this.target.slice(0, n));
  }

  _tick(now) {
    this.raf = 0;
    const dt = Math.min(0.1, (now - this.last) / 1000);
    this.last = now;
    const backlog = this.target.length - this.shown;
    const lag = this.ending ? 0.5 : this.burst ? 3 : 1.2;  // quanto può restare indietro, in secondi
    const speed = Math.max(this.cps, backlog / lag);
    this.shown = Math.min(this.target.length, this.shown + Math.max(1, Math.round(speed * dt)));
    this._paint();
    if (this.shown < this.target.length) this._kick();
    else if (this._done && this.ending) { this._done(); this._done = null; }
  }
}
