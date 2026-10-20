# JARVIS Voce

Wake word **"Hey Jarvis"** (openWakeWord) → registrazione fino al silenzio → trascrizione locale (Whisper) →
`/chat` → risposta letta con voce italiana (Edge-TTS). Tutto gratuito; solo la sintesi vocale usa la rete.

## Avvio (Windows)
```
cd voice
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env     # compila JARVIS_URL e JARVIS_API_TOKEN
python -m jarvis_voice
```
La prima volta scarica i modelli (wake word e Whisper `small`, ~500 MB). Un beep conferma che ti ha sentito.

Opzioni in `.env`: `WAKE_THRESHOLD` (0.5; alzalo se scatta da solo), `WHISPER_MODEL` (`base` è più leggero,
`medium` più preciso), `TTS_VOICE` (es. `it-IT-IsabellaNeural`).

Per l'avvio automatico: collegamento a `pythonw -m jarvis_voice` in `shell:startup`.
