"""Economia del contesto, per tutti i modelli: si manda ciò che serve alla richiesta, non tutto ciò che si ha.

Stessa idea di Graphify (interrogare un sottoinsieme mirato invece di rileggere tutto), applicata ai messaggi che vanno ai modelli:
- i risultati dei tool troppo lunghi si accorciano (inizio e fine);
- i turni vecchi si riducono a una riga e i giri di tool conclusi a un riassunto di una riga (senza mai spezzare la coppia chiamata/risultato);
- i blocchi facoltativi del prompt (competenze, profilo, cervello…) si tolgono dal meno al più importante;
- come ultima risorsa si riducono gli strumenti offerti.
Il tetto dipende dal profilo e si restringe da solo quando un provider risponde «richiesta troppo grande» (limiti di token al minuto dei piani gratuiti)."""
import json
import re

from .usage import est_tokens

TOOL_CAP = 2600  # caratteri massimi di un risultato di tool inviato al modello
OLD_TURN = 260  # caratteri conservati dei turni vecchi
BUDGET = {"auto:fast": 5200}  # i provider veloci gratuiti hanno i limiti più stretti (es. 7000 token al minuto)
DEFAULT_BUDGET = 9000
FLOOR = 1400

TOO_LARGE = re.compile(r"too large|request too big|context.{0,20}(length|window)|maximum context|reduce (your|the) (message|prompt|input)|tokens? per minute|\bTPM\b|\bITPM\b|payload too large|exceeds? the (model|limit)", re.I)
BAD_TOOLS = re.compile(r"tool|function[_ ]call|tool_choice|schema|parameters?", re.I)
GONE = re.compile(r"no longer available|not found|does not exist|deprecated|decommission|unknown model|invalid model|model.{0,20}(unavailable|not supported)", re.I)


def classify_error(status: int, body: str = "") -> str:
    """Categoria dell'errore da riparare (mai il testo: nel corpo possono esserci pezzi del prompt)."""
    body = body or ""
    if status == 413 or (status in (400, 422, 429) and TOO_LARGE.search(body)):
        return "too_large"
    if status == 404 or (status in (400, 422) and GONE.search(body)):
        return "model_gone"
    if status in (400, 422) and BAD_TOOLS.search(body):
        return "bad_tools"
    if status in (401, 403):
        return "auth"
    if status in (400, 422):
        return "bad_request"
    return "retry"


def tokens_of(messages: list[dict], tools: list[dict] | None = None) -> int:
    n = sum(est_tokens(str(m.get("content") or "")) + 4 + sum(est_tokens(json.dumps(c.get("function", {}))) for c in m.get("tool_calls") or []) for m in messages)
    return n + (est_tokens(json.dumps(tools)) if tools else 0)


def cap_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    head, tail = int(limit * 0.7), int(limit * 0.25)
    return f"{text[:head]}\n[…{len(text) - head - tail} caratteri omessi…]\n{text[-tail:]}"


def _digest(msg: dict) -> str:
    return " ".join(str(msg.get("content") or "").split())[:OLD_TURN]


def _groups(messages: list[dict]) -> list[list[dict]]:
    """Messaggi raggruppati in blocchi indivisibili: un assistente con chiamate di tool resta unito ai suoi risultati."""
    out: list[list[dict]] = []
    for m in messages:
        if m.get("role") == "tool" and out:
            out[-1].append(m)
        else:
            out.append([m])
    return out


def _summarize_group(g: list[dict]) -> dict:
    if len(g) > 1 or g[0].get("tool_calls"):
        names = ", ".join(c["function"]["name"] for c in g[0].get("tool_calls") or []) or "strumenti"
        res = " | ".join(_digest(m)[:90] for m in g[1:])
        return {"role": "assistant", "content": f"[Già fatto: {names} → {res}]"[:OLD_TURN + 60]}
    return {**g[0], "content": _digest(g[0])}


