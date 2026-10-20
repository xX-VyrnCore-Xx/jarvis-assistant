---
title: JARVIS Voice
emoji: 🎙️
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
license: other
---
Sintesi vocale XTTS v2 con la voce di JARVIS clonata da `voice/jarvis.wav`. Uso personale (licenza CPML, non commerciale).
Endpoint: `POST /tts {"text": "...", "lang": "it"}` con `Authorization: Bearer <TTS_TOKEN>` → audio WAV.
