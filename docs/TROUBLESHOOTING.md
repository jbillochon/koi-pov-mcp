# Troubleshooting

## Installation and updates

**Tools never appear in Claude**
- JSON syntax error in the Claude config (trailing comma is the usual
  suspect), or wrong `command` path. On Windows check the `.exe` suffix and
  double backslashes.
- Claude Desktop not fully restarted: quit from the tray/menu bar, not just
  the window. Claude Code: exit and relaunch the session.

**Installer fails on the config step**
- The merge is loud by design: it refuses to touch an existing config that
  is not valid JSON. Fix the file and re-run. Works on Windows PowerShell
  5.1 and pwsh (JSON handling is delegated to the venv's Python).

**`pip install --upgrade .` fails: file in use / access denied**
- A running MCP server holds `venv\Scripts\koi-pov-mcp.exe` open. Quit
  Claude Desktop (from the tray) and any Claude Code session, then re-run.
- If an interrupted upgrade left a `~oi-pov-mcp` (or similar) directory in
  `venv\Lib\site-packages`, delete it: it is a rename residue and causes pip
  warnings on every later command.
- To check what is holding it on Windows:
  `Get-Process | Where-Object { $_.Path -like "*koi-pov-mcp*" }`
- After upgrading, restart Claude Desktop and run `/mcp` in Claude Code to
  reload the server.

## Tenants and credentials

**`koi_tenants` shows no tenants**
- None added yet: ask Claude to "add a tenant", or run
  `koi-pov-mcp tenants add <alias>`. Applies without restart.

**`AUTH FAILED (401)`**
- Key rejected. Regenerate it in the Koi console, then re-add the alias
  (overwrites).

**`Unknown tenant`**
- Alias typo. `koi-pov-mcp tenants list` (or the `koi_tenants` tool) shows
  what the server actually sees.

**No browser tab opens for the credential page**
- Claude relays the URL in its answer: open it manually, the page is already
  running and waits 5 minutes.
- If there is no URL either, the capture process could not start; use the
  terminal fallback, which is equivalent:
  `koi-pov-mcp tenants add <alias> --test` (or `xsiam add`).
- Note for versions before 0.7.1: capture used a native Tk window that
  Claude Desktop did not reliably surface on Windows (the operator saw
  nothing until the timeout). Upgrade to 0.7.1+, which uses the browser.
- Tk is still available if preferred:
  `python -m koi_pov_mcp.gui koi <alias> --tk`.

**Keyring fallback warning**
- No OS credential backend (headless Linux, some WSL): the key went to a
  permission-restricted `tenants.json`. On desktop Linux install
  `gnome-keyring` or KWallet for the real store.

**XSIAM `401 unauthorized`**
- Check all three values, and whether the key is standard or advanced: a
  standard key sent with advanced auth (or the reverse) is a guaranteed 401.
  Re-add with the correct checkbox state, or
  `koi-pov-mcp xsiam add <alias> --advanced`.

## Collection

**Sync is slow**
- Expected: 30 requests/minute per route, 500 items per page. Scope domains
  ("sync only inventory") or lower `max_pages` for a first pass.

**A domain shows in `warnings`**
- That domain failed and is **not measured**; the others are unaffected.
  Retry it alone: "sync only <domain> of <alias>". Warnings feed the gap
  list and never reach the customer document as zeros.

**`agent_activity` looks incomplete**
- API windows: sessions cover up to 30 days, events are capped at 24 hours.
  The collector already respects both; it is a platform limit, not a bug.

## Enrichment

**`koi_enrich` takes minutes**
- NVD pacing: ~6.5s per CVE unauthenticated. Add `NVD_API_KEY` to the server
  env (~1.2s), or lower `max_cves`. OSV/KEV/EPSS are fast batch calls.

**No OSV matches**
- Only npm and PyPI items with an exact name@version are queried; other
  marketplaces are deliberately skipped rather than guessed.

## Deliverables

**PDF skipped**
- WeasyPrint missing: `pip install 'koi-pov-mcp[pdf]'`. On Windows it also
  needs the GTK runtime; DOCX and PPTX never depend on it.

**`[[TO BE PROVIDED]]` in the output**
- Working as intended: a narrative section was not written/validated, or a
  data section had nothing collected. It is an action item, not a rendering
  bug; fix the input, not the placeholder.

## Logs and locations

- MCP server log (Windows):
  `%APPDATA%\Claude\logs\mcp-server-koi-pov.log`
- State: `KOI_POV_WORKDIR`, or the OS user-data dir
  (Windows `%LOCALAPPDATA%\koi-pov-mcp`, macOS
  `~/Library/Application Support/koi-pov-mcp`, Linux
  `~/.local/share/koi-pov-mcp`)
- Venv: `~/.koi-pov-mcp/venv`
- Skill: `~/.claude/skills/koi-pov-deliverables`
- Claude Desktop config: `%APPDATA%\Claude\claude_desktop_config.json` /
  `~/Library/Application Support/Claude/...` / `~/.config/Claude/...`
