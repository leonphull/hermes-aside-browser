"""`hermes aside` — manage this profile's Aside settings: model, host, account, effort, speed, permission, browser policy."""

from __future__ import annotations

from .catalog import format_ref, load_catalog, resolve_choice

KEYS = ("model_pin", "host", "account", "effort", "speed", "permission", "browser_policy")


def read_policy(ctx) -> dict:
    return {key: str(ctx.get_config(key, "") or "").strip() for key in KEYS}


def tool_policy(ctx) -> dict:
    """Shape the profile pin the way aside_exec expects it."""
    raw = read_policy(ctx)
    return {
        "model": raw["model_pin"],
        "host": raw["host"],
        "account": raw["account"],
        "effort": raw["effort"],
        "speed": raw["speed"],
        "permission": raw["permission"] or "ask",
    }


def write_policy(ctx, **updates) -> dict:
    current = read_policy(ctx)
    for key, value in updates.items():
        if key not in KEYS:
            raise ValueError(f"unknown setting {key}")
        text = "" if value is None else str(value).strip()
        ctx.set_config(key, text)
        current[key] = text
    return current


def format_models(catalog: dict) -> str:
    lines = ["Aside models from settings.json.", ""]
    default = catalog.get("default")
    if default:
        lines.append(f"Aside default: {format_ref(default['provider'], default['model'])}")
    else:
        lines.append("Aside default: not set")
    lines.append("")
    presets = catalog.get("presets") or {}
    if presets:
        lines.append("Presets from Aside settings:")
        for name, item in presets.items():
            lines.append(f"  {name:10} {format_ref(item['provider'], item['model'])}")
        lines.append("")
    custom = catalog.get("custom") or []
    if custom:
        lines.append("Custom models:")
        for item in custom:
            lines.append(f"  {format_ref(item['provider'], item['id'])}  {item['name']}")
    return "\n".join(lines).rstrip()


def format_status(policy: dict, probe: dict) -> str:
    model = policy["model_pin"] or "Aside's own default"
    host = policy["host"] or "Aside's default host"
    account = policy["account"] or "Aside's current account"
    lines = [
        f"Aside: {probe.get('status')}  {probe.get('message', '')}",
        f"This profile uses model: {model}",
        f"Host: {host}",
        f"Account: {account}",
        f"Permission: {policy.get('permission') or 'ask'}",
        f"Browser policy: {policy.get('browser_policy') or 'prefer'}",
    ]
    if policy["effort"]:
        lines.append(f"Effort: {policy['effort']}")
    if policy["speed"]:
        lines.append(f"Speed: {policy['speed']}")
    return "\n".join(lines)


def build_parser(parser) -> None:
    sub = parser.add_subparsers(dest="aside_cmd", required=True)
    sub.add_parser("status", help="Show Aside readiness and this profile's choice")
    sub.add_parser("models", help="List Aside default, presets, and custom models")
    use = sub.add_parser("use", help="Pin a model, a preset, or Aside's default")
    use.add_argument("choice", help="provider/model, a model id, fast/standard/visual, or default")
    host = sub.add_parser("host", help="Pin a remote Aside host, or local")
    host.add_argument("name", help="A host name from `aside host list`, local (pins the local host), or clear/default (removes the pin)")
    account = sub.add_parser("account", help="Pin an Aside account, or clear")
    account.add_argument("account_id", help="u0, or clear")
    effort = sub.add_parser("effort", help="Pin thinking effort, or clear")
    effort.add_argument("level", help="off, low, medium, high, xhigh, max, ultrabrowse, or clear")
    permission = sub.add_parser("permission", help="Set this profile's Aside permission")
    permission.add_argument("level", help="ask, guard, or full-access (clear/default resets to ask)")
    policy = sub.add_parser("policy", help="prefer Aside, or always use it for browser actions")
    policy.add_argument("mode", help="always or prefer")


def handle(ctx, args) -> None:
    command = args.aside_cmd
    if command == "models":
        print(format_models(load_catalog()))
        return
    if command == "status":
        from .aside_cli import probe
        print(format_status(read_policy(ctx), probe()))
        return
    if command == "use":
        pin = resolve_choice(load_catalog(), args.choice)
        write_policy(ctx, model_pin=pin)
        print("This profile now uses " + (pin or "Aside's own default") + ".")
        return
    if command == "host":
        name = args.name.strip()
        if name.lower() == "local":
            name = "local"
        elif name.lower() in {"clear", "default"}:
            name = ""
        write_policy(ctx, host=name)
        if name:
            print("This profile now uses host " + name + ".")
        else:
            print("This profile host pin is cleared. Aside's own default host applies.")
        return
    if command == "account":
        account_id = args.account_id.strip()
        if account_id in {"clear", "default"}:
            account_id = ""
        write_policy(ctx, account=account_id)
        print("This profile now uses account " + (account_id or "Aside's current account") + ".")
        return
    if command == "effort":
        level = args.level.strip()
        if level in {"clear", "default"}:
            level = ""
        allowed = {"", "off", "minimal", "low", "medium", "high", "xhigh", "max", "ultrabrowse"}
        if level not in allowed:
            raise SystemExit(f"invalid effort {level!r}")
        write_policy(ctx, effort=level)
        print("This profile now uses effort " + (level or "Aside's own default") + ".")
        return
    if command == "permission":
        level = args.level.strip()
        if level in {"clear", "default"}:
            level = "ask"
        if level not in {"ask", "guard", "full-access"}:
            raise SystemExit("permission must be ask, guard, or full-access")
        write_policy(ctx, permission=level)
        print(f"This profile permission is now {level}.")
        return
    if command == "policy":
        mode = args.mode.strip().lower()
        if mode not in {"always", "prefer"}:
            raise SystemExit("policy must be always or prefer")
        write_policy(ctx, browser_policy=mode)
        print(f"This profile browser policy is now {mode}.")
        return
    raise SystemExit(f"unknown command {command}")
