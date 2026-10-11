"""Profile policy for which Aside subscription a Hermes profile uses."""

from __future__ import annotations

from .catalog import resolve_choice

EMPTY = {"model": "", "host": "", "account": "", "effort": "", "speed": ""}


def normalize(raw: dict | None) -> dict:
    data = dict(EMPTY)
    if not raw:
        return data
    for key in EMPTY:
        value = raw.get(key)
        data[key] = "" if value is None else str(value).strip()
    return data


def apply_policy(call: dict, policy: dict | None) -> dict:
    """Fill only the fields the caller left empty. A one-turn override wins."""
    merged = dict(call)
    chosen = normalize(policy)
    for key in ("model", "host", "account", "effort", "speed"):
        if not str(merged.get(key) or "").strip() and chosen[key]:
            merged[key] = chosen[key]
    return merged


def pin_from_choice(catalog: dict, text: str) -> str:
    return resolve_choice(catalog, text)
