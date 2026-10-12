"""Unit tests for the Aside CLI wrapper. No live browser required."""

from __future__ import annotations

import argparse
import json
import os
import re
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
catalog = importlib.import_module("hermes_plugins.aside_browser.catalog")
cli = importlib.import_module("hermes_plugins.aside_browser.cli")
policy = importlib.import_module("hermes_plugins.aside_browser.policy")
tools = importlib.import_module("hermes_plugins.aside_browser.tools")
SKILL_DESCRIPTION = plugin.SKILL_DESCRIPTION

_RECORD_OPENS = False
_OPEN_PATHS: list[str] = []


def _record_open(event: str, args: tuple) -> None:
    if _RECORD_OPENS and event == "open":
        _OPEN_PATHS.append(str(args[0]))


sys.addaudithook(_record_open)


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

    def test_exec_args_has_no_session_continuation(self):
        with self.assertRaises(TypeError):
            aside_cli.exec_args("continue", session_id="ses_abc", account="u0")
        with self.assertRaises(ValueError):
            aside_cli.session_args("resume", session_id="ses_abc")
        for action in ("steer", "queue"):
            with self.assertRaises(ValueError):
                aside_cli.session_args(action, session_id="ses_abc")
        self.assertEqual(aside_cli.session_args("stop", session_id="ses_abc", account="u0"),
                         ["session", "stop", "--account", "u0", "ses_abc"])
        self.assertEqual(aside_cli.session_args("list"), ["session", "list"])

    def test_rejects_flag_injection(self):
        with self.assertRaises(ValueError):
            aside_cli.exec_args("ok", account="--permission")

    def test_full_access_only_when_asked(self):
        argv = aside_cli.exec_args("ok")
        self.assertNotIn("full-access", argv)
        argv = aside_cli.exec_args("ok", permission="full-access")
        self.assertIn("full-access", argv)

    def test_rejects_invalid_permission(self):
        with self.assertRaises(ValueError):
            aside_cli.exec_args("ok", permission="yolo")

    def test_repl_and_memory(self):
        self.assertEqual(aside_cli.repl_args("console.log(1)"), ["repl", "console.log(1)"])
        self.assertEqual(
            aside_cli.memory_args("stripe", max_results=3),
            ["memory", "search", "--json", "-n", "3", "stripe"],
        )


