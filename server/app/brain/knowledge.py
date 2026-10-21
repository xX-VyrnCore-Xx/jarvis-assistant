"""Conoscenza di base del mondo per il secondo cervello: voci essenziali di Wikipedia, caricate poco alla volta in secondo piano
(nessun token spesi: solo embedding) e, a richiesta, qualsiasi argomento (`brain_learn`). Sono fonti esterne: dati, mai istruzioni."""
import logging
import re

import httpx

from ..config import Settings

log = logging.getLogger("jarvis.knowledge")
API = "https://{lang}.wikipedia.org/w/api.php"
SETTING = "knowledge_seed_pos"
HEADERS = {"User-Agent": "JARVIS-personal-assistant/0.6 (https://github.com/xX-VyrnCore-Xx/jarvis-assistant)"}

# (categoria, [voci di Wikipedia in italiano]). L'ordine conta: le prime categorie sono quelle che servono di più.
SEED: list[tuple[str, list[str]]] = [
    ("Italia", ["Italia", "Costituzione della Repubblica Italiana", "Regioni d'Italia", "Storia d'Italia", "Roma", "Milano", "Napoli", "Torino",
                "Unione europea", "Euro", "Sistema sanitario nazionale (Italia)", "Imposta sul valore aggiunto", "Imposta sul reddito delle persone fisiche",
                "Codice fiscale", "Servizio sanitario", "Numero unico di emergenza 112", "Parlamento italiano", "Presidente della Repubblica Italiana"]),
    ("Geografia", ["Terra", "Europa", "Asia", "Africa", "America del Nord", "America del Sud", "Oceania", "Antartide", "Oceano Atlantico", "Oceano Pacifico",
                   "Mar Mediterraneo", "Alpi", "Appennini", "Po (fiume)", "Himalaya", "Nilo", "Amazzonia", "Fuso orario", "Latitudine", "Clima"]),
    ("Paesi", ["Stati Uniti d'America", "Cina", "India", "Giappone", "Germania", "Francia", "Regno Unito", "Spagna", "Russia", "Brasile", "Canada", "Australia",
               "Svizzera", "Grecia", "Turchia", "Egitto", "Messico", "Argentina", "Corea del Sud", "Paesi Bassi", "Portogallo", "Austria", "Polonia", "Ucraina",
               "Stato (diritto)", "Organizzazione delle Nazioni Unite", "NATO", "Unione europea"]),
    ("Scienza", ["Fisica", "Chimica", "Biologia", "Matematica", "Astronomia", "Sistema solare", "Sole", "Luna", "Marte (astronomia)", "Via Lattea", "Big Bang",
                 "Gravità", "Energia", "Elettricità", "Atomo", "Tavola periodica degli elementi", "Molecola", "Acqua", "DNA", "Cellula", "Evoluzione biologica",
                 "Teoria della relatività", "Meccanica quantistica", "Scienza", "Metodo scientifico", "Cambiamento climatico", "Energia rinnovabile", "Vaccino",
                 "Virus", "Batterio", "Sistema immunitario", "Cuore", "Cervello umano", "Sistema digerente", "Vitamina", "Alimentazione", "Sonno"]),
    ("Matematica e unità", ["Numero primo", "Frazione (matematica)", "Percentuale", "Probabilità", "Statistica", "Geometria", "Algebra", "Sistema internazionale di unità di misura",
                            "Interesse (economia)", "Interesse composto"]),
    ("Storia", ["Preistoria", "Antico Egitto", "Antica Grecia", "Impero romano", "Medioevo", "Rinascimento", "Rivoluzione francese", "Rivoluzione industriale",
                "Prima guerra mondiale", "Seconda guerra mondiale", "Guerra fredda", "Risorgimento", "Unità d'Italia", "Fascismo", "Resistenza italiana",
                "Repubblica Italiana", "Caduta del muro di Berlino", "Storia di Internet", "Illuminismo", "Colonialismo"]),
    ("Economia e società", ["Economia", "Prodotto interno lordo", "Inflazione", "Banca centrale europea", "Borsa valori", "Obbligazione (finanza)", "Azione (finanza)",
                            "Fondo comune di investimento", "Mutuo", "Criptovaluta", "Bitcoin", "Impresa", "Contratto di lavoro", "Pensione", "Diritto", "Democrazia",
                            "Capitalismo", "Globalizzazione", "Sviluppo sostenibile"]),
    ("Tecnologia", ["Informatica", "Internet", "World Wide Web", "Intelligenza artificiale", "Apprendimento automatico", "Modello linguistico di grandi dimensioni",
                    "Algoritmo", "Sistema operativo", "Linux", "Microsoft Windows", "Android", "Python", "JavaScript", "Database", "Cloud computing",
                    "Crittografia", "Sicurezza informatica", "Password", "Autenticazione a due fattori", "Phishing", "Smartphone", "Batteria agli ioni di litio",
                    "Automobile elettrica", "Stampa 3D", "Blockchain", "Open source"]),
    ("Cultura", ["Letteratura", "Divina Commedia", "Dante Alighieri", "Leonardo da Vinci", "Michelangelo Buonarroti", "Galileo Galilei", "Albert Einstein",
                 "Isaac Newton", "Marie Curie", "Pittura", "Musica", "Cinema", "Filosofia", "Religione", "Mitologia greca", "Lingua italiana", "Lingua inglese",
                 "Calcio (sport)", "Giochi olimpici", "Cucina italiana", "Pizza", "Vino", "Caffè", "Olio d'oliva"]),
    ("Salute e vita pratica", ["Pronto soccorso", "Primo soccorso", "Febbre", "Influenza", "Diabete mellito", "Ipertensione arteriosa", "Antibiotico", "Allergia",
                               "Esercizio fisico", "Stress", "Meditazione", "Gestione del tempo", "Produttività", "Pianificazione finanziaria", "Risparmio"]),
    ("Programmazione e IA", ["Linguaggio di programmazione", "Struttura dati", "Programmazione orientata agli oggetti", "Programmazione funzionale", "Git", "GitHub",
                             "Docker", "Kubernetes", "Rust (linguaggio di programmazione)", "Go (linguaggio di programmazione)", "TypeScript", "SQL", "PostgreSQL",
                             "Application programming interface", "REST", "Hypertext Transfer Protocol", "Transmission Control Protocol", "Domain Name System",
                             "Rete neurale artificiale", "Apprendimento profondo", "Elaborazione del linguaggio naturale", "Visione artificiale", "Big data",
                             "Algoritmo di ordinamento", "Complessità computazionale"]),
    ("Sicurezza e crittografia", ["Crittografia asimmetrica", "Advanced Encryption Standard", "Transport Layer Security", "Funzione di hash", "Firma digitale", "Ransomware",
                                  "Malware", "Ingegneria sociale (sicurezza informatica)", "Virtual private network", "Firewall", "Regolamento generale sulla protezione dei dati"]),
    ("Spazio e fisica", ["Giove (astronomia)", "Saturno (astronomia)", "Stazione Spaziale Internazionale", "NASA", "Agenzia spaziale europea", "SpaceX",
                         "Buco nero", "Pianeta extrasolare", "Telescopio spaziale James Webb", "Eclissi", "Modello standard", "Bosone di Higgs",
                         "Termodinamica", "Elettromagnetismo", "Onda", "Fusione nucleare", "Energia nucleare", "Superconduttività", "Computer quantistico"]),
    ("Ambiente e natura", ["Ecosistema", "Biodiversità", "Fotosintesi clorofilliana", "Effetto serra", "Anidride carbonica", "Riscaldamento globale", "Accordo di Parigi sul clima",
                           "Terremoto", "Vulcano", "Maremoto", "Uragano", "Ciclo dell'acqua", "Inquinamento", "Economia circolare"]),
    ("Economia e finanza pratica", ["Banca", "Conto corrente", "Carta di credito", "Tasso di interesse", "Euribor", "Debito pubblico", "Spread (finanza)", "Borsa Italiana",
                                    "FTSE MIB", "S&P 500", "Exchange-traded fund", "Dividendo", "Diversificazione (finanza)", "Regime forfettario",
                                    "Partita IVA", "Trattamento di fine rapporto", "Fatturazione elettronica", "Bilancio d'esercizio", "Contabilità"]),
    ("Istituzioni e mondo", ["Consiglio dell'Unione europea", "Commissione europea", "Parlamento europeo", "Banca d'Italia", "Corte costituzionale (Italia)", "Governo italiano",
                             "G7", "G20", "Fondo monetario internazionale", "Banca mondiale", "Organizzazione mondiale della sanità", "Organizzazione mondiale del commercio",
                             "Brexit", "Medio Oriente", "Diritti umani", "Dichiarazione universale dei diritti umani"]),
    ("Arte, cultura e lingue", ["Storia dell'arte", "Impressionismo", "Barocco", "Architettura", "Romanzo", "Poesia", "Teatro", "Opera lirica", "Jazz", "Rock", "Fotografia",
                                "Fumetto", "Videogioco", "Linguistica", "Alfabeto", "Lingua spagnola", "Lingua tedesca", "Lingua francese", "Latino", "Etimologia"]),
    ("Corpo, mente e benessere", ["Anatomia umana", "Sistema nervoso", "Apparato cardiocircolatorio", "Apparato respiratorio", "Ormone", "Microbiota intestinale", "Dieta mediterranea",
                                  "Proteina", "Carboidrato", "Lipidi", "Psicologia", "Memoria (psicologia)", "Apprendimento", "Ansia", "Depressione", "Mindfulness", "Rianimazione cardiopolmonare"]),
]


