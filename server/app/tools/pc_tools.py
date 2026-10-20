from ..pc import PCBridge
from . import ToolRegistry


def register_pc_tools(reg: ToolRegistry, pc: PCBridge) -> None:
    def tool(name: str, description: str, props: dict, required: list[str]) -> None:
        async def fn(**args) -> str:
            return await pc.call(name, args)

        # i tool del PC compaiono solo se l'app Windows è collegata: meno token e niente promesse a vuoto
        reg.register(
            name, description, {"type": "object", "properties": props, "required": required}, fn,
            available=lambda: pc.connected,
        )

    s = {"type": "string"}
    tool("pc_open_url", "Apre un sito nel browser del PC dell'utente (solo http/https).", {"url": s}, ["url"])
    tool("pc_open_app", "Avvia un'applicazione sul PC dell'utente per nome (es. 'spotify', 'notepad', 'calc').", {"name": s}, ["name"])
    tool("pc_list_dir", "Elenca i file di una cartella del PC (percorso nella home dell'utente, es. 'Documenti').", {"path": s}, ["path"])
    tool("pc_search_files", "Cerca file per nome nella cartella home del PC.", {"query": s}, ["query"])
    tool("pc_open_path", "Apre un file o una cartella del PC con il programma predefinito.", {"path": s}, ["path"])
    tool("pc_create_folder", "Crea una cartella nella home del PC.", {"path": s}, ["path"])
    tool("pc_move", "Sposta o rinomina un file/cartella nella home del PC (l'utente deve confermare sul PC).", {"src": s, "dst": s}, ["src", "dst"])
    tool(
        "pc_volume",
        "Regola il volume: 'level' 0-100 oppure 'action' = up|down|mute.",
        {"level": {"type": "integer"}, "action": {"type": "string", "enum": ["up", "down", "mute"]}},
        [],
    )
    tool("pc_brightness", "Imposta la luminosità dello schermo (0-100, solo portatili/monitor supportati).", {"level": {"type": "integer"}}, ["level"])
    tool("pc_lock", "Blocca il PC.", {}, [])
    tool(
        "pc_power",
        "Spegne o riavvia il PC tra 30 secondi, oppure annulla. L'utente deve confermare sul PC.",
        {"mode": {"type": "string", "enum": ["shutdown", "restart", "cancel"]}},
        ["mode"],
    )
