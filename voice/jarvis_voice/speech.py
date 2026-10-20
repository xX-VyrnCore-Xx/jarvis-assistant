import re


def clean_for_speech(text: str) -> str:
    """Toglie markdown, URL ed emoji che suonerebbero male letti da un sintetizzatore."""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[*_`#>~]+", "", text)
    text = re.sub(r"^\s*[-•]\s+", "", text, flags=re.M)
    text = re.sub(r"[\U0001F300-\U0001FAFF☀-➿]", "", text)
    return re.sub(r"\s+", " ", text).strip()