def seed_titles() -> list[str]:
    seen: set[str] = set()
    out = []
    for _, titles in SEED:
        for t in titles:
            if t not in seen:
                seen.add(t)
                out.append(t)
    return out


class Knowledge:
    def __init__(self, settings: Settings, brain, store, client: httpx.AsyncClient | None = None):
        self.s, self.brain, self.store = settings, brain, store
        self._client = client or httpx.AsyncClient(timeout=20, headers=HEADERS, follow_redirects=True)

    async def _query(self, lang: str, params: dict) -> dict:
        r = await self._client.get(API.format(lang=lang), params={"format": "json", "formatversion": 2, **params})
        r.raise_for_status()
        return r.json()

    async def resolve(self, topic: str, lang: str = "it") -> str:
        """Dal testo libero al titolo della voce (ricerca di Wikipedia)."""
        r = await self._client.get(API.format(lang=lang), params={"action": "opensearch", "search": topic, "limit": 1, "format": "json"})
        r.raise_for_status()
        found = r.json()
        return found[1][0] if len(found) > 1 and found[1] else ""

    async def fetch(self, title: str, lang: str = "it", full: bool = False) -> tuple[str, str, str] | None:
        """(titolo, testo, indirizzo) di una voce; None se non esiste. `full` = fino a ~12.000 caratteri, altrimenti l'introduzione."""
        params = {"action": "query", "prop": "extracts|info", "inprop": "url", "explaintext": 1, "redirects": 1, "titles": title,
                  "exchars": 12000 if full else 4000}
        if not full:
            params["exintro"] = 1
        pages = (await self._query(lang, params)).get("query", {}).get("pages", [])
        if not pages or pages[0].get("missing") or not (pages[0].get("extract") or "").strip():
            return None
        p = pages[0]
        text = re.sub(r"\n{3,}", "\n\n", p["extract"]).strip()
        return p.get("title", title), text, p.get("fullurl", f"https://{lang}.wikipedia.org/wiki/{title.replace(' ', '_')}")

    async def learn(self, topic: str, lang: str = "it", full: bool = False, resolve: bool = True) -> dict:
        title = (await self.resolve(topic, lang) or topic) if resolve else topic
        got = await self.fetch(title, lang, full)
        if not got:
            return {"status": "non trovato", "doc_id": 0}
        name, text, url = got
        r = await self.brain.ingest(f"{name} (da Wikipedia)\n\n{text}", title=name, source="wiki", uri=f"wiki:{lang}:{name}", tags=["base", "enciclopedia"], importance=0.35)
        if r.get("doc_id") and r["status"] != "duplicato":
            await self.brain.store.update_doc(r["doc_id"], enriched=True)  # niente chiamate al modello per l'arricchimento
        return {**r, "title": name, "url": url, "chars": len(text)}

    async def seed_batch(self, n: int) -> int:
        """Carica le prossime `n` voci di base (la posizione è nel database: dopo un riavvio si riparte da dove si era arrivati)."""
        titles = seed_titles()
        try:
            pos = int(await self.store.get_setting(SETTING) or 0)
        except ValueError:
            pos = 0
        if pos >= len(titles) or n <= 0:
            return 0
        done = 0
        for t in titles[pos:pos + n]:
            try:
                r = await self.learn(t, resolve=False)
                done += r["status"] in ("creato", "aggiornato")
                if r["status"] == "non trovato":
                    log.info("conoscenza di base: voce «%s» non trovata, la salto", t)
            except Exception as e:  # Wikipedia irraggiungibile: si riprova al prossimo giro senza avanzare
                log.info("conoscenza di base rimandata: %s", type(e).__name__)
                return done
            pos += 1
            await self.store.set_setting(SETTING, str(pos))
        if pos >= len(titles):
            log.info("conoscenza di base completa: %d voci", len(titles))
        return done

    async def refresh_stale(self, n: int) -> int:
        """Riscarica a rotazione `n` voci enciclopediche già nel cervello: se Wikipedia è cambiata il testo si aggiorna (altrimenti nulla)."""
        if n <= 0:
            return 0
        docs = [d for d in await self.brain.store.list_docs(400, source="wiki") if d.uri.startswith("wiki:")]
        if not docs:
            return 0
        docs.sort(key=lambda d: d.id)
        try:
            pos = int(await self.store.get_setting("knowledge_refresh_pos") or 0)
        except ValueError:
            pos = 0
        changed = 0
        for i in range(min(n, len(docs))):
            d = docs[(pos + i) % len(docs)]
            _, lang, name = d.uri.split(":", 2)
            try:
                changed += (await self.learn(name, lang, resolve=False))["status"] == "aggiornato"
            except Exception as e:
                log.info("aggiornamento della voce «%s» rimandato: %s", name, type(e).__name__)
                break
        await self.store.set_setting("knowledge_refresh_pos", str((pos + n) % max(1, len(docs))))
        return changed

    async def progress(self) -> tuple[int, int]:
        try:
            pos = int(await self.store.get_setting(SETTING) or 0)
        except ValueError:
            pos = 0
        return min(pos, len(seed_titles())), len(seed_titles())
