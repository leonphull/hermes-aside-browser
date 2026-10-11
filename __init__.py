"""Aside browser plugin for Hermes Agent."""

from __future__ import annotations

from pathlib import Path

from .aside_cli import find_aside
from .cli import build_parser, handle, read_policy, tool_policy
from .gate import block_message, cached_ready, should_block
from .tools import HANDLERS, SCHEMAS, set_policy_loader

SKILL_DESCRIPTION = "Use the signed-in Aside browser for web tasks."


def _aside_installed() -> bool:
    return find_aside() is not None


def register(ctx) -> None:
    set_policy_loader(lambda: tool_policy(ctx))
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
    def _on_pre_tool_call(tool_name: str = "", args=None, **kwargs):
        policy = read_policy(ctx)
        if not should_block(tool_name, policy, True):
            return None
        from .aside_cli import probe

        ready = cached_ready(lambda: probe(timeout=5).get("status") == "READY")
        if not should_block(tool_name, policy, ready):
            return None
        return {"action": "block", "message": block_message()}

    ctx.register_hook("pre_tool_call", _on_pre_tool_call)
    ctx.register_cli_command(
        "aside",
        "Choose which Aside subscription this Hermes profile uses",
        build_parser,
        lambda args: handle(ctx, args),
        description="List Aside models and pin one for this profile.",
    )
