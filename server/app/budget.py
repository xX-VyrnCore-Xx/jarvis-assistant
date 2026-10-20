"""Quanti token restano: unisce il calcolo del pannello FreeLLMAPI (budget mensili documentati e quote
osservate) con il consumo del mese ricavato da /v1/usage."""


def fmt_tokens(n: float) -> str:
    n = float(n)
    if n >= 1e9:
        return f"{n / 1e9:.1f} G"
    if n >= 1e6:
        return f"{n / 1e6:.1f} M"
    if n >= 1e3:
        return f"{n / 1e3:.0f} k"
    return f"{n:.0f}"


def summarize(free_tier: dict, usage: dict) -> dict:
    used_by_platform = {row["platform"]: row.get("tokens", 0) for row in usage.get("byPlatform", [])}
    platforms: dict[str, dict] = {}
    for pool in free_tier.get("pools", []):
        p = platforms.setdefault(
            pool["platform"],
            {"platform": pool["platform"], "documented": 0, "kind": "unpublished", "live_remaining": 0.0,
             "live_pools": 0, "pools": 0},
        )
        p["pools"] += 1
        if pool.get("kind") == "documented":
            p["kind"] = "documented"
            p["documented"] += pool.get("documentedBudget", 0)
        elif pool.get("kind") == "credits" and p["kind"] != "documented":
            p["kind"] = "credits"
        quota = pool.get("quota") or {}
        if quota.get("metric") == "tokens" and isinstance(quota.get("remaining"), (int, float)):
            p["live_remaining"] += quota["remaining"]
            p["live_pools"] += 1

    rows = []
    for name, p in platforms.items():
        used = used_by_platform.get(name, 0)
        live = p["live_pools"] == p["pools"] and p["pools"] > 0  # quota osservata per ogni pool del provider
        if live:
            remaining, source = p["live_remaining"], "live"
        elif p["kind"] == "documented":
            remaining, source = max(p["documented"] - used, 0), "estimate"
        else:
            remaining, source = None, "unknown"
        rows.append({"platform": name, "kind": p["kind"], "documented": p["documented"], "used": used,
                     "remaining": remaining, "source": source})
    rows.sort(key=lambda r: (r["remaining"] is None, -(r["remaining"] or 0)))

    known = [r for r in rows if r["remaining"] is not None]
    return {
        "month": usage.get("month"),
        "resets_at": usage.get("resetsAt"),
        "documented_monthly_tokens": free_tier.get("summary", {}).get("documentedMonthlyTokens", 0),
        "used_tokens": usage.get("tokens", 0),
        "used_requests": usage.get("requests", 0),
        "remaining_tokens": sum(r["remaining"] for r in known),
        "providers_counted": len(known),
        "providers_unknown": len(rows) - len(known),
        "providers": rows,
        "note": "Stima: i budget mensili sono quelli dichiarati dai provider e possono cambiare; "
                "dove il provider comunica la quota reale (source=live) si usa quella.",
    }


def describe(b: dict) -> str:
    lines = [
        f"Token disponibili questo mese (stima): {fmt_tokens(b['remaining_tokens'])} "
        f"su un budget di {fmt_tokens(b['documented_monthly_tokens'])}; usati {fmt_tokens(b['used_tokens'])} "
        f"in {b['used_requests']} richieste. Reset: {b['resets_at'] or 'inizio del prossimo mese'}.",
    ]
    for r in b["providers"]:
        rem = "n/d" if r["remaining"] is None else fmt_tokens(r["remaining"])
        lines.append(f"- {r['platform']}: {rem} rimasti ({'quota reale' if r['source'] == 'live' else 'stima'})")
    if b["providers_unknown"]:
        lines.append(f"{b['providers_unknown']} provider senza budget pubblicato non sono nel totale.")
    return "\n".join(lines)
