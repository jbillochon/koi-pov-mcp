# Changelog

All notable changes to koi-pov-mcp.

## 0.7.2 - 2026-07-24

- **Credential capture is non-blocking.** `koi_tenant_add` and
  `xsiam_tenant_add` now start the local page and return its URL at once,
  instead of waiting for the form to be submitted. Reason: MCP hosts abandon
  a tool call after a few minutes, so a blocking capture could never
  complete, and it froze the conversation while the operator typed.
- The flow is now: tool returns the link -> the operator fills the page in
  their own time (5-minute expiry) -> `koi_ping` (or `koi_tenants`) confirms.
  Tool descriptions state explicitly that nothing is saved on return.

## 0.7.1 - 2026-07-24

- **Fixed credential capture**: a form served on `127.0.0.1` (random port,
  one-time token) opened in the operator's browser, instead of a native Tk
  window. Reason: when Claude Desktop spawns the MCP server on Windows, a Tk
  window is created but not reliably surfaced to the desktop, so the operator
  saw nothing until the timeout.
- The capture URL is relayed in the tool result, so a browser that fails to
  open is no longer a dead end.
- Tk remains available: `python -m koi_pov_mcp.gui koi <alias> --tk`.

## 0.7.0 - 2026-07-24

- **TI v2**: `koi_enrich` now queries OSV.dev (batch, exact name@version for
  npm/PyPI items), the CISA KEV catalog, and FIRST EPSS for every CVE in
  scope; NVD detail is fetched for the top CVEs (KEV members first, then
  highest EPSS). Payload is dated (`fetched_at`) and lists
  `unmapped_findings` to feed the curated MITRE mapping.
- **Rendering**: `render_deliverables` produces report.docx and deck.pptx
  (pure Python, core dependencies) and report.pdf when WeasyPrint is
  installed. Narrative sections are caller-provided; empty ones render as
  visible `[[TO BE PROVIDED]]` placeholders.
- **XSIAM**: optional per-tenant link via `xsiam_tenant_add` (API URL, Key
  ID, key, advanced checkbox; standard and advanced auth). `xsiam_correlate`
  computes agent coverage overlap and incidents on Koi-known hosts. CLI:
  `koi-pov-mcp xsiam add|list|test|remove`.
- Skill 2.6.0: TI language hierarchy (KEV > EPSS > CVSS), dated intel,
  XSIAM co-presence rules, render workflow.

## 0.4.0 - 2026-07-24

- Per-tenant environments: `history/` snapshots on every sync,
  `deliverables/` directory.
- `koi_sync_all`: sequential sync of every tenant, failure-isolated.
- `koi_whats_new`: follow-up diffs against the previous snapshot or a
  `since` date; changes only, first-sync guard.
- Skill 2.4.0: natural-language command mapping.

## 0.3.1 - 2026-07-24

- `koi_tenant_add`: add a tenant from the Claude interface without the key
  transiting through the conversation.

## 0.3.0 - 2026-07-24

- Tenant CLI (`koi-pov-mcp tenants add|list|test|remove`), keys in the OS
  credential store (keyring; restricted-file fallback), hot reload without
  restart. Env vars remain supported and take precedence.
- Installers register the server without writing keys into Claude configs.

## 0.2.0 - 2026-07-24

- Multi-tenant: per-alias keys (`KOI_API_KEY_<ALIAS>`), isolated per-tenant
  state, `koi_tenants` tool, automatic migration of the v0.1 layout.

## 0.1.x - 2026-07-24

- Initial release: Koi API client (rate limiting, pagination, backoff),
  PoV collector, MCP server (ping/collect/status/report/reset), companion
  skill, Windows/Linux/macOS installers. 0.1.1 fixed PowerShell 5.1
  compatibility in the installer.
