# Changelog

All notable changes to koi-pov-mcp.

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
- **XSIAM**: optional per-tenant link via `xsiam_tenant_add` (native 3-field
  dialog: API URL, Key ID, key, advanced checkbox; standard and advanced
  auth). `xsiam_correlate` computes agent coverage overlap and incidents on
  Koi-known hosts. CLI: `koi-pov-mcp xsiam add|list|test|remove`.
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

- `koi_tenant_add`: add a tenant from the Claude interface via a native
  masked-input dialog; key goes straight to the OS credential store.

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
