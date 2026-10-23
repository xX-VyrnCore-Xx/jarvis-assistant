"""Lavori di coding in background: JARVIS lavora da solo sul server (anche con l'app chiusa) e avvisa quando ha finito.

Come funziona:
- Un lavoro è una richiesta di coding che gira in coda (uno alla volta: c'è una sola sandbox) con lo stesso agente della sezione Codice,
  senza nessuno che possa rispondere: decide da sé, pianifica, committa su un ramo, aspetta la CI e la corregge, apre la PR.
- Lo stato (passi, esito, riepilogo) è nel database: l'app lo mostra dal vivo e dopo un riavvio del server i lavori interrotti
  vengono segnalati (non spariscono in silenzio).
- Alla fine: notifica "code" (app aperte, push Android, Telegram secondo le preferenze) con l'esito e il riepilogo.
- Sul piano gratuito di Render il servizio si addormenta senza traffico: mentre un lavoro è in corso si fa un ping a se stesso
  per tenerlo sveglio."""
import asyncio
import json
import logging
import secrets
import time

import httpx

from .coding import CodingError

log = logging.getLogger("jarvis.codejobs")
MAX_KEEP = 25  # lavori ricordati
MAX_QUEUE = 4  # in coda o in corso contemporaneamente
MAX_STEPS = 60
MAX_SECONDS = 30 * 60

BG_PREFIX = (
    "LAVORO IN BACKGROUND. L'utente non è presente e non può rispondere: non fare domande, scegli tu con buon senso e dichiara le ipotesi nel riepilogo. "
    "Pianifica con code_plan, lavora a passi piccoli e committa spesso su un ramo di lavoro. Usa code_checkpoint prima dei cambiamenti rischiosi e code_lint dopo aver scritto codice. "
    "Dopo il commit apri la PR, attendi la CI (code_wait_checks) e se è rossa leggi i log (code_ci_logs) e correggi la causa vera, fino a 3 tentativi. "
    "Non creare né eliminare repository (servono conferme umane) e non unire la PR (code_merge) a meno che la richiesta lo dica esplicitamente. "
    "Chiudi con un riepilogo breve in italiano: cosa hai fatto, file toccati, PR e stato della CI, cosa resta da fare.\n\nRICHIESTA:\n"
)


