"""Competenze di JARVIS: playbook da esperto (metodo, formato di risposta, errori da evitare) per ambiti come programmazione,
comunicazione, finanza, marketing. Si attivano da sole quando la richiesta le riguarda (poche righe nel prompt, zero chiamate in più)
oppure su richiesta (`use_skill`, `/skill`). La libreria integrata sta in `library/*.md`; quelle personali si salvano nel secondo cervello."""
from __future__ import annotations

import json
import logging
import math
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger("jarvis.skills")
LIBRARY = Path(__file__).parent / "library"
DOMAINS = {"programmazione": "Programmazione", "comunicazione": "Comunicazione", "finanza": "Finanza", "marketing": "Marketing",
           "grafica": "Grafica e design", "tecnologia": "Tecnologia", "business": "Lavoro e business", "vita": "Vita e crescita", "scienza": "Scienza e attualità", "personali": "Le mie competenze"}
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")
STOP = set("che con per una uno dei del della delle degli nel nella sul sulla non sono come anche piu pero ogni dove quando fare farmi fammi dammi voglio vorrei puoi potresti "
           "cosa cose qualcosa tutto tutti molto poco oggi domani ieri adesso ora sempre mai ancora gia qui qua quale quali perche quanto quanti quanta cosi bene male mio mia miei mie questo questa questi queste quello quella ciao jarvis mi ti ci vi lo gli le il la un di da in su tra fra e o a ho ha hai abbiamo sei".split())


def norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", (text or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def stem(w: str) -> str:
    """Radice grezza: senza vocale finale (lento/lenta, codice/codici) e al massimo 6 lettere (ottimizzo/ottimizzare, investimenti/investire)."""
    return (w[:-1] if len(w) > 4 and w[-1] in "aeiou" else w)[:6]


def tokens(text: str) -> list[str]:
    return [stem(w) for w in re.findall(r"[a-z0-9+#]+", norm(text))]


def stems(text: str) -> list[str]:
    """Radici delle parole significative (niente articoli, preposizioni e parole troppo comuni)."""
    return [stem(w) for w in re.findall(r"[a-z0-9+#]{3,}", norm(text)) if w not in STOP]


@dataclass
class Skill:
    name: str
    title: str
    domain: str
    description: str
    triggers: list[str]
    body: str
    builtin: bool = True
    _t: set[str] = field(default_factory=set, repr=False)  # parole del titolo
    _d: set[str] = field(default_factory=set, repr=False)  # parole della descrizione
    _phr: list[str] = field(default_factory=list, repr=False)  # frasi di attivazione normalizzate

    def __post_init__(self) -> None:
        self._t = set(stems(f"{self.title} {self.name.replace('-', ' ')}"))
        self._d = set(stems(self.description))
        self._phr = [" ".join(tokens(t)) for t in self.triggers if t.strip()]  # frasi come sequenze di radici

    def card(self) -> dict:
        return {"name": self.name, "title": self.title, "domain": self.domain, "description": self.description, "builtin": self.builtin}


def parse_block(block: str, builtin: bool = True) -> Skill | None:
    """Un blocco: righe `chiave: valore` (name, title, domain, description, triggers), riga vuota, poi il testo della competenza."""
    head, _, body = block.strip().partition("\n\n")
    meta: dict[str, str] = {}
    for line in head.splitlines():
        k, sep, v = line.partition(":")
        if sep:
            meta[k.strip().lower()] = v.strip()
    name = meta.get("name", "")
    if not (SLUG.match(name) and meta.get("description") and body.strip()):
        return None
    return Skill(name, meta.get("title") or name.replace("-", " ").capitalize(), meta.get("domain", "personali" if not builtin else "vita"), meta["description"],
                 [t.strip() for t in meta.get("triggers", "").split(",") if t.strip()], body.strip(), builtin)


