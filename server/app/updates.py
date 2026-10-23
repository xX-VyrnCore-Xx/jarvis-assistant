"""Aggiornamenti delle app: legge l'ultima Release di GitHub, indica il file giusto per piattaforma (con SHA-256) e avvisa in tempo reale."""
import re
import time

import httpx

from .config import Settings

API = "https://api.github.com/repos/{repo}/releases/latest"
LIST = "https://api.github.com/repos/{repo}/releases?per_page=12"
BY = re.compile(r"\s+by\s+@\S+(\s+in\s+\S+)?\s*$")


def parse_version(v: str) -> tuple[int, ...]:
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)", v or "")
    return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)


def highlights(body: str, limit: int = 8) -> list[str]:
    """Le novità di una Release in poche righe: i punti elenco dopo «What's Changed» (titoli delle PR) senza autore e link, mai le istruzioni di installazione."""
    out: list[str] = []
    for ln in (body or "").splitlines():
        t = ln.strip()
        if not t.startswith(("* ", "- ")) or "Full Changelog" in t:
            continue
        t = BY.sub("", t[2:]).strip().strip("*").strip()
        if t.startswith(("**Windows**", "**Android**")) or len(t) < 8:  # istruzioni di installazione
            continue
        out.append(re.sub(r"\s*\(#\d+\)$", "", t)[:160])
        if len(out) >= limit:
            break
    return out


class UpdateService:
    def __init__(self, settings: Settings, store, notifier, client: httpx.AsyncClient | None = None):
        self.s, self.store, self.notifier = settings, store, notifier
        self._client = client or httpx.AsyncClient(timeout=20)
        self._cache: tuple[float, dict | None] = (0.0, None)
        self._history: list[dict] = []  # Release precedenti (versione + novità), per mostrare tutto ciò che si perde saltando versioni
        self.last_check: float = 0.0
        self.last_error = ""

    @property
    def prefix(self) -> str:
        return f"https://github.com/{self.s.github_repo}/releases/download/"

    async def latest(self, force: bool = False) -> dict | None:
        if not force and self._cache[0] > time.monotonic():
            return self._cache[1]
        try:
            r = await self._client.get(API.format(repo=self.s.github_repo), headers={"Accept": "application/vnd.github+json", "User-Agent": "jarvis-assistant"})
            if r.status_code == 404:
                self._cache = (time.monotonic() + 600, None)
                return None
            r.raise_for_status()
            rel = r.json()
            sums: dict[str, str] = {}
            for a in rel.get("assets", []):
                if a["name"].lower().startswith("sha256sums") and a["browser_download_url"].startswith(self.prefix):
                    t = await self._client.get(a["browser_download_url"], follow_redirects=True)
                    for line in t.text.splitlines():
                        parts = line.split()
                        if len(parts) >= 2 and re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
                            sums[parts[-1].split("/")[-1].lstrip("*")] = parts[0].lower()
            assets = {}
            for a in rel.get("assets", []):
                url = a["browser_download_url"]
                if not url.startswith(self.prefix):  # solo file della Release di questo repository
                    continue
                name = a["name"]
                key = "android" if name.lower().endswith(".apk") else "windows" if name.lower().endswith(".exe") else None
                if key:
                    assets[key] = {"name": name, "url": url, "size": a.get("size", 0), "sha256": sums.get(name, "")}
            try:
                lr = await self._client.get(LIST.format(repo=self.s.github_repo), headers={"Accept": "application/vnd.github+json", "User-Agent": "jarvis-assistant"})
                if lr.status_code == 200 and isinstance(lr.json(), list):
                    self._history = [{"version": x["tag_name"].lstrip("v"), "highlights": highlights(x.get("body") or ""), "published_at": x.get("published_at", "")}
                                     for x in lr.json() if not x.get("draft") and not x.get("prerelease")]
            except (httpx.HTTPError, KeyError, ValueError, TypeError, AttributeError):
                pass  # la cronologia è un di più: l'aggiornamento resta valido
            out = {"version": rel["tag_name"].lstrip("v"), "tag": rel["tag_name"], "notes": (rel.get("body") or "")[:1500],
                   "published_at": rel.get("published_at", ""), "page": rel.get("html_url", ""), "assets": assets}
            self._cache = (time.monotonic() + 600, out)
            self.last_error = ""
            self.last_check = time.time()
            return out
        except (httpx.HTTPError, KeyError, ValueError) as e:
            self.last_error = type(e).__name__
            return self._cache[1]

    async def check_for(self, platform: str, current: str) -> dict:
        rel = await self.latest()
        asset = (rel or {}).get("assets", {}).get(platform)
        if not rel or not asset:
            return {"available": False, "current": current, "latest": rel["version"] if rel else current}
        newer = [h for h in self._history if parse_version(h["version"]) > parse_version(current)]
        return {"available": parse_version(rel["version"]) > parse_version(current), "current": current, "latest": rel["version"], "notes": rel["notes"],
                "published_at": rel["published_at"], "page": rel["page"], "behind": len(newer), "changes": newer[:8], **asset}

    async def poll_and_notify(self, force: bool = False) -> str:
        """Avvisa (una volta per versione) tutte le app quando compare una Release nuova."""
        rel = await self.latest(force=force)
        if not rel:
            return "nessuna release"
        seen = await self.store.get_setting("last_release_notified")
        if not seen:  # primo avvio del controllo: si fissa la versione attuale senza disturbare
            await self.store.set_setting("last_release_notified", rel["version"])
            return f"base {rel['version']}"
        if parse_version(rel["version"]) <= parse_version(seen):
            return "nessuna novità"
        await self.store.set_setting("last_release_notified", rel["version"])
        hl = highlights(rel["notes"], 3)
        notes = re.sub(r"[#*`]", "", rel["notes"]).strip().splitlines()
        body = ("; ".join(hl) if hl else (next((ln for ln in notes if len(ln) > 20), "") or "Nuove funzioni e correzioni."))[:200]
        await self.notifier.push("update", f"Aggiornamento disponibile: JARVIS {rel['version']}", body,
                                 meta={"version": rel["version"], "url": rel["assets"].get("android", {}).get("url") or rel["assets"].get("windows", {}).get("url", ""),
                                       "page": rel["page"]})
        return f"notificata {rel['version']}"
