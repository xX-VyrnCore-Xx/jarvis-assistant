"""Chiamate dal telefono Android (Telefono e WhatsApp) su richiesta dell'utente.

JARVIS non può far partire una chiamata da solo: crea una richiesta di conferma (come per le email); solo dopo l'OK dell'utente manda
al telefono l'ordine di chiamare, che l'app esegue (i contatti si risolvono sul telefono, il server non li vede mai)."""
import re

from . import ToolRegistry

NUMBER = re.compile(r"^[+0-9 ()./-]{3,24}$")


def register_phone_tools(reg: ToolRegistry, pending, notifier_of) -> None:
    async def phone_call(contact: str, via: str = "phone", video: bool = False) -> str:
        who = " ".join((contact or "").split())[:80]
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
                                     telegram=False, meta={"contact": who, "via": way, "video": bool(video)})
            return "Ordine inviato al telefono: la chiamata parte dall'app JARVIS."

        p = pending.create("phone_call", f"Fare una {label}", go)
        return (f"In attesa della conferma dell'utente (app o Telegram) per la {label}. Id richiesta: {p.id}. "
                "Dopo l'OK il telefono avvia la chiamata (l'app JARVIS deve essere installata su Android). Non insistere: avvisalo che deve confermare.")

    reg.register("phone_call", "Chiama una persona dal telefono Android dell'utente, con il Telefono o con WhatsApp (voce o video). Serve la conferma dell'utente. "
                 "'contact' è il nome come in rubrica o un numero; via = phone (predefinito) o whatsapp.",
                 {"type": "object", "properties": {"contact": {"type": "string"}, "via": {"type": "string", "enum": ["phone", "whatsapp"]}, "video": {"type": "boolean"}}, "required": ["contact"]},
                 phone_call)
