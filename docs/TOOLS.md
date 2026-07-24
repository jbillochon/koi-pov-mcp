# Tool and CLI reference

All tenant-scoped tools take `tenant` (alias, default `"default"`). Aliases:
lowercase letters, digits, `-`, `_`, max 40 chars, start alphanumeric.

## Tenant management

### koi_tenant_add(alias, base_url="")
Opens a native masked-input dialog on the operator's machine; the Koi key
goes straight to the OS credential store. Creates the tenant environment,
auto-pings. Returns a status string. Dialog auto-cancels after 3 minutes;
exit paths: saved / cancelled / no-tkinter (CLI fallback suggested).

### koi_tenants()
Lists aliases with: `source` (store|env), `has_report`, `snapshots` count,
`xsiam_linked`, `customer` (from meta when a report exists). Never returns
keys.

### koi_ping(tenant)
Auth/connectivity probe (1-item devices call). Distinguishes NOT CONFIGURED,
unknown alias, AUTH FAILED (401), API ERROR, OK.

### xsiam_tenant_add(tenant)
Native 3-field dialog (API URL prefilled `https://api-`, Key ID, masked key,
Advanced checkbox); stores locally, auto-pings XSIAM. One XSIAM link per Koi
alias; re-adding overwrites.

## Collection and state

### set_pov_meta(customer_name, tenant, prepared_by, pov_start, pov_end, tenant_label)
Merges PoV metadata into the tenant report without touching collected data.

### koi_collect(tenant, domains=None, max_pages=40, activity_days=30)
Syncs one tenant and snapshots the result. `domains` subset of:
`devices, groups, inventory, inventory_views, policies, lists, remediations,
approvals, alerts, agent_activity` (omit = all). Returns collected domains,
`new_warnings`, snapshot id, summary. Synchronous; per-route rate limit
makes full syncs of large tenants take minutes.

### koi_sync_all(domains=None, max_pages=40, activity_days=30)
Sequential sync of every configured tenant; per-tenant failure isolation.
Returns `synced`, `failed` (alias -> error), `results`.

### pov_status(tenant)
Collected vs missing domains, warnings, last snapshots, enrichment/XSIAM
presence and paths, deliverables path, key counts. Feeds the gap list.

### pov_report_json(tenant)
The full aggregated report + `derived` (stage, high_and_critical,
pending_analysis) + `enrichment` + `xsiam` when present. The single source
of truth for deliverable figures.

### koi_whats_new(tenant, since="")
Diff of the latest snapshot vs the previous one, or vs the last snapshot
at/before `since` (ISO or YYYYMMDD). Returns changes only (coverage,
discovery, exposure, governance, remediation, runtime deltas + new items +
new warnings). `baseline: null` on first sync.

### pov_reset(tenant, confirm=False)
Archives report, enrichment, XSIAM correlation (`.json.bak`) and snapshots
(`history_archive/`). Refuses without `confirm=true`; the operator must be
asked first.

## Enrichment and correlation

### koi_enrich(tenant, fetch_cves=True, max_cves=15, osv=True)
Deterministic TI: curated MITRE mapping (+ `unmapped_findings`), OSV batch
for npm/PyPI action candidates (exact name@version), CISA KEV membership,
EPSS for every CVE in scope, NVD detail for the top CVEs (KEV first, then
EPSS desc). Writes dated `enrichment.json`. NVD pace: ~6.5s/CVE without
`NVD_API_KEY` in the server env, ~1.2s with.

### xsiam_correlate(tenant, days=30)
Coverage overlap (koi_devices, xsiam_endpoints, on_both, *_only counts and
samples) and XSIAM incidents in the window: total, by_severity, hosts known
to Koi with incidents, top hosts. Writes dated `xsiam_correlation.json`.
Host-level co-presence only; no causal claims.

## Rendering

### render_deliverables(tenant, formats=None, executive_summary="", recommendations="", success_criteria=None)
Renders into `<tenant>/deliverables/`: `report.docx`, `deck.pptx` (14
slides), `report.pdf` (WeasyPrint required). `success_criteria` is a list of
`{criterion, verdict, evidence}`. Empty narrative renders as visible
`[[TO BE PROVIDED]]`. Returns `produced` (format -> path) and `skipped`
(format -> reason); skipped formats must be announced to the operator.

## CLI

```
koi-pov-mcp                      run the MCP server (stdio); same as `serve`
koi-pov-mcp tenants add <alias> [--base-url URL] [--test]
koi-pov-mcp tenants list         aliases, source, XSIAM link, base URL
koi-pov-mcp tenants test <alias>
koi-pov-mcp tenants remove <alias>          also removes the XSIAM link
koi-pov-mcp xsiam add <alias> [--advanced] [--test]
koi-pov-mcp xsiam list|test|remove <alias>
```

Keys are prompted with hidden input, never taken from argv.

## Environment variables (server env block)

| Variable | Effect |
|---|---|
| `KOI_API_KEY` | Koi key for the `default` tenant (overrides the store) |
| `KOI_API_KEY_<ALIAS>` | Koi key for `<alias>` (overrides the store) |
| `KOI_BASE_URL[_<ALIAS>]` | Koi API base URL override |
| `KOI_POV_WORKDIR` | State directory (default: OS user-data dir) |
| `NVD_API_KEY` | Faster NVD lookups during koi_enrich |
