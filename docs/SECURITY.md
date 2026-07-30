# Security model

## The one rule

**No credential ever transits through a Claude conversation.** Not the Koi
keys, not the XSIAM keys, not in either direction. Everything below serves
that rule.

## How credentials enter the system

| Path | Mechanism | Where the secret goes |
|---|---|---|
| Claude interface | `koi_tenant_add` / `xsiam_tenant_add` start a **local capture page** as a subprocess: an HTTP server bound to `127.0.0.1` on a random port, guarded by a one-time token, expiring after 5 minutes. The operator types or pastes the secret into that page. | OS credential store |
| Terminal | `koi-pov-mcp tenants add` / `xsiam add` prompt via `getpass` (hidden input, never argv, so never visible in the process list or shell history). | OS credential store |
| Env vars (legacy) | `KOI_API_KEY[_<ALIAS>]` in the MCP server env block. | Claude config file |

The capture subprocess writes to the store itself; the MCP tool only ever
sees "saved / cancelled / expired", never the value. Tool results,
`koi_tenants`, and the CLI `list` commands return aliases and metadata only.

A native Tk window remains available for operators who prefer it
(`python -m koi_pov_mcp.gui koi <alias> --tk`), but it is not the default:
when an MCP host spawns the server on Windows, a Tk window is created and
not reliably surfaced, so the operator sees nothing until the timeout.

### The capture log

The page writes its URL to `koi-pov-capture-<mode>-<alias>.log` in the temp
directory, and the tool reads it from there. What that file contains and does
not:

- it holds the **URL and its one-time token**, which grants access to the
  empty form, not to any secret
- it never holds the submitted value: the page writes that straight to the
  credential store
- the token is single-use and the page expires 5 minutes after it started,
  so a stale log is inert

On a shared machine, delete `koi-pov-capture-*.log` after adding a tenant
rather than leaving a live token readable for those five minutes.

## Where secrets live

- **Primary**: the OS credential store via `keyring`: Windows Credential
  Manager, macOS Keychain, Secret Service/KWallet on Linux. Service
  `koi-pov-mcp`, one entry per Koi alias, `xsiam:<alias>` for XSIAM keys.
- **Fallback** (no usable keyring backend, e.g. headless Linux): the key is
  stored in `tenants.json` with permissions restricted to the user (0600
  where the OS honours it), and the CLI says so explicitly.
- **Non-secrets** (aliases, base URLs, XSIAM key IDs, auth mode) live in
  `tenants.json` regardless.

Rotation = re-adding the alias (overwrites). Removal deletes both the store
entry and the index entry.

## What the model can and cannot do

Can: start the capture pages, test connectivity, use the credentials
*indirectly* (the server signs the API calls), see aliases and metadata.
Cannot: read, echo, or export any secret; no tool returns one.

If an operator pastes a credential into the chat anyway, the skill instructs
Claude to refuse to use it, advise rotating it in the console, and rerun the
capture page. A secret that has entered a conversation should be considered
exposed.

## Outbound connections

All read-only, all HTTPS, initiated only by explicit tool calls:

| Destination | Purpose |
|---|---|
| `api.prod.koi.security` (or per-tenant override) | Koi collection |
| XSIAM tenant FQDN `/public_api/v1` | endpoints + incidents (read-only) |
| `services.nvd.nist.gov` | CVE detail |
| `api.osv.dev` | package vulnerabilities |
| `www.cisa.gov` | KEV catalog |
| `api.first.org` | EPSS scores |

Standard `HTTPS_PROXY` env vars are honoured (requests).

## Data at rest

Collected tenant data (`pov_report.json`, snapshots, enrichment,
correlation, deliverables) contains **customer-confidential PoV material**:
customer names, hostnames, and a full software inventory. It is stored
unencrypted under the user's profile. Treat the workstation accordingly
(disk encryption, screen lock); on shared machines, point `KOI_POV_WORKDIR`
at an encrypted location. `pov_reset` archives rather than deletes: purge
`.bak` files and `history_archive/` yourself when a PoV must be fully
destroyed.

**Never commit any of it.** The work directory sits outside the repository by
design and the rendered deliverables are the most sensitive artefacts the
tool produces. This project's own repository is public and contains no
customer identifier of any kind; keep it that way.

Customer isolation is structural: one directory per tenant, every tool
scoped to one alias, and the skill refuses cross-customer comparisons.
