"""Dataset per il fine-tuning LoRA di un modello aperto sullo stile di JARVIS.

Le conversazioni (già cifrate su Supabase) vengono lette, ripulite dai dati sensibili in modalità `strict` (IBAN, carte, chiavi,
password, codice fiscale, email, telefoni), trasformate in esempi di chat e salvate CIFRATE (AES-256-GCM) nel dataset privato di
Hugging Face. L'addestramento avviene fuori da Render, su una GPU gratuita (notebook in `finetune/`), che decifra con la tua ENCRYPTION_KEY.
"""
import base64
import json
from datetime import datetime, timedelta, timezone

from .backup import FOLDER, HF, HFBackup, derive_key, encrypt
from .config import Settings
from .memory import Store
from .privacy import Redactor

PURPOSE = b"jarvis-finetune"
PATH = "finetune/dataset.jsonl.enc"
SYSTEM = ("Sei JARVIS, l'assistente personale del signore: italiano, tono elegante e ironico da Iron Man, risposte concise e precise, "
          "mai inventare, chiedi conferma prima di azioni irreversibili.")
SKIP_SESSIONS = {"briefing"}
MAX_TURNS = 6          # coppie utente/assistente per esempio
MIN_REPLY, MAX_REPLY = 12, 3500
BAD_REPLY = ("errore", "non riesco a", "non ho potuto", "[dato non decifrabile")


def _usable(role: str, text: str) -> bool:
    t = (text or "").strip()
    if role == "user":
        return len(t) >= 2
    return MIN_REPLY <= len(t) <= MAX_REPLY and not t.lower().startswith(BAD_REPLY)


def build_examples(rows: list[dict]) -> list[dict]:
    """Righe cronologiche {session_id, role, content} -> esempi {"messages": [...]}, ognuno con un solo insieme di segnaposto."""
    sessions: dict[str, list[dict]] = {}
    for r in rows:
        if r.get("session_id") not in SKIP_SESSIONS and r.get("role") in ("user", "assistant"):
            sessions.setdefault(r["session_id"], []).append(r)
    out: list[dict] = []
    for msgs in sessions.values():
        pairs, i = [], 0
        while i + 1 < len(msgs):
            a, b = msgs[i], msgs[i + 1]
            if a["role"] == "user" and b["role"] == "assistant" and _usable("user", a["content"]) and _usable("assistant", b["content"]):
                pairs.append((a["content"].strip(), b["content"].strip()))
                i += 2
            else:
                i += 1
        for k in range(0, len(pairs), MAX_TURNS):
            red = Redactor("strict")
            chat = [{"role": "system", "content": SYSTEM}]
            for q, a in pairs[k:k + MAX_TURNS]:
                chat += [{"role": "user", "content": red.mask(q)}, {"role": "assistant", "content": red.mask(a)}]
            out.append({"messages": chat})
    return out


def to_jsonl(examples: list[dict]) -> bytes:
    return "\n".join(json.dumps(e, ensure_ascii=False) for e in examples).encode()


async def export_dataset(settings: Settings, store: Store, backup: HFBackup, days: int = 180, limit: int = 5000) -> dict:
    """Costruisce il dataset e lo carica cifrato su Hugging Face. Restituisce solo statistiche, mai testo."""
    if not backup.enabled:
        raise RuntimeError("serve il dataset privato su Hugging Face (FREEAPI_DB_BACKUP_URL e FREEAPI_DB_BACKUP_TOKEN)")
    end = datetime.now(timezone.utc)
    rows = await store.messages_between((end - timedelta(days=days)).isoformat(), (end + timedelta(days=1)).isoformat(), limit)
    examples = build_examples(rows)
    if not examples:
        return {"examples": 0, "messages": len(rows), "uploaded": False}
    blob = encrypt(derive_key(settings, PURPOSE), to_jsonl(examples))
    ops = [{"key": "header", "value": {"summary": f"Dataset LoRA {end:%Y-%m-%d} ({len(examples)} esempi)"}},
           {"key": "file", "value": {"path": PATH, "encoding": "base64", "content": base64.b64encode(blob).decode()}}]
    r = await backup._client.post(f"{HF}/api/datasets/{backup.repo}/commit/main", headers={**backup._auth, "Content-Type": "application/x-ndjson"},
                                  content="\n".join(json.dumps(o) for o in ops))
    r.raise_for_status()
    return {"examples": len(examples), "messages": len(rows), "uploaded": True, "path": PATH, "kb": len(blob) // 1024, "repo": backup.repo, "folder": FOLDER}
