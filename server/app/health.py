"""Stato di salute del servizio: memoria, database, backup, aggiornamenti, consumo dei modelli."""
import json
import os
import time

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
