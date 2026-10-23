"""Chiamate dal telefono Android (Telefono e WhatsApp) su richiesta dell'utente.

JARVIS non può far partire una chiamata da solo: crea una richiesta di conferma (come per le email); solo dopo l'OK dell'utente manda
al telefono l'ordine di chiamare, che l'app esegue (i contatti si risolvono sul telefono, il server non li vede mai)."""
import re

from ..phonebridge import BridgeError
from . import UNTRUSTED, ToolRegistry

NUMBER = re.compile(r"^[+0-9 ()./-]{3,24}$")


def register_phone_tools(reg: ToolRegistry, pending, notifier_of, bridge=None) -> None:
    async def contacts_search(query: str) -> str:
        """Cerca nella rubrica del telefono (solo nomi e codici: i numeri non lasciano mai il telefono)."""
        q = " ".join((query or "").split())[:60]
        if len(q) < 2:
            return "Errore: scrivi almeno due lettere del nome."
        try:
            data = await bridge.ask("contacts.search", {"query": q})
        except BridgeError as e:
            return f"Errore: {e}"
        rows = data.get("contacts") or []
        if not rows:
            return f"Nessun contatto trovato per «{q}»."
        out = []
        for c in rows[:8]:
            cid, name = str(c.get("id", ""))[:20], str(c.get("name", ""))[:60]
            extra = ", ".join(x for x in (f"{c['numbers']} numeri" if c.get("numbers", 1) > 1 else "", "WhatsApp" if c.get("whatsapp") else "") if x)
            out.append(f"- {name} [id: {cid}]" + (f" ({extra})" if extra else ""))
        return UNTRUSTED + "\n".join(out) + "\nPer chiamare usa phone_call con il nome e l'id (i numeri restano sul telefono)."

    async def phone_call(contact: str, via: str = "phone", video: bool = False, contact_id: str = "") -> str:
        who = " ".join((contact or "").split())[:80]
        cid = re.sub(r"[^A-Za-z0-9_-]", "", contact_id or "")[:24]
        way = (via or "phone").strip().lower()
        way = {"telefono": "phone", "chiamata": "phone", "wa": "whatsapp", "whats app": "whatsapp"}.get(way, way)
        if not who:
            return "Errore: indica chi chiamare (nome o numero)."
        if way not in ("phone", "whatsapp"):
            return "Errore: 'via' deve essere phone o whatsapp."
        if video and way != "whatsapp":
            return "Errore: la videochiamata è disponibile solo su WhatsApp."
        label = f"{'videochiamata' if video else 'chiamata'} {'WhatsApp' if way == 'whatsapp' else 'telefonica'} a «{who}»" + (" (numero)" if NUMBER.fullmatch(who) else "")

        async def go() -> str:
            await notifier_of().push("call", f"Chiama {who}", f"{label[0].upper()}{label[1:]}: tocca per avviarla.",
                                     telegram=False, meta={"contact": who, "contact_id": cid, "via": way, "video": bool(video)})
            return "Ordine inviato al telefono: la chiamata parte dall'app JARVIS."

        p = pending.create("phone_call", f"Fare una {label}", go)
        return (f"In attesa della conferma dell'utente (app o Telegram) per la {label}. Id richiesta: {p.id}. "
                "Dopo l'OK il telefono avvia la chiamata (l'app JARVIS deve essere installata su Android). Non insistere: avvisalo che deve confermare.")

    reg.register("phone_call", "Chiama una persona dal telefono Android dell'utente, con il Telefono o con WhatsApp (voce o video). Serve la conferma dell'utente. "
                 "'contact' è il nome come in rubrica o un numero; via = phone (predefinito) o whatsapp.",
                 {"type": "object", "properties": {"contact": {"type": "string", "description": "Nome come in rubrica o numero"}, "contact_id": {"type": "string", "description": "id restituito da contacts_search (se lo hai)"},
                                    "via": {"type": "string", "enum": ["phone", "whatsapp"]}, "video": {"type": "boolean"}}, "required": ["contact"]},
                 phone_call)

    if bridge is not None:
        reg.register("contacts_search", "Cerca una persona nella rubrica del telefono Android dell'utente (serve l'app aperta e la funzione attiva). Restituisce nomi e codici, MAI i numeri: "
                     "per chiamare passa nome e id a phone_call. Usalo quando l'utente nomina una persona da chiamare o chiede chi c'è in rubrica.",
                     {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}, contacts_search, timeout=30)
