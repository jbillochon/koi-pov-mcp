# Troubleshooting

## Installation and startup

**Tools never appear in Claude**
- JSON syntax error in the Claude config (trailing comma is the usual
  suspect), or wrong `command` path. On Windows check the `.exe` suffix and
  double backslashes.
- Claude Desktop not fully restarted: quit from the tray/menu bar, not just
  the window.

**Installer fails on the config step**
- The merge is loud by design: it refuses to touch an existing config that
  is not valid JSON. Fix the file and re-run. Works on Windows PowerShell
  5.1 and pwsh (JSON handling is delegated to the venv's Python).

## Tenants and credentials

**`koi_tenants` shows no tenants**
- None added yet: `koi-pov-mcp tenants add <alias>`, or ask Claude to "add a
  tenant" (native dialog). Applies without restart.

**`AUTH FAILED (401)`**
- Key rejected. Regenerate it in the Koi console, then re-add the alias
  (overwrites).

**`Unknown tenant`**
- Alias typo. `koi-pov-mcp tenants list` (or the `koi_tenants` tool) shows
  what the server actually sees.

**The credential dialog does not appear**
- It may open behind other windows: check the taskbar.
- "tkinter missing": the Python used to build the venv has no Tk (some
  minimal Linux installs: `apt install python3-tk`, then reinstall). The
  CLI fallback always works.
- It auto-cancels after 3 minutes without input; nothing is saved.

**Keyring fallback warning**
- No OS credential backend (headless Linux, some WSL): the key went to a
  permission-restricted `tenants.json`. On desktop Linux install
  `gnome-keyring` or KWallet for the real store.

**XSIAM `401 unauthorized`**
- Check all three values, and whether the key is standard or advanced: a
  standard key sent with advanced auth (or the reverse) is a guaranteed 401.
  Re-add via the dialog with the correct checkbox state, or
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

## Where things are

- State: `KOI_POV_WORKDIR`, or the OS user-data dir
  (Windows `%LOCALAPPDATA%\koi-pov-mcp`, macOS
  `~/Library/Application Support/koi-pov-mcp`, Linux
  `~/.local/share/koi-pov-mcp`)
- Venv: `~/.koi-pov-mcp/venv`
- Skill: `~/.claude/skills/koi-pov-deliverables`
- Claude Desktop config: `%APPDATA%\Claude\claude_desktop_config.json` /
  `~/Library/Application Support/Claude/...` / `~/.config/Claude/...`
