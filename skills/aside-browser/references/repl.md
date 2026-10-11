# Aside repl contract

Verified against Aside CLI 1.26.1010.1739 via `aside guide repl` and `aside mcp` tools/list on 2026-10-11. If a call fails after an Aside update, run `aside guide repl` and follow that output instead of this page.

## Which repl

- `mcp__aside__repl` is a persistent sandbox. `const` and `let` survive across calls. Use fresh names.
- `aside_repl` and `aside repl "..."` are one-shot. The temporary session closes when the command returns. Put open, act, and read in one script.

Both have a 120 second timeout. No `import` or `require`. Print results with `console.log`.

MCP `repl` arguments are `title` and `code`. MCP `exec` arguments are `prompt` and optional `session_id`. MCP `memory_search` arguments are `queries` (1-3) and optional `max_results`.

## Globals

`page`, `tabs`, `listBrowserTabs()`, `attachBrowserTab(targetId)`, `attachActiveBrowserTab()`, `getTabByTargetId(targetId)`, `openTab(url)`, `closeTab(tab)`, `snapshot(page, options?)`, `annotatedScreenshot(page)`, `page.screenshot()`, `page.pdf(options?)`, `fetch(url)`, `fs`, `path`, `Buffer`, `sleep`, `display`, `pwd`.

`page` starts unset. Call `openTab(url)` or attach a tab the user named before reading it. Use `openTab` and `closeTab`, not `page.context().newPage()` or `page.close()`.

## Snapshot

`snapshot(page, { interactive: true })` is the first read. It returns `{ tree, diff }`. Refs such as `e12` are locator ids: `page.locator('e12')`. They die on the next snapshot. After an action, print `diff`. Do not truncate the tree and do not guess refs.

Escalation: interactive snapshot, full snapshot, one more snapshot only if the page is still changing, then `annotatedScreenshot(page)` or `page.screenshot()`. Avoid `page.content()` and `page.evaluate()` unless the selector is already known.

## Artifacts

Save PDFs and downloads under `./artifacts/`. `fs` cannot browse `~/Downloads`. In a one-shot CLI call, verify a download inside that same script.
