"""`hermes aside` — pick the subscription this Hermes profile uses."""

from __future__ import annotations

from .catalog import format_ref, load_catalog, resolve_choice

KEYS = ("model", "host", "account", "effort", "speed")


def read_policy(ctx) -> dict:
    return {key: str(ctx.get_config(key, "") or "").strip() for key in KEYS}


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
    lines = ["Aside models visible to this machine. No credentials are shown.", ""]
    default = catalog.get("default")
    if default:
        lines.append(f"Aside default: {format_ref(default['provider'], default['model'])}")
    else:
        lines.append("Aside default: not set")
    lines.append("Plugin default: `hermes aside use default` leaves the choice to Aside.")
    lines.append("")
    presets = catalog.get("presets") or {}
    if presets:
        lines.append("Presets from Aside settings:")
        for name, item in presets.items():
            lines.append(f"  {name:10} {format_ref(item['provider'], item['model'])}")
        lines.append("")
    providers = catalog.get("providers") or []
    if not providers:
        lines.append("No connected providers found in Aside.")
    for provider in providers:
        label = "subscription" if provider["kind"] == "subscription" else "connected"
        lines.append(f"{provider['name']} [{label}]  {provider['id']}")
        models = provider["models"] or [{"id": "(no model list)", "name": ""}]
        for model in models:
            name = f"  {model['name']}" if model.get("name") and model["name"] != model["id"] else ""
            lines.append(f"  {format_ref(provider['id'], model['id'])}{name}")
        lines.append("")
    custom = catalog.get("custom") or []
    if custom:
        lines.append("Custom models:")
        for item in custom:
            lines.append(f"  {format_ref(item['provider'], item['id'])}  {item['name']}")
    return "\n".join(lines).rstrip()


def format_status(policy: dict, probe: dict) -> str:
    model = policy["model"] or "Aside's own default"
    host = policy["host"] or "local"
    account = policy["account"] or "Aside's current account"
    lines = [
        f"Aside: {probe.get('status')}  {probe.get('message', '')}",
        f"This profile uses model: {model}",
        f"Host: {host}",
        f"Account: {account}",
    ]
    if policy["effort"]:
        lines.append(f"Effort: {policy['effort']}")
    if policy["speed"]:
        lines.append(f"Speed: {policy['speed']}")
    return "\n".join(lines)


def build_parser(parser) -> None:
    sub = parser.add_subparsers(dest="aside_cmd", required=True)
    sub.add_parser("status", help="Show Aside readiness and this profile's choice")
    sub.add_parser("models", help="List Aside subscriptions and connected models")
    use = sub.add_parser("use", help="Pin a model, a preset, or Aside's default")
    use.add_argument("choice", help="provider/model, a model id, fast/standard/visual, or default")
    host = sub.add_parser("host", help="Pin a remote Aside host, or local")
    host.add_argument("name", help="A host name from `aside host list`, local, or clear")
    account = sub.add_parser("account", help="Pin an Aside account, or clear")
    account.add_argument("account_id", help="u0, or clear")
    effort = sub.add_parser("effort", help="Pin thinking effort, or clear")
    effort.add_argument("level", help="off, low, medium, high, xhigh, max, ultrabrowse, or clear")


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
        write_policy(ctx, model=pin)
        print("This profile now uses " + (pin or "Aside's own default") + ".")
        return
    if command == "host":
        name = args.name.strip()
        if name in {"local", "clear", "default"}:
            name = ""
        write_policy(ctx, host=name)
        print("This profile now uses host " + (name or "local") + ".")
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
    raise SystemExit(f"unknown command {command}")
