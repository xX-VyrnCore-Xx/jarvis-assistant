// Lettura ad alta voce con la voce di JARVIS (XTTS v2 sul server). Se il server non risponde, usa la voce del dispositivo.

export function plainForSpeech(text) {
  return text
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/https?:\/\/\S+/g, " ")
    .replace(/[*_`#>~]+/g, "")
    .replace(/^\s*[-•]\s+/gm, "")
    .replace(/[\u{1F300}-\u{1FAFF}☀-➿]/gu, "")
    .replace(/\s+/g, " ")
    .trim();
}

/** Frasi di al massimo `max` caratteri: la prima parte subito, le altre mentre si ascolta. */
export function sentences(text, max = 220) {
  const out = [];
  for (const part of text.match(/[^.!?;:\n]+[.!?;:]*/g) || []) {
    let s = part.trim();
    while (s.length > max) {
      const cut = s.lastIndexOf(" ", max);
      out.push(s.slice(0, cut > 40 ? cut : max).trim());
      s = s.slice(cut > 40 ? cut : max).trim();
    }
    if (s) out.push(s);
  }
  const merged = [];
  for (const s of out) {
    if (merged.length && merged[merged.length - 1].length + s.length < 160) merged[merged.length - 1] += ` ${s}`;
    else merged.push(s);
  }
  return merged;
}

export class Speaker {
  /** @param {{tts: (t: string) => Promise<Blob>}} api */
  constructor(api) {
    this.api = api;
    this.run = 0;
    this.audio = null;
    this.onState = () => {};
  }

  get speaking() { return this._speaking === true; }

  stop() {
    this.run++;
    this.audio?.pause();
    this.audio = null;
    globalThis.speechSynthesis?.cancel();
    this._set(false);
  }

  _set(v) { if (this._speaking !== v) { this._speaking = v; this.onState(v); } }

  async speak(text, maxChars = 700) {
    this.stop();
    const parts = sentences(plainForSpeech(text).slice(0, maxChars));
    if (!parts.length) return;
    const run = this.run;
    this._set(true);
    let fetchNext = this.api.tts(parts[0]).catch(() => null);
    for (let i = 0; i < parts.length && run === this.run; i++) {
      const blob = await fetchNext;
      fetchNext = i + 1 < parts.length ? this.api.tts(parts[i + 1]).catch(() => null) : null; // prepara la frase successiva
      if (run !== this.run) return;
      if (!blob) { await this._fallback(parts.slice(i).join(" "), run); break; }
      await this._play(blob, run);
    }
    if (run === this.run) this._set(false);
  }

  _play(blob, run) {
    return new Promise((resolve) => {
      const url = URL.createObjectURL(blob);
      const a = new Audio(url);
      this.audio = a;
      const done = () => { URL.revokeObjectURL(url); resolve(); };
      a.onended = done;
      a.onerror = done;
      a.onpause = () => { if (run !== this.run) done(); };
      a.play().catch(done);
    });
  }

  _fallback(text, run) {
    return new Promise((resolve) => {
      const synth = globalThis.speechSynthesis;
      if (!synth) return resolve();
      const u = new SpeechSynthesisUtterance(text);
      u.lang = "it-IT";
      u.onend = u.onerror = resolve;
      if (run === this.run) synth.speak(u); else resolve();
    });
  }
}
