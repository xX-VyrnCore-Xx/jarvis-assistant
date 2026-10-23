"""Controllo automatico degli strumenti che dipendono da servizi esterni (meteo, notizie, cambi, Wikipedia…).

Ogni giro prova una richiesta innocua per strumento. Dopo FAILS errori di fila lo strumento esce dall'elenco offerto ai modelli (così non si sprecano
turni su strumenti rotti) e l'utente riceve un avviso; appena una prova torna a riuscire rientra da solo e arriva l'avviso di ripristino."""
import asyncio
import json
import logging
import time

log = logging.getLogger("jarvis.toolwatch")

PROBES: dict[str, dict] = {
    "get_weather": {"city": "Roma"},
    "news_headlines": {},
    "wikipedia": {"topic": "Roma"},
    "crypto_price": {"coin": "bitcoin"},
    "convert_currency": {"amount": 1, "from_currency": "EUR", "to_currency": "USD"},
    "world_time": {"city": "Tokyo"},
    "web_search": {"query": "ultime notizie"},
}
FAILS = 2


def _bad(result: str) -> bool:
    r = (result or "").strip()
    return not r or r.startswith("Errore") or r.lower().startswith("nessun risultato")


class ToolWatch:
    def __init__(self, tools, notifier=None, probes: dict | None = None):
        self.tools, self.notifier = tools, notifier
        self.probes = probes if probes is not None else PROBES
        self.fails: dict[str, int] = {}
        self.status: dict[str, dict] = {}
        self.last_run = 0.0

    async def run(self) -> dict:
        """Prova tutti gli strumenti registrati che hanno una prova. Restituisce {nome: ok}."""
        out: dict[str, bool] = {}
        for name, args in self.probes.items():
            if name not in self.tools._tools:
                continue
            was_down = name in self.tools.down
            self.tools.down.pop(name, None)  # la prova deve poter girare anche su uno strumento messo da parte
            try:
                res = await self.tools.call(name, json.dumps(args))
            except Exception as e:
                res = f"Errore: {type(e).__name__}"
            ok = not _bad(res)
            out[name] = ok
            self.status[name] = {"ok": ok, "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "detail": "" if ok else res[:120]}
            if ok:
                self.fails[name] = 0
                if was_down:
                    log.info("strumento %s di nuovo disponibile", name)
                    await self._tell("Strumento ripristinato", f"{name} funziona di nuovo.")
            else:
                self.fails[name] = self.fails.get(name, 0) + 1
                if self.fails[name] >= FAILS:
                    self.tools.down[name] = res[:100]
                    if not was_down:
                        log.warning("strumento %s messo da parte: %s", name, res[:100])
                        await self._tell("Strumento fuori servizio", f"{name} non risponde ({res[:80]}). Lo escludo finché non torna a funzionare.")
                elif was_down:
                    self.tools.down[name] = res[:100]
            await asyncio.sleep(0)
        self.last_run = time.time()
        return out

    async def _tell(self, title: str, body: str) -> None:
        if self.notifier:
            try:
                await self.notifier.push("alert", title, body, telegram=False)
            except Exception:
                pass