class SkillRegistry:
    def __init__(self, library: Path = LIBRARY):
        self.skills: dict[str, Skill] = {}
        self._df: dict[str, int] = {}
        for path in sorted(library.glob("*.md")):
            for block in re.split(r"^@@@\s*$", path.read_text(encoding="utf-8"), flags=re.M):
                if block.strip():
                    sk = parse_block(block)
                    if sk:
                        self.skills[sk.name] = sk
                    else:
                        log.warning("competenza non valida in %s: %s", path.name, block.strip()[:50])
        self._reindex()

    def _reindex(self) -> None:
        self._df = {}
        for s in self.skills.values():
            for w in s._t | s._d:
                self._df[w] = self._df.get(w, 0) + 1

    def __len__(self) -> int:
        return len(self.skills)

    def get(self, name: str) -> Skill | None:
        key = norm(name).strip().replace(" ", "-")
        if key in self.skills:
            return self.skills[key]
        by_title = [s for s in self.skills.values() if norm(s.title) == norm(name).strip()]
        if by_title:
            return by_title[0]
        near = [s for s in self.skills.values() if key and (key in s.name or s.name in key)]
        return near[0] if len(near) == 1 else None

    def by_domain(self, domain: str = "") -> list[Skill]:
        d = norm(domain).strip()
        return [s for s in self.skills.values() if not d or s.domain == d or norm(DOMAINS.get(s.domain, "")) == d]

    def add_custom(self, sk: Skill) -> None:
        self.skills[sk.name] = sk
        self._reindex()

    def remove(self, name: str) -> bool:
        sk = self.skills.get(name)
        if not sk or sk.builtin:
            return False
        del self.skills[name]
        self._reindex()
        return True

    def score(self, s: Skill, text_norm: str, words: set[str]) -> float:
        n = max(1, len(self.skills))
        sc, hit = 0.0, False
        for p in s._phr:  # una frase di attivazione presente nella richiesta pesa molto; più lunga = più specifica
            if p and f" {p} " in text_norm:
                sc += 3.0 + 0.4 * min(3, p.count(" "))
                hit = True
        t_hit, d_hit = words & s._t, words & s._d
        for w in t_hit:
            sc += 1.2 * math.log(1 + n / self._df.get(w, 1))
        for w in d_hit:
            sc += 0.5 * math.log(1 + n / self._df.get(w, 1))
        # senza una frase di attivazione servono 2+ parole in comune (una almeno del titolo) o 3+ della descrizione: una sola («tempo», «prezzo») è troppo vaga
        return sc if hit or (t_hit and len(t_hit | d_hit) >= 2) or len(d_hit) >= 3 else 0.0

    def match(self, text: str, k: int = 2, min_score: float = 3.0) -> list[Skill]:
        """Le competenze più adatte alla richiesta (al massimo `k`). Soglia alta: le chiacchiere non ne attivano nessuna."""
        tn = " " + " ".join(tokens(text)) + " "
        words = set(stems(text))
        if not words:
            return []
        ranked = sorted(((self.score(s, tn, words), s) for s in self.skills.values()), key=lambda x: -x[0])
        top = [(sc, s) for sc, s in ranked if sc >= min_score][:k]
        if len(top) == 2 and top[1][0] < 0.6 * top[0][0]:  # la seconda conta solo se quasi pertinente quanto la prima
            top = top[:1]
        return [s for _, s in top]

    def context(self, skills: list[Skill], budget: int = 2400) -> str:
        """Il blocco per il prompt: istruzioni delle competenze attive, nel limite di caratteri (divise equamente)."""
        if not skills:
            return ""
        each = max(600, budget // len(skills))
        parts = []
        for s in skills:
            body = s.body if len(s.body) <= each else s.body[:each].rsplit("\n", 1)[0] + "\n[…usa use_skill per il metodo completo]"
            parts.append(f"## {s.title}\n{body}")
        return "Competenze specialistiche attive: segui questo metodo, adattandolo alla richiesta (non nominarle all'utente, a meno che lo chieda).\n\n" + "\n\n".join(parts)

    def catalog(self) -> str:
        by: dict[str, list[str]] = {}
        for s in self.skills.values():
            by.setdefault(s.domain, []).append(s.name)
        return "; ".join(f"{DOMAINS.get(d, d)}: {', '.join(sorted(n))}" for d, n in by.items())

    # ------------------------------------------------------------------ competenze personali (nel secondo cervello)
    @staticmethod
    def to_json(sk: Skill) -> str:
        return json.dumps({"name": sk.name, "title": sk.title, "description": sk.description, "triggers": sk.triggers, "body": sk.body}, ensure_ascii=False)

    async def load_custom(self, brain) -> int:
        """Rilegge le competenze personali salvate (documenti `skill` del secondo cervello, cifrati come tutto il resto)."""
        if not (brain and brain.enabled):
            return 0
        n = 0
        for d in await brain.store.list_docs(200, source="skill"):
            text = "\n\n".join(c.text for c in await brain.store.doc_chunks(d.id))
            try:
                j = json.loads(text[text.index("{"):])
            except (ValueError, json.JSONDecodeError):
                continue
            name = str(j.get("name", ""))
            if SLUG.match(name) and name not in self.skills and j.get("body") and j.get("description"):
                self.skills[name] = Skill(name, str(j.get("title") or name), "personali", str(j["description"]), [str(t) for t in j.get("triggers", [])], str(j["body"]), False)
                n += 1
        if n:
            self._reindex()
        return n
