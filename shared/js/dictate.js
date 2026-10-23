// Dettatura di qualità: registra la voce con il microfono del dispositivo (rumore ridotto, guadagno automatico), capisce da solo quando hai finito di parlare
// (soglia adattiva sul rumore di fondo) e restituisce l'audio da trascrivere con Whisper sul server. Molto più preciso del riconoscimento integrato del telefono,
// che taglia le pause e sbaglia le parole meno comuni.

const TYPES = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];

export const dictationSupported = () => !!(navigator.mediaDevices?.getUserMedia && globalThis.MediaRecorder && (globalThis.AudioContext || globalThis.webkitAudioContext));

/**
 * Registra una frase. Si ferma da sola dopo `silenceMs` di silenzio dall'ultima parola, o dopo `maxMs`.
 * @param {{signal?: AbortSignal, onLevel?: (v: number) => void, onSpeech?: () => void, maxMs?: number, silenceMs?: number, startMs?: number, stopRef?: {stop?: () => void}}} o
 * @returns {Promise<{blob: Blob|null, spoke: boolean}>} blob nullo se non si è sentito nulla o è stato annullato
 */
export async function recordUtterance({ signal, onLevel = () => {}, onSpeech = () => {}, maxMs = 30_000, silenceMs = 1500, startMs = 7000, stopRef = {} } = {}) {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
  const Ctx = globalThis.AudioContext || globalThis.webkitAudioContext;
  const ctx = new Ctx();
  const src = ctx.createMediaStreamSource(stream);
  const an = ctx.createAnalyser();
  an.fftSize = 1024;
  src.connect(an);
  const type = TYPES.find((t) => MediaRecorder.isTypeSupported?.(t)) || "";
  const rec = new MediaRecorder(stream, { ...(type ? { mimeType: type } : {}), audioBitsPerSecond: 32_000 });
  const chunks = [];
  rec.ondataavailable = (e) => { if (e.data?.size) chunks.push(e.data); };
  const buf = new Float32Array(an.fftSize);
  const t0 = performance.now();
  let floor = 0, calib = 0, spokeAt = 0, lastVoice = 0, cancelled = false, finished = false;

  return new Promise((resolve, reject) => {
    const end = (cancel = false) => {
      if (finished) return;
      finished = true; cancelled = cancel;
      clearInterval(timer);
      try { rec.state !== "inactive" && rec.stop(); } catch { /* già fermo */ }
    };
    stopRef.stop = () => end(false);
    signal?.addEventListener("abort", () => end(true), { once: true });
    rec.onstop = () => {
      stream.getTracks().forEach((t) => t.stop());
      ctx.close().catch(() => {});
      onLevel(0);
      const blob = !cancelled && spokeAt && chunks.length ? new Blob(chunks, { type: rec.mimeType || type || "audio/webm" }) : null;
      resolve({ blob, spoke: !!spokeAt });
    };
    rec.onerror = (e) => { stream.getTracks().forEach((t) => t.stop()); reject(e.error || new Error("Registrazione non riuscita")); };
    rec.start(250);
    const timer = setInterval(() => {
      an.getFloatTimeDomainData(buf);
      let sum = 0;
      for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i];
      const rms = Math.sqrt(sum / buf.length);
      const now = performance.now() - t0;
      onLevel(Math.min(1, rms * 9));
      if (now < 500) { floor = (floor * calib + rms) / (calib + 1); calib++; return; }  // il primo mezzo secondo misura il rumore di fondo
      const threshold = Math.max(0.02, floor * 2.6 + 0.008);
      if (rms > threshold) {
        if (!spokeAt) { spokeAt = now; onSpeech(); }
        lastVoice = now;
      }
      if (spokeAt && now - lastVoice > silenceMs) end(false);
      else if (!spokeAt && now > startMs) end(false);
      else if (now > maxMs) end(false);
    }, 50);
  });
}
