"""Aggiunge a FREEAPI_CONFIG_JSON i provider gratuiti senza chiave (OVH AI Endpoints, Kilo Gateway, ricerca Parallel)
e SiliconFlow se esiste SILICONFLOW_API_KEY. Non tocca le voci già presenti; stampa solo il JSON risultante
(se quello esistente non è valido lo restituisce com'è, ci pensa start.sh)."""
import json
import os
import sys

KEYLESS = ("ovh", "kilo", "parallel")


def merge(raw: str, env: dict) -> str:
    try:
        cfg = json.loads(raw) if raw.strip() else {}
        if not isinstance(cfg, dict) or not isinstance(cfg.get("keys", []), list):
            return raw
    except json.JSONDecodeError:
        return raw
    keys = cfg.setdefault("keys", [])
    have = {k.get("platform") for k in keys if isinstance(k, dict)}
    if env.get("AUTO_KEYLESS_PROVIDERS", "1") != "0":
        keys += [{"platform": p, "label": "jarvis"} for p in KEYLESS if p not in have]
    sf = env.get("SILICONFLOW_API_KEY", "").strip()
    if sf and "siliconflow" not in have:
        keys.append({"platform": "siliconflow", "key": sf, "label": "jarvis"})
    return json.dumps(cfg, separators=(",", ":"))


if __name__ == "__main__":
    sys.stdout.write(merge(os.environ.get("FREEAPI_CONFIG_JSON", ""), dict(os.environ)))
