# koi-pov-mcp

MCP server + Claude skill to run a **Cortex AES (Koi) Proof of Value** end to end:
collect tenant evidence over the Koi API, review the gaps, and produce the
customer-facing report and restitution deck. **Multi-tenant**: an SE running
five or six PoVs in parallel keeps one isolated report per tenant.

Standalone and cross-platform: **Windows, Linux, macOS**. No Docker, no database,
no running service. One Python package, one skill folder.

> Deployment-independent rewrite of the collection layer of
> [povplatform](https://github.com/jbillochon/povplatform). The Koi client and
> collector are ported from it; nothing here imports or requires povplatform.

## How it works

```
Claude Desktop / Claude Code
        |
        |  MCP tools: koi_tenants, koi_ping, set_pov_meta,
        |             koi_collect, pov_status, pov_report_json, pov_reset
        v
  koi-pov-mcp (stdio, local)          skill: koi-pov-deliverables
        |                              (editorial rules, gap list,
        |  Koi external API v2          report & deck structure)
        v
  https://api.prod.koi.security
        |
        v
  <workdir>/<tenant>/pov_report.json   one per tenant, never mixed;
                                       the single source of truth for every
                                       number in that tenant's deliverables
```

- The **MCP server** talks to the tenants: authentication, per-route rate
  limiting (30 req/min), pagination, backoff. It aggregates each tenant into
  its own `pov_report.json`.
- The **skill** governs how deliverables are written from that JSON: never
  invent, evidence before assertion, a zero is not "not measured", gap list
  before writing, one tenant per deliverable.

## Requirements

- Python **3.10+** (`python3 --version` / `python --version`)
- `git`
- Claude Desktop (or Claude Code) with MCP support
- One Koi API key per tenant, with read access

## Quick install

The installers create an isolated venv in `~/.koi-pov-mcp`, install the
package, register the MCP server in your Claude Desktop config, and install
the companion skill into `~/.claude/skills/`.

**Windows (PowerShell 5.1+ or pwsh):**

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

The script prompts for a **Koi API key** (input hidden, stored only in your
local Claude config, registered as the `default` tenant). Press Enter to skip,
or to configure several tenants instead (below). Then **restart Claude Desktop
completely** (quit from the tray/menu bar, not just the window).

### Verify

In a new Claude conversation:

> Use the koi_ping tool

Expected: `OK: authenticated against the Koi API for tenant 'default'.`

| Result | Meaning | Fix |
|---|---|---|
| `NOT CONFIGURED` | No key found in the server env | Add it to the config (below), restart Claude |
| `AUTH FAILED (401)` | Key rejected | Regenerate the key in the Koi console |
| `Unknown tenant` | Alias typo, or key entry missing | Check `koi_tenants` and the env block |
| tool not found | Server not registered or Claude not restarted | Check config path and JSON syntax, restart |

## Multi-tenant configuration

One env entry per tenant, `KOI_API_KEY_<ALIAS>`. The alias (lowercased) is how
you refer to the tenant in every tool call. A plain `KOI_API_KEY` registers the
`default` tenant. `KOI_BASE_URL` (global) or `KOI_BASE_URL_<ALIAS>` (per
tenant) override the API endpoint if ever needed.

```json
{
  "mcpServers": {
    "koi-pov": {
      "command": "C:\\Users\\you\\.koi-pov-mcp\\venv\\Scripts\\koi-pov-mcp.exe",
      "env": {
        "KOI_API_KEY_ACME": "<key for the ACME PoV>",
        "KOI_API_KEY_GLOBEX": "<key for the Globex PoV>",
        "KOI_API_KEY_INITECH": "<key for the Initech PoV>"
      }
    }
  }
}
```

Each tenant gets its own `pov_report.json` under `<workdir>/<alias>/`. State is
never shared: collecting or resetting one tenant cannot touch another, and the
skill refuses to mix two tenants in one deliverable.

`koi_tenants` lists the configured aliases (never the keys) and which ones
already have a collected report.

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

Use the multi-tenant example above, or a single `KOI_API_KEY` for one tenant.
On Windows the command is
`C:\\Users\\you\\.koi-pov-mcp\\venv\\Scripts\\koi-pov-mcp.exe`
(double backslashes required in JSON).

Finally copy `skill/koi-pov-deliverables/` into `~/.claude/skills/`.

**Never paste an API key into a Claude conversation.** Keys belong in the
config file (written by you or the installer) and nowhere else. The server
reads them from its environment; the model never sees them, and `koi_tenants`
only ever returns aliases.

## Usage

A typical wrap-up session on one of several PoVs:

1. `koi_tenants` - see the configured aliases; pick one.
2. `koi_ping(tenant="acme")` - confirm connectivity for that tenant.
3. `set_pov_meta(tenant="acme", customer_name=..., ...)`.
4. `koi_collect(tenant="acme")` - everything, or domain by domain:
   `devices`, `groups`, `inventory`, `inventory_views`, `policies`, `lists`,
   `remediations`, `approvals`, `alerts`, `agent_activity`.
5. `pov_status(tenant="acme")` - collected vs missing, warnings. This feeds
   the mandatory gap review.
6. The skill takes over: gap list first, then report and deck drafted from
   `pov_report_json(tenant="acme")`, every figure traceable to the JSON or
   left as a visible `[[TO BE PROVIDED]]` placeholder.

Collection is synchronous and rate-limited by the API (30 req/min per route).
On a large tenant, prefer one or two domains per call, or lower `max_pages`
for a first pass. Failed domains do not stop the others; they land in
`warnings` and must appear in the gap list.

### State

Everything lives under the OS user-data directory (override with the
`KOI_POV_WORKDIR` env var in the server config), one subdirectory per tenant.
Domains merge incrementally, so you can collect across several sessions and
interleave tenants freely. `pov_reset(tenant=...)` archives that tenant's
report to `.bak` and starts fresh; a v0.1 single-tenant report is migrated to
the `default` tenant automatically.

## Tool reference

| Tool | Purpose |
|---|---|
| `koi_tenants` | List configured tenant aliases and which have reports. |
| `koi_ping` | Auth/connectivity probe for one tenant. Run first. |
| `set_pov_meta` | Customer, author, PoV window for one tenant. |
| `koi_collect` | Collect one, several, or all domains into a tenant's report. |
| `pov_status` | Collected vs missing domains, warnings, key counts. |
| `pov_report_json` | A tenant's full report, the only source for its deliverable figures. |
| `pov_reset` | Archive one tenant's report and start over (needs `confirm=true`). |

All tenant-scoped tools default to `tenant="default"`.

## Roadmap

- **v0.1**: Koi collection, incremental state, companion skill.
- **v0.2** (current): multi-tenant with isolated per-tenant state.
- **v0.3**: rendering tools (`render_deliverables`): PPTX and DOCX everywhere
  (`python-pptx`, `python-docx`, pure Python), PDF where WeasyPrint is
  available (needs GTK on Windows, hence optional: `pip install 'koi-pov-mcp[pdf]'`).
- **v0.4**: optional threat-intel enrichment and XSIAM cross-referencing,
  ported from povplatform's `intelligence/` and `connectors/xsiam/`.

Until v0.3 lands, deliverables are produced as Markdown by the skill, which
states explicitly which formats were not rendered.

## Updating

```bash
cd <your clone> && git pull
~/.koi-pov-mcp/venv/bin/pip install --upgrade .
```

(Windows: `%USERPROFILE%\.koi-pov-mcp\venv\Scripts\pip.exe install --upgrade .`)
Then restart Claude Desktop.

## Troubleshooting

- **`koi_ping` says NOT CONFIGURED** - no key entry in the `env` block, or the
  value is empty. Edit the config file, restart Claude Desktop fully.
- **`Unknown tenant`** - the alias does not match any `KOI_API_KEY_<ALIAS>`
  entry. `koi_tenants` shows what the server actually sees.
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
