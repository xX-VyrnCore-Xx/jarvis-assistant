"""Legge un backup notturno (jarvis/AAAA-MM-GG.json.enc) scaricato da Hugging Face e lo stampa in chiaro.

    ENCRYPTION_KEY=... python scripts/decrypt_backup.py 2026-10-20.json.enc > backup.json

Serve la stessa ENCRYPTION_KEY del server (o JARVIS_API_TOKEN se ENCRYPTION_KEY non è impostata). Decifra sia il file sia i singoli campi cifrati.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.backup import decrypt, derive_key  # noqa: E402
from app.config import Settings  # noqa: E402
from app.crypto import Vault  # noqa: E402

if len(sys.argv) != 2:
    sys.exit(__doc__)
secret = os.environ.get("ENCRYPTION_KEY") or os.environ.get("JARVIS_API_TOKEN", "")
if not secret:
    sys.exit("Imposta ENCRYPTION_KEY.")
data = json.loads(decrypt(derive_key(Settings(encryption_key=secret)), open(sys.argv[1], "rb").read()))
vault = Vault(secret)
for rows in data["tables"].values():
    for row in rows:
        for k, v in list(row.items()):
            if isinstance(v, str) and Vault.sealed(v):
                row[k] = vault.open(v)
        row.pop("terms", None)
json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
