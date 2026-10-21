# Fine-tuning LoRA di JARVIS

1. `POST /api/finetune/export` (token JARVIS): legge le conversazioni, mascheratura **strict** di dati sensibili, e salva `finetune/dataset.jsonl.enc` cifrato (AES-256-GCM) nel dataset privato Hugging Face.
2. Apri `jarvis_lora.ipynb` in Google Colab (GPU T4 gratuita): chiede token HF e `ENCRYPTION_KEY` con `getpass`, decifra solo in memoria, addestra un LoRA su `Qwen2.5-3B-Instruct` in 4 bit e carica l'adattatore in un repo modello **privato**.
3. L'uso dal vivo richiede una GPU che serva modello + adattatore (non Render Free).

Serve un numero decente di conversazioni (da qualche decina di scambi in su); con pochi dati l'adattatore non migliora nulla.
Il notebook non è stato eseguito in questa sessione (nessuna GPU): al primo giro controlla le versioni delle librerie.
