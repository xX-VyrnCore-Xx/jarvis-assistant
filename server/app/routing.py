"""Scelta del modello per ogni richiesta. FreeLLMAPI offre profili di instradamento (`auto:fast`, `auto:smart`, `auto:reliable`, `auto:balanced`)
e un'indicazione sul tipo di lavoro (`X-FreeLLM-Task-Type`): qui si sceglie quello giusto in base a ciò che si sta chiedendo, e si impara
dall'esito: un profilo che fallisce di continuo viene saltato per qualche minuto. Nessuna chiamata in più al modello."""
import re
import time
from dataclasses import dataclass

FAST, SMART, RELIABLE, BALANCED = "auto:fast", "auto:smart", "auto:reliable", "auto:balanced"
CHAIN = {SMART: (BALANCED, RELIABLE), RELIABLE: (BALANCED, FAST), FAST: (BALANCED, RELIABLE), BALANCED: (RELIABLE, FAST)}
BACKGROUND_FAST = {"learn", "enrich", "rag"}  # estrazioni brevi: la velocità conta più della finezza
BACKGROUND_QUALITY = {"journal", "profile"}  # testi lunghi da riassumere bene
BAD_AFTER, BAD_FOR_S, WINDOW_S = 3, 300, 600

CODE = re.compile(r"```|^\s*(def|class|import|from|function|const|let|var|public|private|fn|SELECT|CREATE|INSERT)\b|Traceback|\bat \S+\(\S+:\d+|\b\w+\.(py|js|ts|tsx|rs|go|java|kt|cpp|c|sql|yml|yaml|json|html|css)\b(:\d+)?|"
                  r"\b(codice|script|funzione|bug|errore di compilazione|compila|refactor|repository|repo|commit|pull request|branch|merge|api|endpoint|database|query|deploy|docker|test unitari|sandbox|programma|implementa)\b", re.I | re.M)
SIMPLE = re.compile(r"\b(traduci|traduzione|riassumi|riassunto|correggi|riformula|elenca|sinonimi|che ore|quanto fa|converti|definizione di|significa)\b", re.I)
THINK = re.compile(r"\b(analizza|analisi|confronta|strategia|dimostra|ragiona|pro e contro|spiega in dettaglio|approfondisci|progetta|architettura|pianifica|valuta|ottimizza|perché|motiva|passo per passo|business plan)\b", re.I)


@dataclass
class Route:
    model: str
    task: str  # code | chat | auto
    profile: str
    reason: str


def _last(messages: list[dict], role: str) -> str:
    for m in reversed(messages):
        if m.get("role") == role and isinstance(m.get("content"), str):
            return m["content"]
    return ""


class Router:
    def __init__(self) -> None:
        self.stats: dict[str, dict] = {}
        self.last: Route | None = None

    # ------------------------------------------------------------------ scelta
    def classify(self, messages: list[dict], tools: bool, kind: str) -> tuple[str, str, str]:
        if kind in BACKGROUND_FAST:
            return FAST, "chat", "lavoro di fondo"
        if kind in BACKGROUND_QUALITY:
            return BALANCED, "chat", "riassunto lungo"
        text = _last(messages, "user")
        system = _last(messages[:1], "system")
        coding = bool(CODE.search(text)) or "Sessione di coding attiva" in system
        deep = bool(THINK.search(text)) or len(text) > 450 or text.count("?") >= 3
        spoken = "LETTA AD ALTA VOCE" in system  # risposta parlata: la latenza conta più della finezza
        big = sum(len(str(m.get("content") or "")) for m in messages) // 4 > 4500  # i profili veloci hanno i limiti di token più stretti
        followup = bool(messages) and messages[-1].get("role") == "tool"  # si sta proseguendo un giro di strumenti: affidabilità prima di tutto
        if coding:
            return SMART, "code", "codice"
        if tools and deep:
            return SMART, "auto", "ragionamento con strumenti"
        if tools:
            return RELIABLE, "auto", "continuazione dei strumenti" if followup else "chiamata di strumenti"
        if deep:
            return SMART, "chat", "ragionamento"
        if spoken and not big:
            return FAST, "chat", "risposta parlata"
        if SIMPLE.search(text) and len(text) <= 600 and not big:
            return FAST, "chat", "compito semplice"
        if len(text) <= 120 and not big:
            return FAST, "chat", "richiesta breve"
        return BALANCED, "chat", "contesto ampio" if big else "richiesta normale"

    def usable(self, profile: str, now: float | None = None) -> bool:
        return self.stats.get(profile, {}).get("bad_until", 0) <= (now or time.monotonic())

    def pick(self, messages: list[dict], tools: bool = False, kind: str = "chat") -> Route:
        profile, task, why = self.classify(messages, tools, kind)
        if not self.usable(profile):  # profilo in difficoltà: il primo della catena che sta funzionando
            for alt in CHAIN[profile]:
                if self.usable(alt):
                    profile, why = alt, f"{why} (ripiego)"
                    break
        self.last = Route(profile, task, profile, why)
        return self.last

    def fallback(self, route: Route, attempt: int) -> str:
        """Profilo per il tentativo successivo: affidabile alla seconda, equilibrato alla terza."""
        return RELIABLE if attempt == 1 and route.profile != RELIABLE else BALANCED

    # ------------------------------------------------------------------ apprendimento dall'esito
    def report(self, profile: str, ok: bool, ms: float = 0.0, now: float | None = None) -> None:
        now = now or time.monotonic()
        s = self.stats.setdefault(profile, {"ok": 0, "fail": 0, "ms": 0.0, "recent_fail": [], "bad_until": 0.0})
        if ok:
            s["ok"] += 1
            s["ms"] = ms if not s["ms"] else 0.8 * s["ms"] + 0.2 * ms
            s["recent_fail"] = []
            return
        s["fail"] += 1
        s["recent_fail"] = [t for t in s["recent_fail"] if now - t < WINDOW_S] + [now]
        if len(s["recent_fail"]) >= BAD_AFTER:
            s["bad_until"], s["recent_fail"] = now + BAD_FOR_S, []

    def report_error(self, profile: str, category: str) -> None:
        """Errori di categoria nota (richiesta troppo grande, strumenti rifiutati…): si contano a parte, senza mettere il profilo in castigo."""
        s = self.stats.setdefault(profile, {"ok": 0, "fail": 0, "ms": 0.0, "recent_fail": [], "bad_until": 0.0})
        s.setdefault("errors", {})
        s["errors"][category] = s["errors"].get(category, 0) + 1

    def summary(self) -> dict:
        return {p: {"ok": s["ok"], "fail": s["fail"], "avg_ms": int(s["ms"]), **({"errors": s["errors"]} if s.get("errors") else {})} for p, s in self.stats.items()}
