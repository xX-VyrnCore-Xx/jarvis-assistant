"""Privacy verso i modelli: i dati sensibili vengono sostituiti da segnaposto prima di uscire verso i provider di intelligenza
artificiale e rimessi al loro posto nelle risposte e negli argomenti dei tool. Il modello non vede mai IBAN, carte, chiavi o password."""
import json
import re

# (nome, regex, validazione opzionale)
def _luhn(s: str) -> bool:
    d = [int(c) for c in re.sub(r"\D", "", s)]
    if not 13 <= len(d) <= 19:
        return False
    total = 0
    for i, n in enumerate(reversed(d)):
        if i % 2:
            n = n * 2 - 9 if n * 2 > 9 else n * 2
        total += n
    return total % 10 == 0


def _iban(s: str) -> bool:
    c = re.sub(r"\s", "", s).upper()
    if not 15 <= len(c) <= 34:
        return False
    num = "".join(str(int(ch, 36)) for ch in c[4:] + c[:4])
    return int(num) % 97 == 1


STANDARD = [
    ("IBAN", re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){2,7}\s?[A-Z0-9]{1,4}\b"), _iban),
    ("CARTA", re.compile(r"\b(?:\d[ -]?){13,19}\b"), _luhn),
    ("CHIAVE", re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9_-]{16,}|\bAKIA[0-9A-Z]{16}\b|\bghp_[A-Za-z0-9]{30,}|\bAIza[0-9A-Za-z_-]{30,}|\bxox[baprs]-[A-Za-z0-9-]{10,}|\bfreellmapi-[A-Za-z0-9-]{8,}|\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}|\bBearer\s+[A-Za-z0-9._~+/-]{20,}"), None),
    ("CF", re.compile(r"\b[A-Za-z]{6}\d{2}[A-Za-z]\d{2}[A-Za-z]\d{3}[A-Za-z]\b"), None),
]
# password e simili: si maschera solo il valore, non la parola
SECRET_ASSIGN = re.compile(r"(?i)\b(password|passwd|pwd|pin|chiave|token|secret|segreto|api[_ -]?key)\b(\s*(?:[:=]|è|e'|is)\s*)(\S{4,})")
STRICT = [
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b"), None),
    ("TEL", re.compile(r"(?<!\w)(?:\+|00)?\d[\d\s().-]{7,}\d(?!\w)"), lambda s: 9 <= len(re.sub(r"\D", "", s)) <= 15),
]
PLACEHOLDER = re.compile(r"\[(?:IBAN|CARTA|CHIAVE|CF|SEGRETO|EMAIL|TEL)_\d+\]")


class Redactor:
    """Una istanza per richiesta: la stessa informazione ha sempre lo stesso segnaposto, così il modello può ragionarci sopra."""

    def __init__(self, mode: str = "standard"):
        self.mode = mode if mode in ("off", "standard", "strict") else "standard"
        self.forward: dict[str, str] = {}
        self.backward: dict[str, str] = {}
        self._n: dict[str, int] = {}

    def _slot(self, kind: str, value: str) -> str:
        if value not in self.forward:
            self._n[kind] = self._n.get(kind, 0) + 1
            ph = f"[{kind}_{self._n[kind]}]"
            self.forward[value], self.backward[ph] = ph, value
        return self.forward[value]

    def mask(self, text: str) -> str:
        if self.mode == "off" or not text:
            return text
        text = SECRET_ASSIGN.sub(lambda m: f"{m.group(1)}{m.group(2)}{self._slot('SEGRETO', m.group(3))}", text)
        for kind, rx, check in STANDARD + (STRICT if self.mode == "strict" else []):
            text = rx.sub(lambda m, k=kind, c=check: self._slot(k, m.group(0)) if (c is None or c(m.group(0))) else m.group(0), text)
        return text

    def unmask(self, text: str) -> str:
        if not self.backward or not text:
            return text
        return PLACEHOLDER.sub(lambda m: self.backward.get(m.group(0), m.group(0)), text)

    def unmask_json(self, raw: str) -> str:
        """Argomenti di un tool (JSON): rimette i valori veri, con le virgolette/escape corretti."""
        if not self.backward or not raw:
            return raw
        return PLACEHOLDER.sub(lambda m: json.dumps(self.backward[m.group(0)])[1:-1] if m.group(0) in self.backward else m.group(0), raw)

    @property
    def count(self) -> int:
        return len(self.forward)
