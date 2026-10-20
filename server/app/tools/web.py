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


async def fetch_page_data(url: str, client: httpx.AsyncClient) -> tuple[str, str, str] | str:
    """Legge una pagina pubblica: (titolo, testo, url finale) oppure un messaggio d'errore (str).
    Ogni salto (anche i reindirizzamenti) deve restare su indirizzi pubblici."""
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
        return title, text, url
    return "Errore: troppi reindirizzamenti."


async def fetch_page(url: str, client: httpx.AsyncClient) -> str:
    data = await fetch_page_data(url, client)
    if isinstance(data, str):
        return data
    title, text, final = data
    return UNTRUSTED + (f"Titolo: {title}\n" if title else "") + f"URL: {final}\n\n{text[:MAX_TEXT]}"


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


UNITS = {  # unità -> fattore verso l'unità base della categoria
    "length": {"mm": 0.001, "cm": 0.01, "m": 1, "km": 1000, "in": 0.0254, "ft": 0.3048, "yd": 0.9144, "mi": 1609.344, "nmi": 1852},
    "mass": {"mg": 1e-6, "g": 0.001, "kg": 1, "t": 1000, "oz": 0.028349523, "lb": 0.45359237},
    "volume": {"ml": 0.001, "cl": 0.01, "l": 1, "m3": 1000, "tsp": 0.00492892, "tbsp": 0.0147868, "cup": 0.236588, "gal": 3.78541, "floz": 0.0295735},
    "speed": {"ms": 1, "kmh": 1 / 3.6, "mph": 0.44704, "kn": 0.514444},
    "area": {"m2": 1, "km2": 1e6, "ha": 1e4, "ft2": 0.092903, "ac": 4046.86},
    "data": {"b": 1, "kb": 1e3, "mb": 1e6, "gb": 1e9, "tb": 1e12, "kib": 1024, "mib": 1024**2, "gib": 1024**3},
}
TEMP = {"c", "f", "k"}
COINS = {"btc": "bitcoin", "eth": "ethereum", "sol": "solana", "ada": "cardano", "xrp": "ripple", "doge": "dogecoin", "bnb": "binancecoin",
         "ltc": "litecoin", "dot": "polkadot", "usdt": "tether", "matic": "matic-network", "avax": "avalanche-2", "trx": "tron"}


def convert_units(value: float, a: str, b: str) -> str:
    a, b = a.lower().replace("°", "").replace("/", "").replace(" ", ""), b.lower().replace("°", "").replace("/", "").replace(" ", "")
    if a in TEMP and b in TEMP:
        c = value if a == "c" else (value - 32) * 5 / 9 if a == "f" else value - 273.15
        r = c if b == "c" else c * 9 / 5 + 32 if b == "f" else c + 273.15
        return f"{value:g} °{a.upper()} = {r:.2f} °{b.upper()}"
    for cat, table in UNITS.items():
        if a in table and b in table:
            return f"{value:g} {a} = {value * table[a] / table[b]:.6g} {b}"
    return "Errore: unità non riconosciute o di categorie diverse (supporto: lunghezza, massa, volume, velocità, area, dati, temperatura)."


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

    async def crypto_price(coin: str) -> str:
        ids = ",".join(COINS.get(c.strip().lower(), c.strip().lower()) for c in coin.split(",") if c.strip())[:120]
        if not re.fullmatch(r"[a-z0-9,-]+", ids or "-"):
            return "Errore: nome della criptovaluta non valido."
        r = await http.get("https://api.coingecko.com/api/v3/simple/price",
                           params={"ids": ids, "vs_currencies": "eur,usd", "include_24hr_change": "true"})
        if r.status_code == 429:
            return "Errore: servizio prezzi temporaneamente limitato, riprova tra un minuto."
        r.raise_for_status()
        data = r.json()
        if not data:
            return f"Nessuna criptovaluta trovata per '{coin}' (usa il nome esteso, es. bitcoin)."
        return "\n".join(f"{k}: {v.get('eur', 0):,.2f} € / {v.get('usd', 0):,.2f} $ ({v.get('eur_24h_change', 0):+.1f}% in 24 h)" for k, v in data.items())

    async def world_time(city: str) -> str:
        from datetime import datetime
        from zoneinfo import ZoneInfo

        g = await http.get("https://geocoding-api.open-meteo.com/v1/search", params={"name": city, "count": 1, "language": "it"})
        g.raise_for_status()
        hits = g.json().get("results") or []
        if not hits or not hits[0].get("timezone"):
            return f"Nessuna località trovata per '{city}'."
        now = datetime.now(ZoneInfo(hits[0]["timezone"]))
        return f"A {hits[0]['name']} ({hits[0]['timezone']}) sono le {now:%H:%M} di {now:%d/%m/%Y} (UTC{now:%z})."

    async def unit_convert(value: float, from_unit: str, to_unit: str) -> str:
        return convert_units(value, from_unit, to_unit)

    s = {"type": "string"}
    reg.register("crypto_price", "Prezzo attuale di una o più criptovalute (separate da virgola, es. 'btc, eth') in euro e dollari, con variazione a 24 h.",
                 {"type": "object", "properties": {"coin": s}, "required": ["coin"]}, crypto_price, cache_ttl=60)
    reg.register("world_time", "Ora attuale in una città del mondo.", {"type": "object", "properties": {"city": s}, "required": ["city"]}, world_time)
    reg.register("unit_convert", "Converte unità di misura (lunghezza, massa, volume, velocità, area, dati, temperatura): es. 5 mi -> km, 70 f -> c.",
                 {"type": "object", "properties": {"value": {"type": "number"}, "from_unit": s, "to_unit": s}, "required": ["value", "from_unit", "to_unit"]}, unit_convert)
    reg.register("web_news", "Ultime notizie su un argomento.", {"type": "object", "properties": {"query": s}, "required": ["query"]}, web_news, cache_ttl=900)
    reg.register("wikipedia", "Riassunto di una voce di Wikipedia (lingua predefinita: it). Per definizioni e fatti enciclopedici.",
                 {"type": "object", "properties": {"topic": s, "lang": {"type": "string", "description": "codice lingua, es. it, en"}}, "required": ["topic"]}, wikipedia, cache_ttl=86400)
    reg.register("convert_currency", "Converte un importo tra valute con il cambio BCE del giorno.",
                 {"type": "object", "properties": {"amount": {"type": "number"}, "from_currency": s, "to_currency": s}, "required": ["amount", "from_currency", "to_currency"]},
                 convert_currency, cache_ttl=3600)
    reg.register("read_webpage", "Legge il testo di una pagina web pubblica (http/https) dato l'URL, ad esempio un risultato di web_search.",
                 {"type": "object", "properties": {"url": s}, "required": ["url"]}, read_webpage, cache_ttl=900)
    reg.register("get_weather", "Meteo attuale e previsioni dei prossimi 3 giorni per una città.",
                 {"type": "object", "properties": {"city": {"type": "string", "description": "Nome della città, es. Milano"}}, "required": ["city"]},
                 get_weather, cache_ttl=600)
    reg.register("calculate", "Calcolatrice precisa: + - * / // % ^ , parentesi, sqrt, sin, cos, log, abs, round, pi. Usala per ogni calcolo.",
                 {"type": "object", "properties": {"expression": s}, "required": ["expression"]}, calculate)
