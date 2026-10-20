import json
from collections.abc import Awaitable, Callable
from typing import Any

ToolFn = Callable[..., Awaitable[str]]


class ToolRegistry:
    """Registro dei tool esposti al modello (formato OpenAI function calling)."""

    def __init__(self) -> None:
        self._tools: dict[str, tuple[dict[str, Any], ToolFn]] = {}

    def register(self, name: str, description: str, parameters: dict[str, Any], fn: ToolFn) -> None:
        spec = {
            "type": "function",
            "function": {"name": name, "description": description, "parameters": parameters},
        }
        self._tools[name] = (spec, fn)

    @property
    def specs(self) -> list[dict[str, Any]]:
        return [spec for spec, _ in self._tools.values()]

    async def call(self, name: str, raw_args: str) -> str:
        if name not in self._tools:
            return f"Errore: tool '{name}' inesistente"
        try:
            args = json.loads(raw_args or "{}")
            return await self._tools[name][1](**args)
        except Exception as e:  # il modello deve vedere l'errore e poter reagire
            return f"Errore nell'esecuzione di {name}: {e}"
