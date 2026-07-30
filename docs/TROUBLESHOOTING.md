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
- A running MCP server holds `venv\Scripts\koi-pov-mcp.exe` open. **Quit
  Claude Desktop first**, from the tray, and end any Claude Code session.
- Never run `--force-reinstall` against a running server. pip uninstalls
  before it installs, so it removes the package, then fails on the locked
  `.exe`, and leaves nothing to start: the server disconnects on the next
  launch.
- If an interrupted upgrade left a `~oi_pov_mcp` (or similar) directory in
  `venv\Lib\site-packages`, delete it and reinstall:
  ```powershell
  $sp = "$env:USERPROFILE\.koi-pov-mcp\venv\Lib\site-packages"
  Get-ChildItem $sp -Filter '~*' | Remove-Item -Recurse -Force
  & "$env:USERPROFILE\.koi-pov-mcp\venv\Scripts\python.exe" -m pip install `
      --no-cache-dir "git+https://github.com/jbillochon/koi-pov-mcp.git"
  ```
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

**"the capture page is running but has not reported its URL yet"**
- **Check the browser first.** This message means the page process is alive,
  so a tab has usually already opened and is waiting for the key. The
  earlier wording claimed failure here, which sent operators to the terminal
  fallback while the form sat open in front of them.
- The address is also on disk. The page writes it to
  `%TEMP%\koi-pov-capture-koi-<alias>.log` (`$TMPDIR` on macOS/Linux), first
  line, `URL http://127.0.0.1:<port>/?t=<token>`. Open it manually; the page
  expires 5 minutes after it started.
- Versions before 0.8.0 read that URL through an anonymous pipe. Driven from
  a terminal it arrived in milliseconds; spawned from inside Claude Desktop
  on an EDR-managed workstation it did not arrive at all, and the tool
  reported failure while the page was open. 0.8.0 reads the file instead.
- Also fixed in 0.8.0: when a host started the server through
  `koi-pov-mcp.exe`, `sys.executable` was that wrapper rather than python, so
  the capture page was launched as `koi-pov-mcp.exe -m koi_pov_mcp.gui ...`
  and died on the CLI's argument parser. Symptom: an immediate error quoting
  `usage: koi-pov-mcp [-h] {serve,tenants,xsiam}`.

**No browser tab opens and no URL is given**
- The capture process could not start at all. The terminal fallback is
  equivalent and writes to the same store:
  `koi-pov-mcp tenants add <alias> --test` (or `xsiam add`).
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

**A format is listed under `skipped`**
- The reason is in the value. One failing format never sinks the others, so
  a call that produced two documents out of three is not a full delivery and
  must be reported as such.
- The PDF is drawn with reportlab and has no system dependency. If it is
  skipped for a missing import, reinstall the package rather than installing
  GTK: WeasyPrint is not used here.

**`validation.dropped` is not empty**
- A finding or scenario cited something that could not be found in the
  snapshot, so the whole block was removed rather than shipped with an
  unverifiable claim. `validation.issues` names the reference and why it
  failed.
- The usual cause is citing an item by a name that does not appear in the
  collected lists. Cite items **by name as they appear in
  `pov_report_json`**; `item_id` exists only on `action_candidates`.
- A legitimate citation being rejected on a very short item name means the
  substring floor in `rendering/narrative.py` is too high for that name.

**A `prose_number` issue**
- A figure was written by hand into narrative prose. Every number shown to a
  customer must come from the snapshot, and the data sections already render
  them. Rewrite the sentence qualitatively ("a small number of endpoints")
  and let the tables carry the counts.

**A supply-chain dimension shows no total but names items**
- Working as intended. The collector caps `finding_frequency`, so findings
  outside the cut total zero while named items still carry them. The
  renderers print "this snapshot did not record an estate-wide count"
  rather than a zero that would tell a customer they have no active
  compromise indicators while a malicious item sits in the same document.

**`[[TO BE PROVIDED]]` in the output**
- Working as intended: a narrative section was not written/validated, or a
  data section had nothing collected. It is an action item, not a rendering
  bug; fix the input, not the placeholder.

## Logs and locations

- MCP server log (Windows):
  `%APPDATA%\Claude\logs\mcp-server-koi-pov.log`
- Credential page log: `%TEMP%\koi-pov-capture-<mode>-<alias>.log`
- State: `KOI_POV_WORKDIR`, or the OS user-data dir
  (Windows `%LOCALAPPDATA%\koi-pov-mcp`, macOS
  `~/Library/Application Support/koi-pov-mcp`, Linux
  `~/.local/share/koi-pov-mcp`)
- Venv: `~/.koi-pov-mcp/venv`
- Skill: `~/.claude/skills/koi-pov-deliverables`
- Claude Desktop config: `%APPDATA%\Claude\claude_desktop_config.json` /
  `~/Library/Application Support/Claude/...` / `~/.config/Claude/...`
