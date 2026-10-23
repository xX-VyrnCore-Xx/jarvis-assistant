"""Chiamate dal telefono Android (Telefono e WhatsApp) su richiesta dell'utente.

Quando l'utente dice «chiama X» la chiamata parte subito, senza chiedere conferma (la richiesta stessa è il consenso). Le salvaguardie sono altre: il messaggio dell'utente deve chiedere davvero di chiamare
(un'istruzione nascosta in un'email o in una pagina non fa partire nulla), niente numeri a pagamento, massimo 10 chiamate al giorno. Il server manda
al telefono l'ordine di chiamare, che l'app esegue (i contatti si risolvono sul telefono, il server non li vede mai)."""
import re
import time

from ..phonebridge import BridgeError, clean_contacts
from . import UNTRUSTED, USER_TEXT, ToolRegistry

NUMBER = re.compile(r"^[+0-9 ()./-]{3,24}$")
# numeri a pagamento italiani (89x, 144, 166, 178, 199, 892, 895, 899…): non si chiamano su ordine del modello
PREMIUM = re.compile(r"^(?:\+39|0039)?(?:89\d|144|166|178|199)")
CALLS_PER_DAY = 10
CALL_INTENT = re.compile(r"\b(chiam\w*|telefon\w*|videochiam\w*|videochiamat\w*|whats\s?app|wa|squill\w*|contatta\w*|sentire|sentirlo|sentirla|parlare con|fai una chiamata|fammi (?:una )?chiamata)\b", re.I)


def register_phone_tools(reg: ToolRegistry, pending, notifier_of, bridge=None, store=None) -> None:
    async def contacts_search(query: str) -> str:
        """Cerca nella rubrica del telefono (solo nomi e codici: i numeri non lasciano mai il telefono)."""
        q = " ".join((query or "").split())[:60]
        if len(q) < 2:
            return "Errore: scrivi almeno due lettere del nome."
        try:
            data = await bridge.ask("contacts.search", {"query": q})
        except BridgeError as e:
            return f"Errore: {e}"
        rows = clean_contacts(data.get("contacts"))
        bridge.audit("search", q, len(rows))
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
        if NUMBER.fullmatch(who) and PREMIUM.match(re.sub(r"[ ()./-]", "", who)):
            return "Errore: non chiamo numeri a pagamento o a sovrapprezzo."
        if video and way != "whatsapp":
            return "Errore: la videochiamata è disponibile solo su WhatsApp."
        label = f"{'videochiamata' if video else 'chiamata'} {'WhatsApp' if way == 'whatsapp' else 'telefonica'} a «{who}»" + (" (numero)" if NUMBER.fullmatch(who) else "")

        asked = USER_TEXT.get()
        if asked and not CALL_INTENT.search(asked):  # il messaggio dell'utente non chiede di chiamare: potrebbe essere un'istruzione nascosta in un contenuto esterno
            return "Errore: l'utente non ha chiesto di chiamare in questo messaggio, quindi non avvio la chiamata."
        if store is not None:
            day = f"calls:{time.strftime('%Y-%m-%d')}"
            n = int(await store.get_setting(day) or 0)
            if n >= CALLS_PER_DAY:
                return f"Limite di {CALLS_PER_DAY} chiamate al giorno raggiunto: per sicurezza non ne avvio altre."
            await store.set_setting(day, str(n + 1))
        notifier = notifier_of()
        await notifier.push("call", f"Chiamo {who}", f"{label[0].upper()}{label[1:]}.", telegram=False,
                            meta={"contact": who, "contact_id": cid, "via": way, "video": bool(video)})
        online = bool(getattr(notifier, "listeners", 1))
        return (f"Chiamata avviata: {label}. Parte dall'app JARVIS sul telefono." if online
                else f"Ho inviato l'ordine per la {label}, ma l'app JARVIS non è aperta: la chiamata parte appena la apri (entro 2 minuti).")

    reg.register("phone_call", "Chiama una persona dal telefono Android dell'utente, con il Telefono o con WhatsApp (voce o video). La chiamata PARTE SUBITO: non chiedere conferma all'utente, ha già chiesto lui di chiamare. "
                 "'contact' è il nome come in rubrica o un numero; via = phone (predefinito) o whatsapp.",
                 {"type": "object", "properties": {"contact": {"type": "string", "description": "Nome come in rubrica o numero"}, "contact_id": {"type": "string", "description": "id restituito da contacts_search (se lo hai)"},
                                    "via": {"type": "string", "enum": ["phone", "whatsapp"]}, "video": {"type": "boolean"}}, "required": ["contact"]},
                 phone_call)

    if bridge is not None:
        reg.register("contacts_search", "Cerca una persona nella rubrica del telefono Android dell'utente (serve l'app aperta e la funzione attiva). Restituisce nomi e codici, MAI i numeri: "
                     "per chiamare passa nome e id a phone_call. Usalo quando l'utente nomina una persona da chiamare o chiede chi c'è in rubrica.",
                     {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}, contacts_search, timeout=30)
