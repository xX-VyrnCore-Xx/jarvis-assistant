"""Tool delle competenze: elenco, uso a richiesta, creazione e rimozione di competenze personali."""
import re

from ..tools import ToolRegistry
from .registry import DOMAINS, SLUG, Skill, SkillRegistry, norm


def register_skill_tools(reg: ToolRegistry, skills: SkillRegistry, brain=None) -> None:
    s = {"type": "string"}
    obj = lambda props, req=(): {"type": "object", "properties": props, "required": list(req)}  # noqa: E731

    async def list_skills(domain: str = "") -> str:
        rows = skills.by_domain(domain)
        if not rows:
            return f"Nessuna competenza per «{domain}». Ambiti: " + ", ".join(DOMAINS.values()) + "."
        return "\n".join(f"{x.name} — {x.title}: {x.description}" for x in rows)

    async def use_skill(name: str) -> str:
        sk = skills.get(name)
        if not sk:
            return "Competenza non trovata. Disponibili: " + skills.catalog()
        return f"# {sk.title}\n{sk.body}\n\nApplica questo metodo alla richiesta dell'utente (non citarlo se non serve)."

    async def skill_save(name: str, title: str, description: str, instructions: str, triggers: str = "") -> str:
        key = norm(name).strip().replace(" ", "-")
        if not SLUG.match(key):
            return "Errore: il nome deve essere di 2-41 caratteri: lettere minuscole, numeri e trattini."
        if (cur := skills.skills.get(key)) and cur.builtin:
            return "Errore: è il nome di una competenza integrata; scegline un altro."
        if not (brain and brain.enabled):
            return "Errore: le competenze personali si salvano nel secondo cervello, che è spento."
        if len(instructions.strip()) < 40 or len(instructions) > 6000 or not description.strip() or len(description) > 300:
            return "Errore: servono una descrizione (max 300 caratteri) e istruzioni di 40-6000 caratteri."
        trig = [t.strip() for t in re.split(r"[,;\n]", triggers) if t.strip()][:20]
        sk = Skill(key, title.strip()[:80] or key, "personali", description.strip(), trig, instructions.strip(), False)
        r = await brain.ingest(SkillRegistry.to_json(sk), title=f"Competenza: {sk.title}", source="skill", uri=f"skill:{key}", pinned=True, importance=0.9)
        if r.get("doc_id"):
            await brain.store.update_doc(r["doc_id"], enriched=True)
        skills.add_custom(sk)
        return f"Competenza «{sk.title}» salvata ({'aggiornata' if r['status'] == 'aggiornato' else 'nuova'}): si attiverà da sola quando la richiesta c'entra" + (" (parole chiave: " + ", ".join(trig) + ")." if trig else ".")

    async def skill_delete(name: str) -> str:
        key = norm(name).strip().replace(" ", "-")
        sk = skills.skills.get(key)
        if not sk:
            return "Errore: competenza non trovata."
        if sk.builtin:
            return "Errore: le competenze integrate non si eliminano."
        d = await brain.store.find_doc(uri_hash=brain.vault.blind(f"skill:{key}")) if brain else None
        if d:
            await brain.forget(d.id)
        skills.remove(key)
        return "Competenza eliminata."

    reg.register("list_skills", "Elenca le competenze specialistiche di JARVIS (programmazione, comunicazione, finanza, marketing, business, vita). 'domain' opzionale.",
                 obj({"domain": s}), list_skills)
    reg.register("use_skill", "Carica il metodo completo di una competenza (nome da list_skills) per seguirlo nella risposta. Usalo se serve più dettaglio di quello già nel contesto.",
                 obj({"name": s}, ["name"]), use_skill)
    reg.register("skill_save", "Crea o aggiorna una competenza personale dell'utente (un playbook riutilizzabile: metodo, formato, regole). Solo su sua richiesta. 'triggers' = parole/frasi che la attivano, separate da virgola.",
                 obj({"name": s, "title": s, "description": s, "instructions": s, "triggers": s}, ["name", "title", "description", "instructions"]), skill_save)
    reg.register("skill_delete", "Elimina una competenza personale (non quelle integrate). Solo su richiesta dell'utente.", obj({"name": s}, ["name"]), skill_delete)
