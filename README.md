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

## Surfaces

| Hermes UI | What you get |
| --- | --- |
| Plugins | `aside-browser`, tools `aside_status`, `aside_exec`, `aside_repl`, `aside_session`, `aside_memory` |
| Connectors | `aside` MCP server |
| Skills | `aside-browser` |

If both the connector and the plugin tools are loaded, the skill uses the connector for exec, repl, and memory (repl state persists there) and the plugin for session steer, queue, and stop.

## Disclosure

Installing this runs the local `aside` executable and can drive the user's real browser, including signed-in sites. It can read page text, screenshots saved by a script, and Aside memory snippets. It does not read Hermes credential files, browser cookies, or password stores, and it does not send telemetry. Network access happens inside Aside, not in this package. `permission=full-access` is off unless a caller sets it. Archive and delete require `confirm=true`.

## Catalog

`catalog/optional-mcps/aside/manifest.yaml` is the Connectors entry for a pull request to `NousResearch/hermes-agent`. A plugin-catalog pin belongs in a follow-up once this repo has a reviewed commit SHA.

## Development

```bash
python3 -m unittest tests/test_aside_cli.py
hermes plugins validate .
```
