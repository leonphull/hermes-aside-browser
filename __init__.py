"""Aside browser plugin for Hermes Agent."""

from __future__ import annotations

from pathlib import Path

from .aside_cli import find_aside
from .tools import HANDLERS, SCHEMAS

SKILL_DESCRIPTION = "Use the signed-in Aside browser for web tasks."


def _aside_installed() -> bool:
    return find_aside() is not None


def register(ctx) -> None:
    for name, schema in SCHEMAS.items():
        ctx.register_tool(
            name=name,
            toolset="aside",
            schema=schema,
            handler=HANDLERS[name],
            check_fn=_aside_installed,
            description=schema["function"]["description"],
        )
    skill = Path(__file__).resolve().parent / "skills" / "aside-browser" / "SKILL.md"
    ctx.register_skill("aside-browser", skill, description=SKILL_DESCRIPTION)