class ToolGuardTest(unittest.TestCase):
    def setUp(self):
        tools.set_policy_loader(lambda: {})

    def tearDown(self):
        tools.set_policy_loader(lambda: {})

    def test_delete_requires_confirm(self):
        payload = json.loads(tools.aside_session({"action": "delete", "session_id": "ses_abc"}))
        self.assertEqual(payload["status"], "CONFIRM_REQUIRED")

    def test_empty_prompt(self):
        payload = json.loads(tools.aside_exec({"prompt": "  "}))
        self.assertEqual(payload["status"], "INVALID_INPUT")

    def test_probe_needs_aside(self):
        with mock.patch.object(aside_cli, "find_aside", return_value=None), mock.patch.object(catalog, "load_catalog", return_value={}):
            payload = json.loads(tools.aside_status({}))
        self.assertEqual(payload["status"], "NEEDS_ASIDE")
        self.assertNotIn("curl", payload["message"])
        self.assertEqual(payload["resolved"]["permission"], "ask")

    def test_probe_ready(self):
        with mock.patch.object(aside_cli, "find_aside", return_value="/bin/aside"), mock.patch.object(catalog, "load_catalog", return_value={}):
            with mock.patch.object(
                aside_cli,
                "run_aside",
                return_value={"ok": True, "status": "OK", "exit_code": 0, "stdout": "ASIDE_READY", "stderr": ""},
            ):
                payload = json.loads(tools.aside_status({}))
        self.assertEqual(payload["status"], "READY")

    def test_status_shows_profile_permission(self):
        tools.set_policy_loader(lambda: {"permission": "guard"})
        with mock.patch.object(aside_cli, "probe", return_value={"status": "READY"}), mock.patch.object(catalog, "load_catalog", return_value={}):
            payload = json.loads(tools.aside_status({}))
        self.assertEqual(payload["resolved"]["permission"], "guard")

    def test_locked_arguments_are_absent_from_schemas(self):
        forbidden = {
            "aside_exec": {"permission", "host", "account", "session_id"},
            "aside_repl": {"host", "account"},
            "aside_session": {"account", "prompt"},
            "aside_memory": {"account"},
        }
        for name, keys in forbidden.items():
            properties = tools.SCHEMAS[name]["function"]["parameters"]["properties"]
            self.assertTrue(keys.isdisjoint(properties), name)
        actions = tools.SCHEMAS["aside_session"]["function"]["parameters"]["properties"]["action"]["enum"]
        self.assertEqual(actions, ["list", "stop", "archive", "delete"])

    def test_pinned_host_and_account_override_all_handlers(self):
        tools.set_policy_loader(lambda: {"host": "mini", "account": "u0"})
        calls = [
            (tools.aside_exec, {"prompt": "go", "host": "evil", "account": "u9"}),
            (tools.aside_repl, {"code": "console.log(1)", "host": "evil", "account": "u9"}),
            (tools.aside_session, {"action": "list", "account": "u9"}),
            (tools.aside_memory, {"queries": ["go"], "account": "u9"}),
        ]
        captured = []

        def capture(argv, timeout):
            captured.append(argv)
            return {"ok": True}

        with mock.patch.object(aside_cli, "find_aside", return_value="/bin/aside"), mock.patch.object(aside_cli, "run_aside", side_effect=capture):
            for handler, args in calls:
                handler(args)
        for argv in captured:
            self.assertIn(["--account", "u0"], [argv[i:i + 2] for i in range(len(argv) - 1)])
            self.assertNotIn("u9", argv)
        for argv in captured[:2]:
            self.assertIn(["--host", "mini"], [argv[i:i + 2] for i in range(len(argv) - 1)])
            self.assertNotIn("evil", argv)

    def test_unpinned_host_and_account_hidden_values_are_dropped(self):
        tools.set_policy_loader(lambda: {})
        captured = []

        def capture(argv, timeout):
            captured.append(argv)
            return {"ok": True}

        with mock.patch.object(aside_cli, "find_aside", return_value="/bin/aside"), mock.patch.object(aside_cli, "run_aside", side_effect=capture):
            tools.aside_exec({"prompt": "go", "host": "evil", "account": "u9"})
            tools.aside_repl({"code": "console.log(1)", "host": "evil", "account": "u9"})
            tools.aside_session({"action": "list", "account": "u9"})
            tools.aside_memory({"queries": ["go"], "account": "u9"})
        self.assertEqual(len(captured), 4)
        for argv in captured:
            self.assertNotIn("--account", argv)
            self.assertNotIn("--host", argv)
            self.assertNotIn("u9", argv)
            self.assertNotIn("evil", argv)

    def test_pinned_local_host_is_passed_through(self):
        tools.set_policy_loader(lambda: {"host": "local"})
        captured = []

        def capture(argv, timeout):
            captured.append(argv)
            return {"ok": True}

        with mock.patch.object(aside_cli, "find_aside", return_value="/bin/aside"), mock.patch.object(aside_cli, "run_aside", side_effect=capture):
            tools.aside_exec({"prompt": "go", "host": "evil"})
            tools.aside_repl({"code": "console.log(1)", "host": "evil"})
        for argv in captured:
            self.assertIn(["--host", "local"], [argv[i:i + 2] for i in range(len(argv) - 1)])
            self.assertNotIn("evil", argv)

    def test_permission_only_comes_from_policy(self):
        captured = []

        def capture(argv, timeout):
            captured.append(argv)
            return {"ok": True}

        with mock.patch.object(aside_cli, "find_aside", return_value="/bin/aside"), mock.patch.object(aside_cli, "run_aside", side_effect=capture):
            tools.aside_exec({"prompt": "go", "permission": "full-access"}, permission="full-access")
            tools.set_policy_loader(lambda: {"permission": "ask"})
            tools.aside_exec({"prompt": "go", "permission": "full-access"}, permission="full-access")
            tools.set_policy_loader(lambda: {"permission": "full-access"})
            tools.aside_exec({"prompt": "go", "permission": "ask"}, permission="ask")
        self.assertIn(["--permission", "ask"], [captured[0][i:i + 2] for i in range(len(captured[0]) - 1)])
        self.assertIn(["--permission", "ask"], [captured[1][i:i + 2] for i in range(len(captured[1]) - 1)])
        self.assertIn(["--permission", "full-access"], [captured[2][i:i + 2] for i in range(len(captured[2]) - 1)])


