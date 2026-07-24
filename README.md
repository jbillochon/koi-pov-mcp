# koi-pov-mcp

MCP server + Claude skill to run a **Cortex AES (Koi) Proof of Value** end to end:
collect tenant evidence over the Koi API, review the gaps, and produce the
customer-facing report and restitution deck.

Standalone and cross-platform: **Windows, Linux, macOS**. No Docker, no database,
no running service. One Python package, one skill folder.

> Deployment-independent rewrite of the collection layer of
> [povplatform](https://github.com/jbillochon/povplatform). The Koi client and
> collector are ported from it; nothing here imports or requires povplatform.

## How it works

```
Claude Desktop / Claude Code
        |
        |  MCP tools: koi_ping, set_pov_meta, koi_collect,
        |             pov_status, pov_report_json, pov_reset
        v
  koi-pov-mcp (stdio, local)          skill: koi-pov-deliverables
        |                              (editorial rules, gap list,
        |  Koi external API v2          report & deck structure)
        v
  https://api.prod.koi.security
        |
        v
  pov_report.json  (single source of truth for every number
                    that reaches a customer deliverable)
```

- The **MCP server** talks to the tenant: authentication, per-route rate
  limiting (30 req/min), pagination, backoff. It aggregates everything into
  one `pov_report.json`.
- The **skill** governs how deliverables are written from that JSON: never
  invent, evidence before assertion, a zero is not "not measured", gap list
  before writing.

## Requirements

- Python **3.10+** (`python3 --version` / `python --version`)
- `git`
- Claude Desktop (or Claude Code) with MCP support
- A Koi API key with read access to the tenant

## Quick install

The installers create an isolated venv in `~/.koi-pov-mcp`, install the
package, register the MCP server in your Claude Desktop config, and install
the companion skill into `~/.claude/skills/`.

**Windows (PowerShell):**

```powershell
git clone https://github.com/jbillochon/koi-pov-mcp.git
cd koi-pov-mcp
powershell -ExecutionPolicy Bypass -File install\install.ps1
```

**Linux / macOS:**

```bash
git clone https://github.com/jbillochon/koi-pov-mcp.git
cd koi-pov-mcp
bash install/install.sh
```

The script prompts for your **Koi API key** (input hidden, stored only in your
local Claude config). Press Enter to skip and add it later. Then **restart
Claude Desktop** completely (quit from the tray/menu bar, not just the window).

### Verify

In a new Claude conversation:

> Use the koi_ping tool

Expected: `OK: authenticated against the Koi API.`

| Result | Meaning | Fix |
|---|---|---|
| `NOT CONFIGURED` | `KOI_API_KEY` missing from the server env | Add it to the config (below), restart Claude |
| `AUTH FAILED (401)` | Key rejected | Regenerate the key in the Koi console |
| tool not found | Server not registered or Claude not restarted | Check config path and JSON syntax, restart |

## Manual install

```bash
python3 -m venv ~/.koi-pov-mcp/venv
~/.koi-pov-mcp/venv/bin/pip install git+https://github.com/jbillochon/koi-pov-mcp.git
```

Then add the server to your Claude Desktop config:

| OS | Config file |
|---|---|
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Linux | `~/.config/Claude/claude_desktop_config.json` |

```json
{
  "mcpServers": {
    "koi-pov": {
      "command": "/home/you/.koi-pov-mcp/venv/bin/koi-pov-mcp",
      "env": {
        "KOI_API_KEY": "<your key>"
      }
    }
  }
}
```

On Windows the command is
`C:\\Users\\you\\.koi-pov-mcp\\venv\\Scripts\\koi-pov-mcp.exe`
(double backslashes required in JSON).

Finally copy `skill/koi-pov-deliverables/` into `~/.claude/skills/`.

**Never paste the API key into a Claude conversation.** It belongs in the
config file (written by you or the installer) and nowhere else. The server
reads it from its environment; the model never sees it.

## Usage

A typical PoV wrap-up session:

1. `koi_ping` - confirm connectivity.
2. `set_pov_meta` - customer name, author, PoV window.
3. `koi_collect` - everything, or domain by domain:
   `devices`, `groups`, `inventory`, `inventory_views`, `policies`, `lists`,
   `remediations`, `approvals`, `alerts`, `agent_activity`.
4. `pov_status` - what was collected, what is missing, warnings. This feeds
   the mandatory gap review.
5. The skill takes over: gap list first, then report and deck drafted from
   `pov_report_json`, every figure traceable to the JSON or left as a visible
   `[[TO BE PROVIDED]]` placeholder.

Collection is synchronous and rate-limited by the API (30 req/min per route).
On a large tenant, prefer one or two domains per call, or lower `max_pages`
for a first pass. Failed domains do not stop the others; they land in
`warnings` and must appear in the gap list.

### State

Everything lives in one file, `pov_report.json`, under the OS user-data
directory (override with the `KOI_POV_WORKDIR` env var in the server config).
Domains merge incrementally, so you can collect across several sessions.
`pov_reset` archives it to `.bak` and starts fresh.

## Tool reference

| Tool | Purpose |
|---|---|
| `koi_ping` | Auth/connectivity probe. Run first. |
| `set_pov_meta` | Customer, author, PoV window, tenant label. |
| `koi_collect` | Collect one, several, or all domains into the report. |
| `pov_status` | Collected vs missing domains, warnings, key counts. |
| `pov_report_json` | Full aggregated report, the only source for deliverable figures. |
| `pov_reset` | Archive the report and start a new PoV (needs `confirm=true`). |

## Roadmap

- **v0.1** (current): Koi collection, incremental state, companion skill.
- **v0.2**: rendering tools (`render_deliverables`): PPTX and DOCX everywhere
  (`python-pptx`, `python-docx`, pure Python), PDF where WeasyPrint is
  available (needs GTK on Windows, hence optional: `pip install 'koi-pov-mcp[pdf]'`).
- **v0.3**: optional threat-intel enrichment and XSIAM cross-referencing,
  ported from povplatform's `intelligence/` and `connectors/xsiam/`.

Until v0.2 lands, deliverables are produced as Markdown by the skill, which
states explicitly which formats were not rendered.

## Troubleshooting

- **`koi_ping` says NOT CONFIGURED** - the `env` block is missing or the key
  is empty. Edit the config file, restart Claude Desktop fully.
- **Tools never appear** - JSON syntax error in the config (trailing comma is
  the usual suspect), or the `command` path is wrong. On Windows check the
  `.exe` suffix and double backslashes.
- **Collection is slow** - expected: the API allows 30 req/min per route and
  pages are 500 items. Use `domains=[...]` and `max_pages` to scope.
- **`agent_activity` window** - sessions cover up to 30 days, events are
  capped at 24h by the API. The collector already respects both.
- **Corporate proxy** - the server uses `requests`; standard `HTTPS_PROXY`
  env vars in the server `env` block work.

## License

MIT
