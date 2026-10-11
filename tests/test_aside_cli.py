"""Unit tests for the Aside CLI wrapper. No live browser required."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import importlib.util

spec = importlib.util.spec_from_file_location(
    "hermes_plugins.aside_browser",
    ROOT / "__init__.py",
    submodule_search_locations=[str(ROOT)],
)
plugin = importlib.util.module_from_spec(spec)
plugin.__package__ = "hermes_plugins.aside_browser"
plugin.__path__ = [str(ROOT)]
sys.modules[spec.name] = plugin
spec.loader.exec_module(plugin)

aside_cli = importlib.import_module("hermes_plugins.aside_browser.aside_cli")
tools = importlib.import_module("hermes_plugins.aside_browser.tools")
SKILL_DESCRIPTION = plugin.SKILL_DESCRIPTION


class FindAsideTest(unittest.TestCase):
    def test_prefers_aside_bin_when_executable(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "aside"
            binary.write_text("#!/bin/sh\n", encoding="utf-8")
            binary.chmod(0o755)
            with mock.patch.dict(os.environ, {"ASIDE_BIN": str(binary)}):
                self.assertEqual(aside_cli.find_aside(), str(binary))

    def test_skips_missing_aside_bin(self):
        with mock.patch.dict(os.environ, {"ASIDE_BIN": "/no/such/aside"}):
            with mock.patch.object(aside_cli.shutil, "which", return_value=None):
                with mock.patch.object(Path, "home", return_value=Path("/no/such/home")):
                    self.assertIsNone(aside_cli.find_aside())


class RedactTest(unittest.TestCase):
    def test_redacts_long_base64_line(self):
        blob = "A" * 500
        text = aside_cli.redact_and_truncate(f"keep\n{blob}\n")
        self.assertIn("keep", text)
        self.assertNotIn(blob, text)
        self.assertIn("redacted", text)

    def test_strips_ansi(self):
        self.assertEqual(aside_cli.strip_ansi("ok\x1b[2m[ok]\x1b[0m"), "ok[ok]")


class ArgTest(unittest.TestCase):
    def test_exec_args(self):
        self.assertEqual(
            aside_cli.exec_args("check inbox", account="u1", effort="high"),
            ["exec", "--account", "u1", "--effort", "high", "check inbox"],
        )

    def test_resume_uses_session_command(self):
        self.assertEqual(
            aside_cli.exec_args("continue", session_id="ses_abc", account="u0"),
            ["session", "resume", "--account", "u0", "ses_abc", "continue"],
        )

    def test_rejects_flag_injection(self):
        with self.assertRaises(ValueError):
            aside_cli.exec_args("ok", account="--permission")

    def test_full_access_only_when_asked(self):
        argv = aside_cli.exec_args("ok")
        self.assertNotIn("full-access", argv)
        argv = aside_cli.exec_args("ok", permission="full-access")
        self.assertIn("full-access", argv)

    def test_repl_and_memory(self):
        self.assertEqual(aside_cli.repl_args("console.log(1)"), ["repl", "console.log(1)"])
        self.assertEqual(
            aside_cli.memory_args("stripe", max_results=3),
            ["memory", "search", "--json", "-n", "3", "stripe"],
        )


class ToolGuardTest(unittest.TestCase):
    def test_delete_requires_confirm(self):
        payload = json.loads(tools.aside_session({"action": "delete", "session_id": "ses_abc"}))
        self.assertEqual(payload["status"], "CONFIRM_REQUIRED")

    def test_empty_prompt(self):
        payload = json.loads(tools.aside_exec({"prompt": "  "}))
        self.assertEqual(payload["status"], "INVALID_INPUT")

    def test_probe_needs_aside(self):
        with mock.patch.object(aside_cli, "find_aside", return_value=None):
            payload = json.loads(tools.aside_status({}))
        self.assertEqual(payload["status"], "NEEDS_ASIDE")
        self.assertNotIn("curl", payload["message"])

    def test_probe_ready(self):
        with mock.patch.object(aside_cli, "find_aside", return_value="/bin/aside"):
            with mock.patch.object(
                aside_cli,
                "run_aside",
                return_value={"ok": True, "status": "OK", "exit_code": 0, "stdout": "ASIDE_READY", "stderr": ""},
            ):
                payload = json.loads(tools.aside_status({}))
        self.assertEqual(payload["status"], "READY")


class SkillTest(unittest.TestCase):
    def test_description_matches_index_and_length(self):
        text = (ROOT / "skills" / "aside-browser" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn(f"description: {SKILL_DESCRIPTION}", text)
        self.assertLessEqual(len(SKILL_DESCRIPTION), 60)
        self.assertTrue(SKILL_DESCRIPTION.endswith("."))
        self.assertNotIn("curl ", text)
        self.assertIn("browser_navigate", text)


if __name__ == "__main__":
    unittest.main()


class PolicyTest(unittest.TestCase):
    def test_pin_does_not_override_explicit_model(self):
        from hermes_plugins.aside_browser.policy import apply_policy
        merged = apply_policy({"prompt": "go", "model": "openai-codex/gpt-5.5"}, {"model": "xai-grok-oauth/grok-4.7"})
        self.assertEqual(merged["model"], "openai-codex/gpt-5.5")

    def test_empty_call_takes_profile_pin(self):
        from hermes_plugins.aside_browser.policy import apply_policy
        merged = apply_policy({"prompt": "go"}, {"model": "kimi-code/k3", "host": "mini"})
        self.assertEqual(merged["model"], "kimi-code/k3")
        self.assertEqual(merged["host"], "mini")

    def test_resolve_unique_and_default(self):
        from hermes_plugins.aside_browser.catalog import resolve_choice
        catalog = {
            "presets": {"standard": {"provider": "claude-code", "model": "claude-opus-5-5"}},
            "providers": [
                {"id": "xai-grok-oauth", "models": [{"id": "grok-4.7", "name": "Grok 4.7"}]},
                {"id": "kimi-code", "models": [{"id": "k3", "name": "Kimi K3"}]},
            ],
            "custom": [],
        }
        self.assertEqual(resolve_choice(catalog, "default"), "")
        self.assertEqual(resolve_choice(catalog, "grok-4.7"), "xai-grok-oauth/grok-4.7")
        self.assertEqual(resolve_choice(catalog, "standard"), "claude-code/claude-opus-5-5")
        with self.assertRaises(ValueError):
            resolve_choice(catalog, "nope")


class GateTest(unittest.TestCase):
    def test_always_blocks_builtin_browser_only_when_ready(self):
        from hermes_plugins.aside_browser.gate import should_block
        policy = {"browser_policy": "always"}
        self.assertTrue(should_block("browser_navigate", policy, True))
        self.assertTrue(should_block("open_preview", policy, True))
        self.assertFalse(should_block("browser_navigate", policy, False))
        self.assertFalse(should_block("aside_exec", policy, True))
        self.assertFalse(should_block("computer_use", policy, True))
        self.assertFalse(should_block("browser_navigate", {"browser_policy": "prefer"}, True))
