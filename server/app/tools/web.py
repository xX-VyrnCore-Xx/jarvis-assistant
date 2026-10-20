"""Tool su web e calcoli: lettura di pagine (con difese SSRF), meteo, calcolatrice sicura."""
import ast
import asyncio
import ipaddress
import math
import operator
import re
import socket
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx

from . import UNTRUSTED, ToolRegistry

MAX_BYTES = 1_500_000
MAX_TEXT = 6000

WMO = {0: "sereno", 1: "prevalentemente sereno", 2: "parzialmente nuvoloso", 3: "coperto", 45: "nebbia", 48: "nebbia con brina",
       51: "pioviggine leggera", 53: "pioviggine", 55: "pioviggine intensa", 61: "pioggia debole", 63: "pioggia", 65: "pioggia forte",
       66: "pioggia gelata", 67: "pioggia gelata forte", 71: "neve debole", 73: "neve", 75: "neve forte", 77: "granelli di neve",
       80: "rovesci deboli", 81: "rovesci", 82: "rovesci violenti", 85: "rovesci di neve", 86: "forti rovesci di neve",
       95: "temporale", 96: "temporale con grandine", 99: "temporale con forte grandine"}


class _Text(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "head", "template"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title = ""
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        if tag == "title":
            self._in_title = True
        if tag in ("p", "br", "div", "li", "h1", "h2", "h3", "tr"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip and data.strip():
            self.parts.append(data.strip() + " ")


def html_to_text(html: str) -> tuple[str, str]:
    p = _Text()
    p.feed(html)
    text = re.sub(r"[ \t]+", " ", "".join(p.parts))
    return p.title.strip(), re.sub(r"\n\s*\n+", "\n", text).strip()


def _public(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            return False
    return bool(infos)


async def fetch_page(url: str, client: httpx.AsyncClient) -> str:
    """Legge una pagina pubblica. Ogni salto (anche i reindirizzamenti) deve restare su indirizzi pubblici."""
    for _ in range(4):
        u = urlparse(url)
        if u.scheme not in ("http", "https") or not u.hostname:
            return "Errore: indirizzo non valido (solo http/https)."
        if not await asyncio.to_thread(_public, u.hostname):
            return "Errore: indirizzo non raggiungibile o non pubblico."
        async with client.stream("GET", url, headers={"User-Agent": "Mozilla/5.0 JARVIS", "Accept": "text/html,text/plain"},
                                 follow_redirects=False) as r:
            if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                url = urljoin(url, r.headers["location"])
                continue
            if r.status_code >= 400:
                return f"Errore: la pagina ha risposto {r.status_code}."
            ctype = r.headers.get("content-type", "")
            if ctype and not re.match(r"(text/|application/(xhtml|json|xml))", ctype):
                return f"Errore: tipo di contenuto non leggibile ({ctype.split(';')[0]})."
            raw = b""
            async for chunk in r.aiter_bytes():
                raw += chunk
                if len(raw) > MAX_BYTES:
                    break
            body = raw.decode(r.encoding or "utf-8", errors="replace")
        title, text = html_to_text(body) if "html" in ctype or body.lstrip().startswith("<") else ("", body)
        text = text[:MAX_TEXT]
        return UNTRUSTED + (f"Titolo: {title}\n" if title else "") + f"URL: {url}\n\n{text}"
    return "Errore: troppi reindirizzamenti."


_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow}
_FUNCS = {"sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan, "log": math.log, "log10": math.log10,
          "exp": math.exp, "abs": abs, "round": round, "min": min, "max": max, "floor": math.floor, "ceil": math.ceil}
_CONST = {"pi": math.pi, "e": math.e}


def calc(expr: str) -> float:
    def ev(n):
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
            a, b = ev(n.left), ev(n.right)
            if isinstance(n.op, ast.Pow) and (abs(b) > 1000 or abs(a) > 1e6):
                raise ValueError("potenza troppo grande")
            return _OPS[type(n.op)](a, b)
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
            return -ev(n.operand) if isinstance(n.op, ast.USub) else ev(n.operand)
        if isinstance(n, ast.Name) and n.id in _CONST:
            return _CONST[n.id]
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _FUNCS and not n.keywords:
            return _FUNCS[n.func.id](*[ev(a) for a in n.args])
        raise ValueError("espressione non consentita")

    return ev(ast.parse(expr.strip().replace("^", "**"), mode="eval").body)


def register_web_tools(reg: ToolRegistry, client: httpx.AsyncClient | None = None) -> None:
    http = client or httpx.AsyncClient(timeout=20)

    async def read_webpage(url: str) -> str:
        return await fetch_page(url, http)

    async def get_weather(city: str) -> str:
        g = await http.get("https://geocoding-api.open-meteo.com/v1/search", params={"name": city, "count": 1, "language": "it"})
        g.raise_for_status()
        hits = g.json().get("results") or []
        if not hits:
            return f"Nessuna località trovata per '{city}'."
        place = hits[0]
        w = await http.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": place["latitude"], "longitude": place["longitude"], "timezone": "auto", "forecast_days": 3,
            "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m,precipitation",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"})
        w.raise_for_status()
        j = w.json()
        c, d = j["current"], j["daily"]
        lines = [f"Meteo a {place['name']} ({place.get('country', '')}): {WMO.get(c['weather_code'], '—')}, {c['temperature_2m']:.0f}°C "
                 f"(percepiti {c['apparent_temperature']:.0f}°C), vento {c['wind_speed_10m']:.0f} km/h, precipitazioni {c['precipitation']} mm."]
        for i, day in enumerate(d["time"]):
            lines.append(f"- {day}: {WMO.get(d['weather_code'][i], '—')}, {d['temperature_2m_min'][i]:.0f}–{d['temperature_2m_max'][i]:.0f}°C, "
                         f"pioggia {d['precipitation_probability_max'][i]}%")
        return "\n".join(lines)

    async def calculate(expression: str) -> str:
        try:
            r = calc(expression)
        except ZeroDivisionError:
            return "Errore: divisione per zero."
        except (ValueError, SyntaxError, TypeError, OverflowError) as e:
            return f"Errore nel calcolo: {e}"
        return str(round(r, 10) if isinstance(r, float) else r)

    async def web_news(query: str) -> str:
        def _news() -> list[dict]:
            from ddgs import DDGS

            return DDGS().news(query, max_results=6, region="it-it")

        rows = await asyncio.to_thread(_news)
        body = "\n\n".join(f"{r.get('title')} ({r.get('source', '')}, {str(r.get('date', ''))[:10]})\n{r.get('url')}\n{r.get('body', '')}" for r in rows)
        return UNTRUSTED + body if body else "Nessuna notizia trovata."

    async def wikipedia(topic: str, lang: str = "it") -> str:
        if not re.fullmatch(r"[a-z]{2,3}", lang):
            return "Errore: lingua non valida."
        found = (await http.get(f"https://{lang}.wikipedia.org/w/api.php", params={"action": "opensearch", "search": topic, "limit": 1, "format": "json"})).json()
        if not found[1]:
            return f"Nessuna voce trovata per '{topic}'."
        r = await http.get(f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{found[1][0].replace(' ', '_')}")
        r.raise_for_status()
        j = r.json()
        return f"{UNTRUSTED}{j.get('title')}: {j.get('extract', '')[:MAX_TEXT]}\n{j.get('content_urls', {}).get('desktop', {}).get('page', '')}"

    async def convert_currency(amount: float, from_currency: str, to_currency: str) -> str:
        a, b = from_currency.upper(), to_currency.upper()
        if not (re.fullmatch(r"[A-Z]{3}", a) and re.fullmatch(r"[A-Z]{3}", b)):
            return "Errore: usa i codici a tre lettere (EUR, USD, GBP…)."
        r = await http.get("https://api.frankfurter.app/latest", params={"amount": amount, "from": a, "to": b})
        if r.status_code == 404:
            return "Valuta non supportata."
        r.raise_for_status()
        j = r.json()
        return f"{amount:g} {a} = {j['rates'][b]:g} {b} (cambio BCE del {j['date']})"

    s = {"type": "string"}
    reg.register("web_news", "Ultime notizie su un argomento.", {"type": "object", "properties": {"query": s}, "required": ["query"]}, web_news)
    reg.register("wikipedia", "Riassunto di una voce di Wikipedia (lingua predefinita: it). Per definizioni e fatti enciclopedici.",
                 {"type": "object", "properties": {"topic": s, "lang": {"type": "string", "description": "codice lingua, es. it, en"}}, "required": ["topic"]}, wikipedia)
    reg.register("convert_currency", "Converte un importo tra valute con il cambio BCE del giorno.",
                 {"type": "object", "properties": {"amount": {"type": "number"}, "from_currency": s, "to_currency": s}, "required": ["amount", "from_currency", "to_currency"]},
                 convert_currency)
    reg.register("read_webpage", "Legge il testo di una pagina web pubblica (http/https) dato l'URL, ad esempio un risultato di web_search.",
                 {"type": "object", "properties": {"url": s}, "required": ["url"]}, read_webpage)
    reg.register("get_weather", "Meteo attuale e previsioni dei prossimi 3 giorni per una città.",
                 {"type": "object", "properties": {"city": {"type": "string", "description": "Nome della città, es. Milano"}}, "required": ["city"]},
                 get_weather)
    reg.register("calculate", "Calcolatrice precisa: + - * / // % ^ , parentesi, sqrt, sin, cos, log, abs, round, pi. Usala per ogni calcolo.",
                 {"type": "object", "properties": {"expression": s}, "required": ["expression"]}, calculate)