class SessionFailClosedTest(unittest.TestCase):
    BAD_CALLS = [
        (tools.aside_exec, {"prompt": "go", "session_id": "ses_abc"}),
        (tools.aside_exec, {"prompt": "go", "session_id": " ses_abc "}),
        (tools.aside_exec, {"prompt": "go", "session_id": "bogus"}),
        (tools.aside_session, {"action": "resume", "session_id": "ses_abc", "prompt": "go"}),
        (tools.aside_session, {"action": "steer", "session_id": "ses_abc", "prompt": "go"}),
        (tools.aside_session, {"action": "queue", "session_id": "ses_abc", "prompt": "go"}),
        (tools.aside_session, {"action": " Resume ", "session_id": "ses_abc", "prompt": "go"}),
    ]

    def setUp(self):
        tools.set_policy_loader(lambda: {"account": "u0", "host": "mini", "permission": "full-access"})

    def tearDown(self):
        tools.set_policy_loader(lambda: {})

    def _run(self, handler, args, **kwargs):
        with mock.patch.object(aside_cli, "find_aside", return_value="/bin/aside"), \
                mock.patch.object(aside_cli.subprocess, "run") as run, \
                mock.patch.object(aside_cli, "run_aside") as run_aside:
            payload = json.loads(handler(args, **kwargs))
        run.assert_not_called()
        run_aside.assert_not_called()
        return payload

    def test_continuation_never_reaches_subprocess(self):
        for handler, args in self.BAD_CALLS:
            payload = self._run(handler, args)
            self.assertFalse(payload["ok"], args)
            self.assertEqual(payload["status"], "POLICY_UNVERIFIED", args)
            self.assertIn("new aside_exec", payload["message"])

    def test_continuation_blocked_via_injected_kwargs_and_dict_shapes(self):
        payload = self._run(tools.aside_exec, {"prompt": "go", "session_id": "ses_abc"}, session_id="ses_other", task_id="t")
        self.assertEqual(payload["status"], "POLICY_UNVERIFIED")
        # Injected Hermes context kwargs never turn a fresh exec into a continuation or a block.
        captured = []
        with mock.patch.object(aside_cli, "find_aside", return_value="/bin/aside"), \
                mock.patch.object(aside_cli, "run_aside", side_effect=lambda argv, timeout: captured.append(argv) or {"ok": True}):
            tools.aside_exec({"prompt": "go"}, session_id="ses_injected", task_id="t")
        self.assertEqual(captured[0][0], "exec")
        self.assertNotIn("ses_injected", captured[0])
        for bad in (None, "ses_abc", ["ses_abc"]):
            self.assertIn(json.loads(tools.aside_session(bad))["status"], {"INVALID_INPUT"})

    def test_blocked_even_when_policy_is_invalid(self):
        tools.set_policy_loader(lambda: {"permission": "yolo"})
        payload = self._run(tools.aside_exec, {"prompt": "go", "session_id": "ses_abc"})
        self.assertEqual(payload["status"], "POLICY_UNVERIFIED")

    def test_fresh_exec_runs_with_all_pins_via_mocked_subprocess(self):
        done = mock.Mock(returncode=0, stdout="[ok] ses_new1", stderr="")
        with mock.patch.object(aside_cli, "find_aside", return_value="/bin/aside"), \
                mock.patch.object(aside_cli.subprocess, "run", return_value=done) as run:
            payload = json.loads(tools.aside_exec({"prompt": "go", "permission": "ask", "account": "u9"}))
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["session_ids"], ["ses_new1"])
        argv = run.call_args.args[0]
        self.assertEqual(
            argv, ["/bin/aside", "exec", "--account", "u0", "--host", "mini", "--permission", "full-access", "go"]
        )

    def test_list_stop_archive_delete_still_work(self):
        done = mock.Mock(returncode=0, stdout="[ok]", stderr="")
        expected = {
            "list": ["session", "list", "--account", "u0"],
            "stop": ["session", "stop", "--account", "u0", "ses_abc"],
            "archive": ["session", "archive", "--account", "u0", "ses_abc"],
            "delete": ["session", "delete", "--account", "u0", "ses_abc"],
        }
        for action, tail in expected.items():
            with mock.patch.object(aside_cli, "find_aside", return_value="/bin/aside"), \
                    mock.patch.object(aside_cli.subprocess, "run", return_value=done) as run:
                payload = json.loads(
                    tools.aside_session({"action": action, "session_id": "ses_abc", "confirm": True, "account": "u9"})
                )
            self.assertTrue(payload["ok"], action)
            self.assertEqual(run.call_args.args[0], ["/bin/aside", *tail])


