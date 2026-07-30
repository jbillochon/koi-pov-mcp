# Tool and CLI reference

All tenant-scoped tools take `tenant` (alias, default `"default"`). Aliases:
lowercase letters, digits, `-`, `_`, max 40 chars, start alphanumeric.

## Tenant management

### koi_tenant_add(alias, base_url="")
Starts a local credential page and returns its URL for the operator to open;
the Koi key goes from that page straight to the OS credential store and never
transits the conversation. The call returns as soon as the page reports its
URL, it does not wait for the form to be filled. The page expires after 5
minutes and nothing is saved until it is submitted, so the tenant is only
usable once `koi_ping` confirms it.

The page writes its URL to a log file in the temp directory
(`koi-pov-capture-koi-<alias>.log`) and the tool polls that file. If the URL
does not arrive within 30 seconds the tool says so and gives the log path
rather than reporting failure: a browser tab has usually already opened.

### koi_tenants()
Lists aliases with: `source` (store|env), `has_report`, `snapshots` count,
`xsiam_linked`, `customer` (from meta when a report exists). Never returns
keys.

### koi_ping(tenant)
Auth/connectivity probe (1-item devices call). Distinguishes NOT CONFIGURED,
unknown alias, AUTH FAILED (401), API ERROR, OK.

### xsiam_tenant_add(tenant)
Same credential-page flow for the XSIAM API URL, key ID and key; stores
locally and auto-pings XSIAM. One XSIAM link per Koi alias; re-adding
overwrites.

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

### render_deliverables(tenant, formats=None, headline="", executive_summary="", recommendations="", success_criteria=None, key_findings=None, attack_scenarios=None, recommended_actions=None, threat_context=None, data_gaps=None)

Renders into `<tenant>/deliverables/`: `report.docx`, `report.pdf`
(reportlab, no system dependency) and `deck.pptx`. Slide and page counts vary
with the narrative supplied.

Data sections (discovery, supply chain, risk inventory, governance,
remediation, agentic activity, threat intelligence) are rendered from the
collected data with no input at all. The arguments below carry only what
requires judgement.

| Argument | Shape |
|---|---|
| `headline` | One sentence naming the central problem. No figures. |
| `executive_summary`, `recommendations` | Plain text. `recommendations` is the legacy free-text fallback used only when `recommended_actions` is empty. |
| `success_criteria` | `[{criterion, verdict, evidence}]` |
| `key_findings` | `[{title, severity, confidence, narrative, evidence[], mitre_techniques[], affected_scope}]`; severity `critical\|high\|medium\|low\|info`, confidence `confirmed\|likely\|possible` |
| `attack_scenarios` | `[{title, steps[], impact, likelihood, enabling_evidence[], mitre_techniques[], breaks_at}]`; at least two steps |
| `recommended_actions` | `[{title, rationale, priority, effort, platform_capability, expected_outcome, addresses_findings[]}]`; effort `low\|medium\|high`, priority 1 = most urgent |
| `threat_context` | `[{campaign_or_pattern, relevance, tenant_link[]}]`; rendered under an explicit "NOT verified against your tenant" banner |
| `data_gaps` | Short strings naming what the report could not establish |

**Evidence** is `{kind, reference, note}` where `kind` is `inventory_item`,
`koi_finding`, `governance`, `agent_activity`, `cve` or `contextual`, and
`reference` names something present in `pov_report_json`. Cite items **by
name**: `item_id` is only present on `action_candidates`. The `note` carries
the specificity and is rendered, so it is worth writing.

Citations are checked against an index built from the snapshot before
anything is written. Unverifiable evidence is stripped, and a finding or
scenario left with none is dropped entirely. `contextual` is exempt by
design.

Empty narrative renders as a visible `[[TO BE PROVIDED]]` placeholder rather
than being invented.

**Returns** `produced` (format -> path), `skipped` (format -> reason) and
`validation`:

```
{checked_citations, verified_citations, verification_rate, dropped[], issues[]}
```

`issues[].kind` is `unknown_item`, `unknown_cve`, `bad_mitre`,
`empty_evidence` or `prose_number`. The last one flags a figure written into
narrative prose, which is a violation: every number shown to a customer must
come from the snapshot. Skipped formats and a non-empty `dropped` or
`issues` must be announced to the operator, never glossed over.

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
