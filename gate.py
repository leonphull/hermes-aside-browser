"""Block the built-in browser when this profile says Aside is the browser."""

from __future__ import annotations

import time

BROWSER_PREFIX = "browser_"
PREVIEW_TOOLS = {"open_preview", "drive_preview"}
_CACHE: dict[str, tuple[float, bool]] = {}
_READY_TTL = 30.0
_DOWN_TTL = 10.0


def policy_is_always(policy: dict | None) -> bool:
    return str((policy or {}).get("browser_policy") or "").strip().lower() == "always"


def should_block(tool_name: str, policy: dict | None, aside_ready: bool) -> bool:
    if not policy_is_always(policy) or not aside_ready:
        return False
    name = (tool_name or "").strip()
    if name.startswith("aside_") or name.startswith("mcp__aside__"):
        return False
    if name.startswith(BROWSER_PREFIX) or name in PREVIEW_TOOLS:
        return True
    return False


def block_message() -> str:
    return (
        "Aside is READY and this profile uses it for browser actions. "
        "Call aside_exec. Use aside_repl only when you must inspect the DOM yourself. "
        "Do not call the built-in browser or the desktop preview for this."
    )


def cached_ready(probe, now: float | None = None) -> bool:
    """Return a cached readiness bit. probe() is only called when the cache is stale."""
    clock = time.monotonic() if now is None else now
    hit = _CACHE.get("ready")
    if hit is not None:
        stamped, ready = hit
        ttl = _READY_TTL if ready else _DOWN_TTL
        if clock - stamped < ttl:
            return ready
    try:
        ready = bool(probe())
    except Exception:
        ready = False
    _CACHE["ready"] = (clock, ready)
    return ready


def clear_ready_cache() -> None:
    _CACHE.clear()