class PolicyFailClosedTest(unittest.TestCase):
    def tearDown(self):
        tools.set_policy_loader(lambda: {})

    def _argv(self, loader, handler=tools.aside_exec, args=None):
        tools.set_policy_loader(loader)
        captured = []
        with mock.patch.object(aside_cli, "find_aside", return_value="/bin/aside"), \
                mock.patch.object(aside_cli, "run_aside", side_effect=lambda argv, timeout: captured.append(argv) or {"ok": True}):
            payload = json.loads(handler(args or {"prompt": "go"}))
        return payload, captured

    def test_empty_policy_still_enforces_ask(self):
        for loader in (lambda: {}, lambda: None, lambda: {"permission": ""}, lambda: {"permission": "  "}):
            _, captured = self._argv(loader)
            argv = captured[0]
            self.assertIn(["--permission", "ask"], [argv[i:i + 2] for i in range(len(argv) - 1)])

    def test_invalid_policy_fails_closed_without_subprocess(self):
        bad_loaders = [
            lambda: {"permission": "yolo"},
            lambda: {"permission": "FULL-ACCESS"},
            lambda: {"permission": "ask", "effort": "turbo"},
            lambda: {"permission": "ask", "speed": "warp"},
            lambda: ["ask"],
            lambda: "full-access",
            lambda: (_ for _ in ()).throw(RuntimeError("boom")),
        ]
        calls = [
            (tools.aside_exec, {"prompt": "go"}),
            (tools.aside_repl, {"code": "console.log(1)"}),
            (tools.aside_session, {"action": "list"}),
            (tools.aside_memory, {"queries": ["x"]}),
        ]
        for loader in bad_loaders:
            for handler, args in calls:
                payload, captured = self._argv(loader, handler, args)
                self.assertFalse(payload["ok"])
                self.assertEqual(payload["status"], "POLICY_INVALID")
                self.assertEqual(captured, [])

    def test_status_reports_invalid_policy_not_full_access(self):
        tools.set_policy_loader(lambda: {"permission": "yolo"})
        with mock.patch.object(aside_cli, "probe", return_value={"status": "READY", "ok": True}), \
                mock.patch.object(catalog, "load_catalog", return_value={}):
            payload = json.loads(tools.aside_status({}))
        self.assertEqual(payload["status"], "POLICY_INVALID")
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["resolved"]["permission"], "invalid")


