"""Read Aside's local model catalog. Never returns credentials."""

from __future__ import annotations

import json
from pathlib import Path

PRESETS = ("fast", "standard", "visual")


def aside_home() -> Path:
    return Path.home() / ".aside"


def account_dir(account: str | None = None) -> Path | None:
    root = aside_home() / "u"
    if not root.is_dir():
        return None
    if account:
        name = account[1:] if account.startswith("u") and account[1:].isdigit() else account
        path = root / name
        return path if path.is_dir() else None
    direct = root / "0"
    if direct.is_dir():
        return direct
    dirs = sorted(p for p in root.iterdir() if p.is_dir())
    return dirs[0] if dirs else None


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _kind(provider_id: str, spec: dict) -> str:
    name = str(spec.get("name") or "")
    blob = f"{provider_id} {name}".lower()
    if "oauth" in blob or "subscription" in blob or "accountModelCatalog" in spec:
        return "subscription"
    if spec.get("baseUrl"):
        return "connected"
    return "connected"


def _models(spec: dict) -> list[dict]:
    raw = spec.get("models")
    if isinstance(raw, list):
        out = []
        for item in raw:
            if isinstance(item, str) and item.strip():
                out.append({"id": item.strip(), "name": item.strip()})
            elif isinstance(item, dict) and item.get("id"):
                out.append({"id": str(item["id"]), "name": str(item.get("name") or item["id"])})
        return out
    catalog = spec.get("accountModelCatalog")
    if isinstance(catalog, dict) and isinstance(catalog.get("modelIds"), list):
        return [{"id": str(item), "name": str(item)} for item in catalog["modelIds"] if isinstance(item, str)]
    return []


def load_catalog(account: str | None = None) -> dict:
    folder = account_dir(account)
    if folder is None:
        return {"account_dir": None, "default": None, "providers": [], "presets": {}, "custom": []}
    settings = _read_json(folder / "settings.json")
    models = _read_json(folder / "models.json")
    default = settings.get("defaultModel") if isinstance(settings.get("defaultModel"), dict) else {}
    providers = []
    for provider_id, spec in (models.get("providers") or {}).items():
        if not isinstance(spec, dict):
            continue
        providers.append(
            {
                "id": str(provider_id),
                "name": str(spec.get("name") or provider_id),
                "kind": _kind(str(provider_id), spec),
                "models": _models(spec),
            }
        )
    presets = {}
    categories = settings.get("modelCategories") if isinstance(settings.get("modelCategories"), dict) else {}
    for name in PRESETS:
        item = categories.get(name)
        if isinstance(item, dict) and item.get("provider") and item.get("modelId"):
            presets[name] = {"provider": str(item["provider"]), "model": str(item["modelId"])}
    custom = []
    for item in settings.get("customModels") or []:
        if isinstance(item, dict) and item.get("id"):
            custom.append(
                {
                    "id": str(item["id"]),
                    "name": str(item.get("name") or item["id"]),
                    "provider": str(item.get("provider") or "custom"),
                }
            )
    default_ref = None
    if default.get("provider") and default.get("modelId"):
        default_ref = {"provider": str(default["provider"]), "model": str(default["modelId"])}
    return {
        "account_dir": str(folder),
        "default": default_ref,
        "providers": providers,
        "presets": presets,
        "custom": custom,
    }


def format_ref(provider: str, model: str) -> str:
    return f"{provider}/{model}"


def resolve_choice(catalog: dict, text: str) -> str:
    """Return a provider/model pin, or '' for Aside's own default."""
    choice = text.strip()
    if not choice or choice in {"default", "aside", "aside-default"}:
        return ""
    if choice in catalog.get("presets") or {}:
        preset = catalog["presets"][choice]
        return format_ref(preset["provider"], preset["model"])
    if "/" in choice:
        provider, model = choice.split("/", 1)
        if not provider or not model or provider.startswith("-") or model.startswith("-"):
            raise ValueError("model must look like provider/model")
        return f"{provider}/{model}"
    matches = []
    for provider in catalog.get("providers") or []:
        for model in provider["models"]:
            if choice in {model["id"], model["name"]}:
                matches.append(format_ref(provider["id"], model["id"]))
    for item in catalog.get("custom") or []:
        if choice in {item["id"], item["name"]}:
            matches.append(format_ref(item["provider"], item["id"]))
    unique = list(dict.fromkeys(matches))
    if len(unique) == 1:
        return unique[0]
    if not unique:
        raise ValueError(f"unknown model {choice!r}; run `hermes aside models`")
    raise ValueError(f"{choice!r} matches {', '.join(unique)}; pass provider/model")
