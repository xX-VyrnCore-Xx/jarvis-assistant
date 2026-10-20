import re


def clean_for_speech(text: str) -> str:
    """Toglie markdown, URL ed emoji che suonerebbero male letti da un sintetizzatore."""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[*_`#>~]+", "", text)
    text = re.sub(r"^\s*[-•]\s+", "", text, flags=re.M)
    text = re.sub(r"[\U0001F300-\U0001FAFF☀-➿]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def split_sentences(text: str, max_len: int = 160) -> list[str]:
    """Frasi raggruppate fino a `max_len` caratteri: la prima parte subito, le altre in sequenza."""
    out: list[str] = []
    for part in re.findall(r"[^.!?;:\n]+[.!?;:]*", text):
        part = part.strip()
        while len(part) > 220:
            cut = part.rfind(" ", 0, 220)
            cut = cut if cut > 40 else 220
            out.append(part[:cut].strip())
            part = part[cut:].strip()
        if not part:
            continue
        if out and len(out[-1]) + len(part) < max_len:
            out[-1] += " " + part
        else:
            out.append(part)
    return out
