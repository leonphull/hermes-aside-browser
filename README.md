# hermes-aside-browser

Hermes Agent uses the signed-in [Aside](https://aside.com) browser when the Aside CLI is installed, and keeps its own browser as the fallback.

Aside's CLI already speaks MCP (`exec`, `repl`, `memory_search`) and ships a thin skill for Codex, Claude Code, Cursor, and OpenCode. Hermes is not in that installer. This repo is the Hermes package: a plugin toolset, a skill, and the catalog entry that puts Aside in Connectors.

## What Hermes does with it

When Aside is ready, browser work goes to Aside instead of `browser_navigate`. Logged-in sites, the current Aside tab, and localhost stay in the user's real browser. If the CLI is missing or the app is closed, the agent says so once and uses Hermes's built-in browser or `web_extract`. Nothing here downloads or installs Aside.

## Install

Plugin (Tools + Skills):

```bash
hermes plugins install leonphull/hermes-aside-browser --enable
```

Connector (the vendor MCP tools):

```bash
hermes mcp add aside --command aside --args mcp
```

If `aside` is not on the PATH Hermes uses, pass the absolute path. On macOS that is often `~/.local/bin/aside`. Start a new Hermes session after either install. The connector tools are `mcp__aside__exec`, `mcp__aside__repl`, and `mcp__aside__memory_search`.

Skill only, from this tap:

```bash
hermes skills tap add leonphull/hermes-aside-browser
hermes skills install leonphull/hermes-aside-browser/aside-browser
```

Do not point `aside skills install` at Hermes. That installer does not know Hermes, and its skill tells the agent to run a remote installer script. This package refuses to do that.


## Choose the subscription

Each Hermes profile keeps its own choice. Empty means Aside's own default, which is whatever you set in Aside (plan model or a connected provider).

```bash
hermes aside models
hermes aside use default
hermes aside use xai-grok-oauth/grok-4.7
hermes aside use standard
hermes aside host local
hermes aside host clear
hermes aside account u0
hermes aside permission ask
hermes aside status
```

`hermes aside permission` takes `ask`, `guard`, or `full-access` (`clear` resets to `ask`). Run it once with the level you want. It is a user-only profile setting, defaults to `ask`, and is not a tool argument. `hermes aside host local` pins the literal host `local`. `hermes aside host clear` (or `default`) removes the pin, and Aside's own default host applies; `hermes aside account clear` does the same for the account. The plugin tools have no host, account, or permission arguments. Any such value a model sends anyway is removed before the profile settings are merged, so an unset host or account cannot be redirected by a hidden value. A different model, effort, or speed named for one turn still wins over the matching profile pin. The tool argument `profile` is an Aside browser profile id on the selected host (see `aside host profiles`); it is not a Hermes profile and not an Aside account.

`hermes aside models` lists only the Aside default, presets, and custom models from `settings.json`. The plugin never opens `models.json`, which holds provider configurations and may contain keys.

## Surfaces

| Hermes UI | What you get |
| --- | --- |
| Plugins | `aside-browser`, tools `aside_status`, `aside_exec`, `aside_repl`, `aside_session`, `aside_memory` |
| Connectors | `aside` MCP server |
| Skills | `aside-browser` |

If both the connector and plugin tools are loaded, the skill always uses plugin `aside_exec`, so the user's permission setting (effective default `ask`) and pins apply. It uses plugin `aside_repl` when a host or account is pinned, and plugin `aside_memory` when an account is pinned. With no such pin, the connector's repl and memory_search are allowed (repl state persists there). Session list, stop, archive, and delete use the plugin (the account pin applies).

Existing sessions are not continued through this plugin. `aside session resume`, `steer`, and `queue` accept only `--account`, and the plugin has no verified way to read an existing session's permission or host, so `aside_exec` with `session_id` and `aside_session` with `resume`, `steer`, or `queue` fail closed with `POLICY_UNVERIFIED` before anything runs. Start a new `aside_exec` without `session_id` instead; it applies the permission setting and the host, account, and model pins. If the profile policy is unreadable or holds an invalid value, every tool fails closed with `POLICY_INVALID` (the permission defaults to `ask` only when it is unset).

The permission setting applies to `aside_exec` only. `aside_repl` runs vendor JavaScript scripting, and the vendor MCP connector and the terminal run the `aside` CLI directly; all of these are outside this wrapper's guarantees, so `ask` does not protect everything Aside can do. The connector is a separate vendor surface. `mcp__aside__exec` and the other connector tools are outside these protections; the skill routes work to the plugin tools, but that is guidance and does not technically lock the connector. Remove the connector (`hermes mcp remove aside`) if you need that enforced.

## Disclosure

Installing this runs the local `aside` executable and can drive the user's real browser, including signed-in sites. It can read page text, screenshots saved by a script, and Aside memory snippets. It does not read Hermes credential files, browser cookies, or password stores, and it does not send telemetry. The plugin never opens or parses `~/.aside/u/*/models.json`. The `aside` connector is not covered by the plugin's permission, host, or account protections. Network access happens inside Aside, not in this package. Permission is a user profile setting that defaults to `ask`, not a tool argument. Archive and delete require `confirm=true`.

## Catalog

`catalog/optional-mcps/aside/manifest.yaml` is the Connectors entry for a pull request to `NousResearch/hermes-agent`. A plugin-catalog pin belongs in a follow-up once this repo has a reviewed commit SHA.

## Development

```bash
python3 -m unittest tests/test_aside_cli.py
hermes plugins validate .
```
