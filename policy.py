"""Profile policy for which Aside subscription a Hermes profile uses."""

from __future__ import annotations

from .aside_cli import EFFORTS, PERMISSIONS, SPEEDS
from .catalog import resolve_choice

EMPTY = {"model": "", "host": "", "account": "", "effort": "", "speed": "", "permission": ""}
DEFAULT_PERMISSION = "ask"


class PolicyError(ValueError):
    """The trusted profile policy is unusable. Callers must fail closed."""


def normalize(raw: dict | None) -> dict:
    data = dict(EMPTY)
    if raw is None:
        return data
    if not isinstance(raw, dict):
        raise PolicyError("profile policy is not a mapping")
    for key in EMPTY:
        value = raw.get(key)
        data[key] = "" if value is None else str(value).strip()
    return data


def effective_policy(raw: dict | None) -> dict:
    """Return the validated policy. Empty permission means ask; unknown values raise."""
    chosen = normalize(raw)
    chosen["permission"] = chosen["permission"] or DEFAULT_PERMISSION
    if chosen["permission"] not in PERMISSIONS:
        raise PolicyError("profile permission must be ask, guard, or full-access")
    if chosen["effort"] and chosen["effort"] not in EFFORTS:
        raise PolicyError("profile effort is invalid")
    if chosen["speed"] and chosen["speed"] not in SPEEDS:
        raise PolicyError("profile speed is invalid")
    return chosen


def apply_policy(call: dict, policy: dict | None) -> dict:
    """Apply user locks while preserving one-turn model, effort, and speed choices.

    Host, account, and permission always come from the profile, never from the call. They are
    removed from the call first, so a hidden model-supplied value cannot reach the CLI when the
    profile leaves them unset (empty host means Aside's own default host, empty account means
    Aside's current account, empty permission means ask).
    Raises PolicyError when the profile policy is invalid.
    """
    merged = dict(call)
    for key in ("host", "account", "permission"):
        merged.pop(key, None)
    chosen = effective_policy(policy)
    for key in ("model", "effort", "speed"):
        if not str(merged.get(key) or "").strip() and chosen[key]:
            merged[key] = chosen[key]
    for key in ("host", "account"):
        if chosen[key]:
            merged[key] = chosen[key]
    merged["permission"] = chosen["permission"]
    return merged


def pin_from_choice(catalog: dict, text: str) -> str:
    return resolve_choice(catalog, text)