class SkillTest(unittest.TestCase):
    def test_description_matches_index_and_length(self):
        text = (ROOT / "skills" / "aside-browser" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn(f"description: {SKILL_DESCRIPTION}", text)
        self.assertLessEqual(len(SKILL_DESCRIPTION), 60)
        self.assertTrue(SKILL_DESCRIPTION.endswith("."))
        self.assertNotIn("curl ", text)
        self.assertIn("browser_navigate", text)

    def test_descriptions_route_exec_through_plugin(self):
        texts = {name: schema["function"]["description"] for name, schema in tools.SCHEMAS.items()}
        self.assertNotIn("use that instead", texts["aside_exec"])
        self.assertIn("required route", texts["aside_exec"])
        self.assertIn("Do not use mcp__aside__exec", texts["aside_exec"])
        self.assertIn("permission", texts["aside_exec"])
        self.assertIn("POLICY_UNVERIFIED", texts["aside_exec"])
        self.assertNotIn("Pass session_id", texts["aside_exec"])
        self.assertIn("POLICY_UNVERIFIED", texts["aside_session"])
        for word in ("resume", "steer", "queue"):
            self.assertIn(word, texts["aside_session"].lower())
        for name in ("aside_repl", "aside_memory"):
            self.assertNotIn("use that instead", texts[name], name)
            self.assertIn("pins", texts[name], name)
            self.assertIn("With no", texts[name], name)
        self.assertIn("host or account", texts["aside_repl"])
        self.assertIn("account pin", texts["aside_memory"])

    def test_skill_and_readme_routing_is_consistent(self):
        skill = (ROOT / "skills" / "aside-browser" / "SKILL.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("always use `aside_exec`, never `mcp__aside__exec`", skill)
        self.assertNotIn("Otherwise `mcp__aside__exec`", skill)
        self.assertNotIn("profile.model_pin", skill)
        self.assertNotIn("profile` browser policy", skill)
        self.assertIn("POLICY_UNVERIFIED", skill)
        self.assertIn("POLICY_UNVERIFIED", readme)
        self.assertNotIn("not re-applied", skill + readme)
        self.assertNotIn("Plugin pins are not enforced across resume", readme)
        self.assertNotIn("Session steer, queue, and stop use the plugin", readme)
        self.assertNotIn("Pass `session_id` to continue", skill)
        self.assertIn("separate vendor surface", skill)
        self.assertIn("separate vendor surface", readme)
        self.assertNotIn("technically locked", skill + readme)
        self.assertIn("always uses plugin `aside_exec`", readme)

    def test_docs_state_scope_and_no_policy_bypass(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        skill = (ROOT / "skills" / "aside-browser" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("applies to `aside_exec` only", readme)
        self.assertIn("outside this wrapper's guarantees", readme)
        self.assertIn("pins the literal host `local`", readme)
        self.assertIn("not a Hermes profile", readme)
        self.assertIn("Never change the user's Aside policy", skill)
        self.assertIn("do not route around it", skill)
        self.assertIn("outside this wrapper's guarantees", skill)
        self.assertNotIn("always override anything named in a task", readme)
        self.assertNotIn("every tool fails closed", readme)
        self.assertNotIn("Empty means the local machine", (ROOT / "plugin.yaml").read_text(encoding="utf-8"))
        self.assertIn("not guaranteed local", (ROOT / "plugin.yaml").read_text(encoding="utf-8"))

    def test_readme_has_no_invalid_permission_pipeline(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("ask|guard|full-access", readme)
        self.assertIn("\nhermes aside permission ask\n", readme)

    def _host_ctx(self):
        store = {}
        ctx = type(
            "C",
            (),
            {
                "get_config": lambda self, key, default="": store.get(key, default),
                "set_config": lambda self, key, value: store.__setitem__(key, value),
            },
        )()
        return ctx, store

    def test_cli_host_local_saves_literal_local(self):
        ctx, store = self._host_ctx()
        cli.handle(ctx, argparse.Namespace(aside_cmd="host", name="local"))
        self.assertEqual(store["host"], "local")
        self.assertEqual(cli.tool_policy(ctx)["host"], "local")

    def test_cli_host_clear_and_default_unset(self):
        for word in ("clear", "default"):
            ctx, store = self._host_ctx()
            cli.handle(ctx, argparse.Namespace(aside_cmd="host", name="mini"))
            self.assertEqual(store["host"], "mini")
            cli.handle(ctx, argparse.Namespace(aside_cmd="host", name=word))
            self.assertEqual(store["host"], "")
            self.assertEqual(cli.tool_policy(ctx)["host"], "")

    def test_cli_status_distinguishes_local_pin_from_unset(self):
        ctx, store = self._host_ctx()
        probe = {"status": "READY"}
        self.assertIn("Host: Aside's default host", cli.format_status(cli.read_policy(ctx), probe))
        cli.handle(ctx, argparse.Namespace(aside_cmd="host", name="local"))
        self.assertIn("Host: local", cli.format_status(cli.read_policy(ctx), probe))

    def test_status_profile_keys_match_skill_names(self):
        ctx = type("C", (), {"get_config": lambda self, key, default: "", "set_config": lambda self, k, v: None})()
        self.assertEqual(
            set(cli.tool_policy(ctx)), {"model", "host", "account", "effort", "speed", "permission"}
        )

    def test_fresh_exec_applies_all_pins(self):
        argv = aside_cli.exec_args("go", account="u0", host="mini", model="p/m", permission="guard")
        self.assertEqual(
            argv, ["exec", "--account", "u0", "--host", "mini", "--model", "p/m", "--permission", "guard", "go"]
        )

    def test_guide_cannot_override_safety_rules(self):
        text = (ROOT / "skills" / "aside-browser" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("syntax", text)
        self.assertIn("safety rules always override the guide", text)
        self.assertNotIn("the guide wins", text)

    def test_plugin_versions_match(self):
        version = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))["version"]
        yaml = (ROOT / "plugin.yaml").read_text(encoding="utf-8")
        yaml_version = re.search(r"^version: (.+)$", yaml, re.MULTILINE).group(1)
        self.assertEqual(version, yaml_version)
        self.assertEqual(version, "0.3.0")


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

    def test_host_and_account_pins_override_call(self):
        merged = policy.apply_policy({"host": "evil", "account": "u9"}, {"host": "mini", "account": "u0"})
        self.assertEqual(merged["host"], "mini")
        self.assertEqual(merged["account"], "u0")

    def test_unpinned_host_and_account_hidden_values_are_dropped(self):
        for pinned in ({}, None, {"host": "", "account": ""}):
            merged = policy.apply_policy({"host": "evil", "account": "u9", "prompt": "go"}, pinned)
            self.assertNotIn("host", merged)
            self.assertNotIn("account", merged)
            self.assertEqual(merged["prompt"], "go")

    def test_local_host_pin_is_a_literal_value(self):
        merged = policy.apply_policy({"host": "evil"}, {"host": "local"})
        self.assertEqual(merged["host"], "local")

    def test_permission_from_call_is_dropped(self):
        self.assertEqual(policy.apply_policy({"permission": "full-access"}, {})["permission"], "ask")
        self.assertEqual(policy.apply_policy({"permission": "full-access"}, None)["permission"], "ask")
        self.assertEqual(policy.apply_policy({"permission": "full-access"}, {"permission": "ask"})["permission"], "ask")

    def test_model_effort_and_speed_keep_fill_empty_semantics(self):
        merged = policy.apply_policy(
            {"model": "explicit", "effort": "", "speed": "fast"},
            {"model": "pinned", "effort": "high", "speed": "default"},
        )
        self.assertEqual(merged["model"], "explicit")
        self.assertEqual(merged["effort"], "high")
        self.assertEqual(merged["speed"], "fast")

    def test_resolve_unique_and_default(self):
        from hermes_plugins.aside_browser.catalog import resolve_choice
        known = {
            "presets": {"standard": {"provider": "claude-code", "model": "claude-opus-5-5"}},
            "custom": [
                {"provider": "xai-grok-oauth", "id": "grok-4.7", "name": "Grok 4.7"},
                {"provider": "kimi-code", "id": "k3", "name": "Kimi K3"},
            ],
        }
        self.assertEqual(resolve_choice(known, "default"), "")
        self.assertEqual(resolve_choice(known, "grok-4.7"), "xai-grok-oauth/grok-4.7")
        self.assertEqual(resolve_choice(known, "Kimi K3"), "kimi-code/k3")
        legacy = {"providers": [{"id": "x", "models": [{"id": "m", "name": "m"}]}]}
        self.assertEqual(resolve_choice(legacy, "provider/model"), "provider/model")
        with self.assertRaises(ValueError):
            resolve_choice(legacy, "m")
        self.assertEqual(resolve_choice(known, "standard"), "claude-code/claude-opus-5-5")
        with self.assertRaises(ValueError):
            resolve_choice(known, "nope")


class CatalogTest(unittest.TestCase):
    def test_models_json_is_never_opened(self):
        global _RECORD_OPENS
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / ".aside" / "u" / "0"
            folder.mkdir(parents=True)
            (folder / "settings.json").write_text(json.dumps({
                "defaultModel": {"provider": "p", "modelId": "default"},
                "modelCategories": {"standard": {"provider": "p", "modelId": "preset"}},
                "customModels": [{"provider": "custom", "id": "mine", "name": "Mine"}],
            }), encoding="utf-8")
            canary = "SUPERSECRET_CANARY_KEY"
            (folder / "models.json").write_text(json.dumps({
                "providers": {"private": {"apiKey": canary, "baseUrl": "https://private.invalid"}},
            }), encoding="utf-8")
            _OPEN_PATHS.clear()
            with mock.patch.object(Path, "home", return_value=Path(tmp)):
                _RECORD_OPENS = True
                try:
                    current = catalog.load_catalog()
                    explicit = catalog.load_catalog("u0")
                    output = cli.format_models(current)
                finally:
                    _RECORD_OPENS = False
            self.assertFalse(any("models.json" in path for path in _OPEN_PATHS), _OPEN_PATHS)
            self.assertTrue(any("settings.json" in path for path in _OPEN_PATHS))
            self.assertNotIn(canary, str(current) + str(explicit) + output)
            self.assertEqual(current, explicit)
            self.assertEqual(current["default"], {"provider": "p", "model": "default"})
            self.assertEqual(current["presets"]["standard"], {"provider": "p", "model": "preset"})
            self.assertEqual(current["custom"], [{"provider": "custom", "id": "mine", "name": "Mine"}])
            self.assertNotIn("providers", current)
            self.assertIn("p/default", output)
            self.assertIn("p/preset", output)
            self.assertIn("custom/mine", output)
            self.assertNotIn("No connected providers", output)


class CliPermissionTest(unittest.TestCase):
    def test_permission_setting_and_default(self):
        class Context:
            config = {}

            def get_config(self, key, default):
                return self.config.get(key, default)

            def set_config(self, key, value):
                self.config[key] = value

        ctx = Context()
        self.assertEqual(cli.tool_policy(ctx)["permission"], "ask")
        parser = argparse.ArgumentParser()
        cli.build_parser(parser)
        for value in ("guard", "full-access", "clear", "default"):
            args = parser.parse_args(["permission", value])
            with mock.patch("builtins.print"):
                cli.handle(ctx, args)
            self.assertEqual(cli.tool_policy(ctx)["permission"], "ask" if value in {"clear", "default"} else value)
        with self.assertRaisesRegex(SystemExit, "permission must be"):
            cli.handle(ctx, parser.parse_args(["permission", "yolo"]))
        self.assertIn("Permission: ask", cli.format_status(cli.read_policy(ctx), {"status": "READY"}))


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


if __name__ == "__main__":
    unittest.main()
