"""Resolve the Aside CLI and run it without a shell."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

READY_MARKER = "ASIDE_READY"
SESSION_ID_RE = re.compile(r"\bses_[A-Za-z0-9]+\b")
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
MAX_OUTPUT = 48_000
EFFORTS = {"off", "minimal", "low", "medium", "high", "xhigh", "max", "ultrabrowse"}
SPEEDS = {"default", "fast"}
PERMISSIONS = {"ask", "guard", "full-access"}
CONTINUATION_ACTIONS = {"resume", "steer", "queue"}


def find_aside() -> str | None:
    """Return an executable aside binary, or None. Never downloads one."""
    candidates: list[str] = []
    env_bin = os.environ.get("ASIDE_BIN", "").strip()
    if env_bin:
        candidates.append(env_bin)
    which = shutil.which("aside")
    if which:
        candidates.append(which)
    home = Path.home()
    candidates.extend(
        [
            str(home / ".local" / "bin" / "aside"),
            "/usr/local/bin/aside",
            "/opt/homebrew/bin/aside",
        ]
    )
    seen: set[str] = set()
    for raw in candidates:
        if not raw or raw in seen:
            continue
        seen.add(raw)
        path = Path(raw).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    return None


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text or "")


def _looks_like_base64(line: str) -> bool:
    sample = line.strip()
    if len(sample) < 400:
        return False
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")
    return sum(c in allowed for c in sample) / len(sample) > 0.98


def redact_and_truncate(text: str, limit: int = MAX_OUTPUT) -> str:
    lines = []
    for line in strip_ansi(text).splitlines():
        if _looks_like_base64(line):
            lines.append(f"[redacted image or binary data, {len(line)} chars]")
        else:
            lines.append(line)
    out = "\n".join(lines)
    if len(out) > limit:
        return out[:limit] + f"\n[truncated, {len(out)} chars total]"
    return out


def safe_token(value: str, label: str) -> str:
    text = str(value).strip()
    if not text or text.startswith("-") or any(ch in text for ch in "\n\r\x00"):
        raise ValueError(f"invalid {label}")
    return text


def run_aside(args: list[str], timeout: int) -> dict:
    binary = find_aside()
    if not binary:
        return {
            "ok": False,
            "status": "NEEDS_ASIDE",
            "message": (
                "aside CLI not found. Install it from Aside Settings > Developers. "
                "This plugin does not run an installer."
            ),
        }
    timeout = max(5, min(int(timeout), 600))
    try:
        proc = subprocess.run(
            [binary, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = redact_and_truncate(exc.stdout or "")
        return {
            "ok": False,
            "status": "TIMEOUT",
            "binary": binary,
            "message": (
                f"aside timed out after {timeout}s. The Aside session may still be "
                "running; use aside_session to list or stop it."
            ),
            "stdout": stdout,
            "session_ids": SESSION_ID_RE.findall(stdout),
        }
    stdout = redact_and_truncate(proc.stdout or "")
    stderr = redact_and_truncate(proc.stderr or "", limit=8_000)
    return {
        "ok": proc.returncode == 0,
        "status": "OK" if proc.returncode == 0 else "ASIDE_CLI_ERROR",
        "binary": binary,
        "exit_code": proc.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "session_ids": SESSION_ID_RE.findall(stdout),
        "cli_ok": "[ok" in strip_ansi(proc.stdout or ""),
    }


def probe(timeout: int = 20) -> dict:
    binary = find_aside()
    if not binary:
        return {
            "ok": False,
            "status": "NEEDS_ASIDE",
            "binary": None,
            "message": (
                "aside CLI not found. Install it from Aside Settings > Developers, "
                "then start a new Hermes session."
            ),
        }
    result = run_aside(["repl", 'console.log("ASIDE_READY")'], timeout=timeout)
    stdout = result.get("stdout") or ""
    if result.get("status") == "TIMEOUT":
        return {
            "ok": False,
            "status": "ASIDE_NOT_RUNNING",
            "binary": binary,
            "message": "aside did not answer the readiness probe. Open the Aside app and retry.",
        }
    if READY_MARKER in stdout and result.get("exit_code") == 0:
        return {
            "ok": True,
            "status": "READY",
            "binary": binary,
            "message": (
                "Aside is ready. Prefer it over the built-in browser for signed-in "
                "and interactive web tasks."
            ),
        }
    return {
        "ok": False,
        "status": "ASIDE_NOT_RUNNING",
        "binary": binary,
        "message": (
            "aside is installed but did not report ready. Open the Aside app and retry. "
            "Do not install a second copy."
        ),
        "stdout": stdout,
        "stderr": result.get("stderr") or "",
    }


def global_flags(*, account: str | None = None, host: str | None = None, profile: str | None = None) -> list[str]:
    flags: list[str] = []
    if account:
        flags += ["--account", safe_token(account, "account")]
    if host:
        flags += ["--host", safe_token(host, "host")]
    if profile:
        flags += ["--profile", safe_token(profile, "profile")]
    return flags


def exec_args(
    prompt: str,
    *,
    account: str | None = None,
    host: str | None = None,
    profile: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    speed: str | None = None,
    permission: str | None = None,
) -> list[str]:
    text = safe_token(prompt, "prompt")
    flags = global_flags(account=account, host=host, profile=profile)
    if model:
        flags += ["--model", safe_token(model, "model")]
    if effort:
        if effort not in EFFORTS:
            raise ValueError("invalid effort")
        flags += ["--effort", effort]
    if speed:
        if speed not in SPEEDS:
            raise ValueError("invalid speed")
        flags += ["--speed", speed]
    if permission:
        if permission not in PERMISSIONS:
            raise ValueError("invalid permission")
        flags += ["--permission", permission]
    return ["exec", *flags, text]


def repl_args(
    code: str,
    *,
    account: str | None = None,
    host: str | None = None,
    profile: str | None = None,
) -> list[str]:
    script = str(code)
    if not script.strip():
        raise ValueError("code is required")
    if script.lstrip().startswith("-"):
        raise ValueError("code must not start with '-'")
    return ["repl", *global_flags(account=account, host=host, profile=profile), script]


def session_args(
    action: str,
    *,
    session_id: str | None = None,
    account: str | None = None,
) -> list[str]:
    """Build argv for list, stop, archive, and delete only.

    resume, steer, and queue are deliberately absent: they would drive an existing
    session whose permission and host this plugin cannot verify.
    """
    action = action.strip()
    flags = ["--account", safe_token(account, "account")] if account else []
    if action == "list":
        return ["session", "list", *flags]
    sid = safe_token(session_id or "", "session_id")
    if not sid.startswith("ses_"):
        raise ValueError("session_id must start with ses_")
    if action == "stop":
        return ["session", "stop", *flags, sid]
    if action == "archive":
        return ["session", "archive", *flags, sid]
    if action == "delete":
        return ["session", "delete", *flags, sid]
    raise ValueError("invalid action")


def memory_args(query: str, *, max_results: int = 5, account: str | None = None) -> list[str]:
    text = safe_token(query, "query")
    count = max(1, min(int(max_results), 10))
    flags = ["--account", safe_token(account, "account")] if account else []
    return ["memory", "search", *flags, "--json", "-n", str(count), text]