class CodeJobs:
    def __init__(self, settings, store, agent, coding, notifier):
        self.s, self.store, self.agent, self.coding, self.notifier = settings, store, agent, coding, notifier
        self.jobs: dict[str, dict] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._gate = asyncio.Semaphore(1)  # una sola sandbox: i lavori vanno uno dopo l'altro
        self._keep: asyncio.Task | None = None
        self.loaded = False

    # ------------------------------------------------------------------ archivio
    async def load(self) -> None:
        """Rilegge i lavori salvati; quelli rimasti a metà per un riavvio del server si segnano come interrotti e si avvisa l'utente."""
        try:
            rows = json.loads(await self.store.get_setting("code_jobs") or "[]")
        except ValueError:
            rows = []
        self.jobs = {r["id"]: r for r in rows if isinstance(r, dict) and r.get("id")}
        broken = [j for j in self.jobs.values() if j["status"] in ("queued", "running")]
        for j in broken:
            j.update(status="interrupted", finished=time.time(), result=j.get("result") or "Il server si è riavviato mentre lavoravo: puoi rilanciare il lavoro.")
        self.loaded = True
        if broken:
            await self._save()
            self.notifier.sync("code_jobs")
            try:
                await self.notifier.push("code", "Lavoro di coding interrotto", f"«{broken[0]['title']}»: il server si è riavviato. Rilancialo dalla sezione Codice.", telegram=True,
                                         meta={"job_id": broken[0]["id"]})
            except Exception:  # noqa: BLE001
                log.exception("avviso di lavoro interrotto non consegnato")

    async def _save(self) -> None:
        rows = sorted(self.jobs.values(), key=lambda j: j["created"])[-MAX_KEEP:]
        self.jobs = {j["id"]: j for j in rows}
        try:
            await self.store.set_setting("code_jobs", json.dumps(rows, ensure_ascii=False))
        except Exception:  # noqa: BLE001
            log.exception("salvataggio dei lavori di coding non riuscito")

    # ------------------------------------------------------------------ vista
    @staticmethod
    def view(j: dict, full: bool = False) -> dict:
        out = {k: j.get(k) for k in ("id", "title", "status", "repo", "created", "started", "finished", "pr", "notify")}
        out["steps"] = (j.get("steps") or [])[-(MAX_STEPS if full else 3):]
        out["now"] = (j.get("steps") or [""])[-1] if j.get("steps") else ""
        out["result"] = j.get("result") or "" if full else (j.get("result") or "")[:300]
        if full:
            out["prompt"] = j.get("prompt", "")
        return out

    def listing(self) -> list[dict]:
        return [self.view(j) for j in sorted(self.jobs.values(), key=lambda j: j["created"], reverse=True)]

    @property
    def active(self) -> int:
        return sum(1 for j in self.jobs.values() if j["status"] in ("queued", "running"))

    def get(self, job_id: str) -> dict | None:
        j = self.jobs.get(job_id)
        return self.view(j, full=True) if j else None

    # ------------------------------------------------------------------ avvio e annullamento
    async def start(self, prompt: str, repo: str = "", model: str | None = None, skill: str = "", notify: bool = True, title: str = "") -> dict:
        prompt = (prompt or "").strip()
        if len(prompt) < 4:
            raise CodingError("Descrivi cosa deve fare il lavoro.")
        if self.active >= MAX_QUEUE:
            raise CodingError(f"Ci sono già {MAX_QUEUE} lavori in coda o in corso: aspetta che finisca o annulla uno.")
        if not self.coding.enabled:
            raise CodingError("Il coding non è attivo: manca GITHUB_TOKEN sul server.")
        job = {"id": secrets.token_hex(4), "title": (title or prompt.splitlines()[0])[:80], "prompt": prompt[:6000], "status": "queued", "repo": repo.strip(), "created": time.time(),
               "started": 0, "finished": 0, "steps": [], "result": "", "pr": 0, "notify": bool(notify), "model": model, "skill": skill}
        self.jobs[job["id"]] = job
        await self._save()
        self._tasks[job["id"]] = asyncio.create_task(self._run(job["id"]))
        self.notifier.sync("code")
        return self.view(job)

    async def cancel(self, job_id: str) -> bool:
        j = self.jobs.get(job_id)
        if not j or j["status"] not in ("queued", "running"):
            return False
        t = self._tasks.get(job_id)
        if t:
            t.cancel()
        return True

    # ------------------------------------------------------------------ esecuzione
    def _step(self, j: dict, text: str) -> None:
        if not text or (j["steps"] and j["steps"][-1] == text):
            return
        j["steps"].append(text[:140])
        del j["steps"][:-MAX_STEPS]
        self.notifier.sync("code_jobs")  # avviso leggero: le app aggiornano solo l'elenco dei lavori

    async def _run(self, job_id: str) -> None:
        j = self.jobs[job_id]
        status, result = "failed", ""
        try:
            async with self._gate:
                j.update(status="running", started=time.time())
                self._step(j, "Inizio")
                await self._save()
                self._ensure_keepalive()
                if j["repo"]:
                    self._step(j, f"Apro {j['repo']}")
                    await self.coding.resume(j["repo"])
                elif not self.coding.session:
                    raise CodingError("Nessun progetto aperto: apri un repository dalla sezione Codice (o indica il repository) e rilancia.")
                j["repo"] = self.coding.session.repo
                async with asyncio.timeout(MAX_SECONDS):
                    async for kind, data in self.agent.reply_stream(BG_PREFIX + j["prompt"], "code", model=j.get("model"), skills=[j["skill"]] if j.get("skill") else None, mode="code"):
                        if kind == "status":
                            self._step(j, data)
                        elif kind == "done":
                            result = data
                status = "done"
        except asyncio.CancelledError:
            status, result = "cancelled", "Lavoro annullato."
        except TimeoutError:
            status, result = "failed", f"Tempo scaduto ({MAX_SECONDS // 60} minuti): il lavoro fatto finora è nella sandbox/ramo; rilancia per continuare."
        except CodingError as e:
            status, result = "failed", str(e)
        except Exception as e:  # noqa: BLE001
            log.exception("lavoro di coding %s fallito", job_id)
            status, result = "failed", f"Errore: {str(e)[:200] or type(e).__name__}"
        finally:
            s = self.coding.session
            j.update(status=status, finished=time.time(), result=(result or j.get("result") or "")[:5000], pr=(s.pr if s and s.repo == j.get("repo") else 0))
            self._tasks.pop(job_id, None)
            await asyncio.shield(self._finish(j))

    async def _finish(self, j: dict) -> None:
        await self._save()
        self.notifier.sync("code_jobs")
        self.notifier.sync("code")  # la conversazione di coding ha il riepilogo del lavoro: le app la ricaricano
        if j["status"] == "cancelled" or not j.get("notify"):
            return
        ok = j["status"] == "done"
        mins = max(1, round((j["finished"] - j["started"]) / 60)) if j["started"] else 0
        head = f"{'✅' if ok else '⚠️'} Coding {'finito' if ok else 'non riuscito'}: {j['title']}"
        body = (j["result"] or "").strip().replace("\n", " ")[:260] + (f" · {mins} min" if mins else "") + (f" · PR #{j['pr']}" if j.get("pr") else "")
        try:
            await self.notifier.push("code", head, body, telegram=True, meta={"job_id": j["id"], "repo": j.get("repo", "")})
        except Exception:  # noqa: BLE001
            log.exception("notifica di fine lavoro non consegnata")

    # ------------------------------------------------------------------ tenere sveglio il servizio mentre si lavora
    def _ensure_keepalive(self) -> None:
        url = (self.s.public_url or self.s.render_external_url or "").rstrip("/")
        if url and (self._keep is None or self._keep.done()):
            self._keep = asyncio.create_task(self._ping(url + "/health"))

    async def _ping(self, url: str) -> None:
        async with httpx.AsyncClient(timeout=10) as c:
            while self.active:
                try:
                    await c.get(url)
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(240)
