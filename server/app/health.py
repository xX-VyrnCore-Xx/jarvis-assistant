"""Stato di salute del servizio: memoria, database, backup, aggiornamenti, consumo dei modelli."""
import json
import logging
import os
import time

log = logging.getLogger("jarvis.heartbeat")
STARTED = time.monotonic()
PULSE: dict[str, tuple[float, float]] = {}  # ciclo -> (ultimo giro, ogni quanti secondi dovrebbe girare)
PAGE = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 4096


def rss_mb() -> float:
    """Memoria residente del processo (MB), letta da /proc: su Render Free il limite è 512 MB per tutto il container."""
    try:
        with open("/proc/self/statm") as f:
            return int(f.read().split()[1]) * PAGE / 1e6
    except (OSError, ValueError, IndexError):
        return 0.0


def container_mb() -> float:
    """Memoria dell'intero container (JARVIS + FreeLLMAPI), se disponibile (cgroup v2/v1)."""
    for p in ("/sys/fs/cgroup/memory.current", "/sys/fs/cgroup/memory/memory.usage_in_bytes"):
        try:
            with open(p) as f:
                return int(f.read().strip()) / 1e6
        except (OSError, ValueError):
            continue
    return 0.0


async def deep_health(app) -> dict:
    st = app.state
    t0 = time.monotonic()
    try:
        await st.store.get_setting("health_probe")
        db_ok = True
    except Exception:
        db_ok = False
    db_ms = int((time.monotonic() - t0) * 1000)
    try:
        backup = json.loads(await st.store.get_setting("backup_status") or "{}")
    except Exception:
        backup = {}
    return {
        "db": {"ok": db_ok, "latency_ms": db_ms},
        "memory": {"process_mb": round(rss_mb()), "container_mb": round(container_mb()), "limit_mb": 512},
        "freellm_ready": await st.admin.ready() if st.budget.enabled else None,
        "brain": {"indexed": len(st.brain.index), "enabled": st.brain.enabled},
        "usage_today": st.usage.today(),
        "backup": backup,
        "update": {"last_error": st.updates.last_error, "checked_at": st.updates.last_check},
        "realtime_listeners": st.notifier.listeners,
        "pending_actions": len(st.pending.list_pending()),
    }


def beat(name: str, every_s: float) -> None:
    """Ogni ciclo di fondo segna qui che è vivo: il battito del server li controlla tutti."""
    PULSE[name] = (time.monotonic(), every_s)


def stale_loops(now: float | None = None) -> list[tuple[str, int]]:
    """Cicli che non girano da più di 3 volte il loro intervallo (+1 minuto): (nome, minuti di silenzio)."""
    now = now or time.monotonic()
    return [(n, int((now - t) / 60)) for n, (t, every) in PULSE.items() if now - t > 3 * every + 60]


def heartbeat_line(app, now: float | None = None) -> str:
    st = app.state
    now = now or time.monotonic()
    up = int(now - STARTED)
    t = st.usage.today()
    mem = container_mb() or rss_mb()
    parts = [f"su {up // 3600}h{up % 3600 // 60:02d}", f"mem {mem:.0f}/512 MB",
             f"modelli oggi {t['requests']} ({t['errors']} err, {t['avg_latency_ms'] / 1000:.1f} s)",
             f"cervello {len(st.brain.index)} frammenti", f"app in diretta {st.notifier.listeners}",
             f"conferme {len(st.pending.list_pending())}"]
    tgh = getattr(getattr(st, "tg", None), "health", None) or {}
    if tgh.get("mode"):
        parts.append(f"telegram {tgh['mode']} {'ok' if tgh.get('url_ok') and not tgh.get('last_error') else 'PROBLEMA: ' + (tgh.get('last_error') or 'webhook diverso')[:50]}")
    bad = stale_loops(now)
    parts.append("cicli ok" if not bad else "CICLI FERMI: " + ", ".join(f"{n} ({m} min)" for n, m in bad))
    return " | ".join(parts)
