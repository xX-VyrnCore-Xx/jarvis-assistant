"""Scelta degli strumenti per ogni richiesta. Mandare al modello tutte le definizioni dei tool costa 4-5.000 token a messaggio
(lentezza, quota gratuita e limiti dei provider superati); qui si invia solo ciò che c'entra con la richiesta.
Se serve altro, il modello chiama `need_tools` e il gruppo si aggiunge nello stesso turno: nessuna funzione va persa."""
from ..skills.registry import tokens

CORE = {"get_datetime", "calculate", "date_info", "remember", "recall", "brain_search", "add_reminder", "remind_in", "web_search"}

# gruppo -> (nomi esatti o prefissi che finiscono con *, frasi/parole che lo attivano)
GROUPS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "promemoria": (("list_reminders", "delete_reminder", "reminder_snooze"),
                   ("promemoria", "ricordami", "rimanda", "sveglia", "avvisami", "elimina il promemoria", "cancella il promemoria", "posticipa")),
    "calendario": (("calendar_*",), ("calendario", "agenda", "evento", "eventi", "appuntamento", "appuntamenti", "riunione", "impegno", "impegni", "libero", "disponibile",
                                     "disponibilità", "invito", "fissa", "sposta", "organizza", "settimana", "domani ho", "cosa ho")),
    "email": (("gmail_*",), ("email", "mail", "posta", "inbox", "bozza", "rispondi", "rispondere", "scrivi a", "allegato", "mittente", "non lette")),
    "drive": (("drive_*",), ("drive", "documento", "documenti", "foglio", "cartella", "google docs", "presentazione", "file su")),
    "web": (("web_news", "read_webpage", "wikipedia", "get_weather"),
            ("notizie", "news", "meteo", "piove", "pioggia", "temperatura", "previsioni", "wikipedia", "chi è", "cos'è", "cosa è", "che cos'è", "sito", "pagina", "http", "leggi", "ultime", "attualità", "fa caldo", "fa freddo")),
    "coding": (("code_*",), ("coding", "codice", "programma", "programmare", "sandbox", "repo", "repository", "github", "commit", "pull request", "branch", "merge", "crea un progetto", "sviluppa", "scrivi il codice",
                              "implementa", "sessione di coding", "applicazione", "sito web", "script", "bug", "refactor", "ci verde", "test automatici", "elimina il repo", "elimina la repo", "cancella il repo", "lista dei repo", "issue", "rilascio", "release")),
    "notizie": (("news_headlines", "feed_list", "feed_add", "feed_remove", "jarvis_status"),
                ("notizie", "news", "ultime notizie", "cosa succede", "cosa è successo", "successo oggi", "oggi nel mondo", "attualità", "titoli", "giornale", "giornali", "rss", "feed",
                 "terremoto", "terremoti", "sisma", "breaking", "ultim'ora", "aggiornato", "aggiornamento", "aggiornati", "versione", "release", "ti sei aggiornato", "stato di jarvis")),
    "utilita": (("convert_currency", "crypto_price", "unit_convert", "world_time"),
                ("cambio", "valuta", "euro", "dollari", "dollaro", "sterline", "bitcoin", "crypto", "cripto", "ethereum", "converti", "conversione", "quanti metri", "chilometri", "miglia",
                 "che ore sono a", "ora a", "ora di", "fuso", "kg", "libbre", "litri")),
    "liste": (("task_*",), ("lista", "liste", "spesa", "attività", "da fare", "todo", "compra", "aggiungi alla", "completa")),
    "memoria": (("list_memories", "forget"), ("ricordi", "dimentica", "cosa ricordi", "cancella il ricordo")),
    "cervello": (("brain_*",), ("cervello", "nota", "appunto", "appunti", "salva", "studia", "impara", "profilo", "cosa so", "ripasso", "collegat", "dossier", "archivio", "quello che ti ho detto")),
    "competenze": (("list_skills", "use_skill", "skill_save", "skill_delete"), ("competenza", "competenze", "skill", "playbook")),
    "pc": (("pc_*",), ("pc", "computer", "volume", "luminosità", "spegni", "riavvia", "blocca", "apri", "schermo", "musica", "riproduci", "pausa", "app", "programma", "file", "sposta", "cartella", "windows")),
    "notifiche": (("send_notification",), ("notifica", "notifiche", "manda un avviso", "avviso")),
    "token": (("get_token_budget",), ("token", "quota", "consumo", "budget", "limite")),
}
_STEMMED = {g: [" ".join(tokens(p)) for p in phrases] for g, (_, phrases) in GROUPS.items()}
_META = {
    "type": "function",
    "function": {
        "name": "need_tools",
        "description": "Attiva altri strumenti quando quelli disponibili non bastano (es. 'calendario', 'email', 'pc', 'web', 'liste', 'cervello', 'utilita', 'drive', 'promemoria', 'competenze', 'memoria', 'notifiche', 'token', 'notizie', 'coding'). Dopo averlo chiamato usa subito lo strumento che ti serviva.",
        "parameters": {"type": "object", "properties": {"group": {"type": "string", "enum": sorted(GROUPS)}}, "required": ["group"]},
    },
}


def _members(group: str, names: list[str]) -> set[str]:
    out = set()
    for pat in GROUPS[group][0]:
        out |= {n for n in names if (n.startswith(pat[:-1]) if pat.endswith("*") else n == pat)}
    return out


class ToolSelector:
    def groups_for(self, text: str, prior: list[str] | tuple[str, ...] = ()) -> set[str]:
        """Gruppi pertinenti: la richiesta e i due messaggi precedenti dell'utente (così «e domani?» mantiene il contesto)."""
        found: set[str] = set()
        for i, t in enumerate([text, *prior]):
            body = " " + " ".join(tokens(t)) + " "
            for g, phrases in _STEMMED.items():
                if g not in found and any(p and f" {p} " in body for p in phrases):
                    found.add(g)
            if i == 0 and len(found) >= 3:
                break
        return found

    def specs(self, all_specs: list[dict], groups: set[str]) -> list[dict]:
        names = [s["function"]["name"] for s in all_specs]
        grouped = set().union(*(_members(g, names) for g in GROUPS))
        allowed = CORE | set().union(*(_members(g, names) for g in groups)) if groups else set(CORE)
        chosen = [s for s in all_specs if s["function"]["name"] in allowed or s["function"]["name"] not in grouped and s["function"]["name"] not in CORE]
        hidden = [g for g in GROUPS if g not in groups and _members(g, names)]
        return chosen + ([_META] if hidden else [])

    def tools_of(self, all_specs: list[dict], group: str) -> list[str]:
        return sorted(_members(group, [s["function"]["name"] for s in all_specs])) if group in GROUPS else []