def fit(messages: list[dict], tools: list[dict] | None, budget: int, core_tools: set[str] | None = None) -> tuple[list[dict], list[dict] | None, int]:
    """Porta messaggi e strumenti dentro `budget` token. Ritorna (messaggi puliti, strumenti, token risparmiati). Sotto il tetto non cambia nulla."""
    before = tokens_of(messages, tools)
    opt = [b for b in (messages[0].get("_opt") if messages and messages[0].get("role") == "system" else None) or [] if b]
    msgs = [{k: v for k, v in m.items() if k != "_opt"} for m in messages]
    if before <= budget:
        return msgs, tools, 0
    # 1) risultati di tool lunghi
    msgs = [{**m, "content": cap_text(str(m["content"]), TOOL_CAP)} if m.get("role") == "tool" and isinstance(m.get("content"), str) else m for m in msgs]
    if tokens_of(msgs, tools) <= budget:
        return msgs, tools, before - tokens_of(msgs, tools)
    # 2) blocchi facoltativi del prompt, dal meno importante (gli ultimi aggiunti) al più
    system = msgs[0]
    if system.get("role") == "system":
        content = str(system["content"])
        for block in reversed(opt):
            if block and block in content:
                content = content.replace(block, "", 1).rstrip()
                msgs[0] = {**system, "content": content}
                if tokens_of(msgs, tools) <= budget:
                    return msgs, tools, before - tokens_of(msgs, tools)
    # 3) turni vecchi ridotti a una riga, dal più vecchio; l'ultimo messaggio dell'utente e l'ultimo giro di tool restano interi
    head = msgs[:1] if msgs and msgs[0].get("role") == "system" else []
    body = _groups(msgs[len(head):])
    last_user = max((i for i, g in enumerate(body) if g[0].get("role") == "user"), default=len(body) - 1)
    for i in range(len(body)):
        if i >= last_user:
            break
        body[i] = [_summarize_group(body[i])]
        if tokens_of(head + [m for g in body for m in g], tools) <= budget:
            break
    msgs = head + [m for g in body for m in g]
    # 4) ancora troppo: si buttano i turni vecchi più lontani (mai l'ultima domanda dell'utente né l'ultimo giro di tool)
    while tokens_of(msgs, tools) > budget:
        gs = _groups(msgs[len(head):])
        keep_user = max((i for i, g in enumerate(gs) if g[0].get("role") == "user"), default=len(gs) - 1)
        drop = next((i for i in range(len(gs) - 1) if i != keep_user), None)
        if drop is None:
            break
        msgs = head + [m for i, g in enumerate(gs) if i != drop for m in g]
    if tools and tokens_of(msgs, tools) > budget:
        keep = core_tools or set()
        slim = [t for t in tools if t["function"]["name"] in keep or t["function"]["name"] == "need_tools"]
        tools = slim or tools[:6]
    if tokens_of(msgs, tools) > budget and head:  # estrema: il prompt di sistema stesso si accorcia
        msgs[0] = {**msgs[0], "content": cap_text(str(msgs[0]["content"]), max(2400, budget * 2))}
    return msgs, tools, max(0, before - tokens_of(msgs, tools))


class ContextBudget:
    """Tetto di token per profilo, appreso: si restringe quando un provider rifiuta per dimensione e si riallarga piano piano."""

    def __init__(self, default: int = DEFAULT_BUDGET):
        self.default = default
        self.scale: dict[str, float] = {}
        self.saved = 0  # token risparmiati in totale (per lo stato)

    def for_profile(self, profile: str) -> int:
        base = BUDGET.get(profile, self.default) if self.default == DEFAULT_BUDGET else self.default
        return max(FLOOR, int(base * self.scale.get(profile, 1.0)))

    def too_large(self, profile: str, sent: int = 0) -> int:
        """Un provider ha rifiutato per dimensione: il nuovo tetto è il 60% del precedente, e comunque il 60% di ciò che era stato inviato."""
        base = max(1, BUDGET.get(profile, self.default) if self.default == DEFAULT_BUDGET else self.default)
        new = self.for_profile(profile) * 0.6
        if sent:
            new = min(new, sent * 0.6)
        self.scale[profile] = max(0.15, new / base)
        return self.for_profile(profile)

    def ok(self, profile: str) -> None:
        if (s := self.scale.get(profile, 1.0)) < 1.0:
            self.scale[profile] = min(1.0, s + 0.03)  # recupero lento dopo ogni risposta riuscita
