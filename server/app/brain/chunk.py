"""Suddivisione dei testi in frammenti coerenti per il recupero."""
import re

TARGET = 1200  # caratteri per frammento (~300 token)
MAX = 1800
OVERLAP = 180
HEADING = re.compile(r"^(#{1,6}\s+.+|[A-ZÀ-Ú0-9][^\n]{0,60}:\s*)$")


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _sections(text: str) -> list[tuple[str, str]]:
    """(titolo di sezione, corpo): il titolo viene ripetuto davanti a ogni frammento per dare contesto."""
    out: list[tuple[str, list[str]]] = [("", [])]
    for line in text.splitlines():
        if re.match(r"^#{1,6}\s+\S", line):
            out.append((re.sub(r"^#+\s*", "", line).strip(), []))
        else:
            out[-1][1].append(line)
    return [(h, "\n".join(b).strip()) for h, b in out if "\n".join(b).strip() or h]


def _split_long(paragraph: str) -> list[str]:
    """Un paragrafo troppo lungo si divide a fine frase."""
    if len(paragraph) <= MAX:
        return [paragraph]
    parts, cur = [], ""
    for s in re.split(r"(?<=[.!?;])\s+", paragraph):
        while len(s) > MAX:  # frase senza punteggiatura: taglio sugli spazi
            cut = s.rfind(" ", 0, MAX)
            cut = cut if cut > MAX // 2 else MAX
            parts.append((cur + " " + s[:cut]).strip()) if cur else parts.append(s[:cut].strip())
            cur, s = "", s[cut:].strip()
        if len(cur) + len(s) + 1 > TARGET and cur:
            parts.append(cur.strip())
            cur = ""
        cur = f"{cur} {s}".strip()
    if cur:
        parts.append(cur)
    return parts


def chunk_text(text: str, title: str = "") -> list[str]:
    """Frammenti di ~TARGET caratteri su confini di paragrafo, con sovrapposizione e titolo davanti."""
    text = re.sub(r"\r\n?", "\n", text).strip()
    if not text:
        return []
    chunks: list[str] = []
    for heading, body in _sections(text):
        prefix = " › ".join(p for p in (title, heading) if p)
        paras = [p for para in re.split(r"\n\s*\n", body) for p in _split_long(para.strip()) if p]
        cur = ""
        for p in paras:
            if cur and len(cur) + len(p) + 2 > TARGET:
                chunks.append((f"{prefix}\n" if prefix else "") + cur)
                tail = cur[-OVERLAP:]
                cur = (tail[tail.find(" ") + 1:] + "\n\n" if len(cur) > OVERLAP else "") + p
            else:
                cur = f"{cur}\n\n{p}" if cur else p
        if cur.strip():
            chunks.append((f"{prefix}\n" if prefix else "") + cur)
    # i frammenti minuscoli (es. una riga isolata) si uniscono al precedente
    merged: list[str] = []
    for c in chunks:
        if merged and len(c) < 120 and len(merged[-1]) + len(c) < MAX:
            merged[-1] += "\n" + c
        else:
            merged.append(c)
    return merged
