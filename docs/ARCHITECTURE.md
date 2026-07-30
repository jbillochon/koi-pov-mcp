# Architecture

## Components

```
Claude Desktop / Claude Code (the LLM + the operator)
        |
        |  14 MCP tools (stdio)
        v
+--------------------------- koi-pov-mcp -----------------------------+
|  server.py        tool surface, tenant resolution, state layout     |
|  cli.py           `koi-pov-mcp` entry point: serve + credential CLI |
|  dialog.py        launches the credential page, collects its URL    |
|  gui.py           the credential page itself (local HTTP, one-time  |
|                   token); Tk remains available behind --tk          |
|  secrets.py       tenant registry: OS keyring / restricted file /   |
|                   env vars                                          |
|  client.py        Koi API v2 client (rate limit, paging, backoff)   |
|  collector.py     Koi -> PoVReport aggregation model                |
|  diffing.py       snapshot-to-snapshot what's-new computation       |
|  enrichment.py    NVD CVE fetch + curated MITRE mapping             |
|  ti_sources.py    OSV.dev, CISA KEV, FIRST EPSS                     |
|  ti_tool.py       koi_enrich orchestration                          |
|  xsiam.py         XSIAM client (standard/advanced auth) + correlate |
|  xsiam_tool.py    xsiam_tenant_add / xsiam_correlate                |
|  render_tool.py   render_deliverables                               |
|  rendering/       see below                                         |
+---------------------------------------------------------------------+
        |                    |                     |
        v                    v                     v
  Koi API v2          TI sources             XSIAM public API
  api.prod.koi.       NVD, OSV.dev,          {tenant FQDN}/public_api/v1
  security            CISA KEV, FIRST EPSS
```

### The rendering package

```
rendering/
  __init__.py        render(): normalise, derive, dispatch to the builders
  narrative.py       the structured narrative contract and its verification
  supply_chain.py    entry channels, publisher concentration, trust signals
  common.py          Data accessor, null-awareness ("not measured" != 0)
  docx_report.py     Word document, palette and formatting helpers
  docx_sections.py     its analytical sections
  pdf_report.py      PDF (reportlab), palette and formatting helpers
  pdf_sections.py      its analytical sections
  deck.py            PPTX, palette and drawing primitives
  deck_sections.py     its analytical slides
```

The split is deliberate: each `*_report.py` or `deck.py` owns its document,
its palette and its primitives, and hands them to its `*_sections.py`
through a small kit. The analytical sections can then grow without turning
any builder into one long function, and the three documents cannot drift
apart on styling.

`supply_chain.py` is a straight port from
[povplatform](https://github.com/jbillochon/povplatform) and is kept
identical to it, so both projects group and label Koi findings the same way.
A fix in one belongs in the other.

The **skill** (`skill/koi-pov-deliverables/SKILL.md`) is the behavioural
layer: natural-language command mapping, the editorial rules (never invent,
never write a figure into prose, evidence before assertion, zero vs
not-measured, one tenant per deliverable), the TI language hierarchy, and
the deliverable workflow. The server supplies facts and files; the skill
governs how Claude turns them into customer documents.

## Division of labour: why no LLM inside the server

povplatform embedded LLM providers because it was a headless pipeline. Here
the LLM is Claude itself, already in the loop and already governed by the
skill. The server therefore only produces **deterministic, traceable
artifacts**: API aggregates, snapshot diffs, TI facts with a fetch date,
rendered files. Narrative enters the system exclusively through
`render_deliverables` arguments, written by Claude under the skill's rules,
and missing narrative renders as a visible placeholder.

## What is written, and what is computed

The line matters, because it is what keeps figures out of the model's hands.

**Computed, no input at all**: discovery tables, the supply-chain view
(entry channels with their shares, publisher concentration, the four trust
dimensions), the risk inventory, governance, remediation, agentic activity,
the threat-intelligence tables, and the collection notes.

**Written by Claude**: the headline, the executive summary, findings, attack
scenarios, recommended actions, threat context and data gaps - the parts
where judgement has value.

Moving the supply-chain analysis into `supply_chain.py` was a deliberate
transfer across that line. It reads as analysis, but it is arithmetic over
the finding taxonomy, so it belongs on the deterministic side where it
cannot be invented.

## Verification of the narrative

`narrative.py` sits between the arguments and the builders. Before anything
is written:

- an index is built from the snapshot: item names and ids, finding labels,
  policy names, agents and hosts, and the CVEs collected during enrichment
- every evidence entry names a `kind` and a `reference` that must be found in
  the matching pool; `contextual` is exempt by design, since it carries
  public knowledge and renders under a visible caveat
- evidence that cannot be traced is stripped, and a finding or scenario left
  with none is dropped entirely rather than shipped with a caveat
- MITRE identifiers are format-checked, CVEs are checked for form and for
  membership in the collected set
- narrative prose is scanned for hand-written figures, ignoring years and
  small ordinals

The result is a `validation` report returned to the operator: citations
checked and verified, the resulting rate, what was dropped and why. A silent
drop is exactly the failure this guards against, so the skill requires the
block to be reported after every render.

The vocabulary is identical to povplatform's `intelligence/schema.py`, so a
section written for one project moves to the other without translation.

## Per-tenant environment

```
<workdir>/                       KOI_POV_WORKDIR or the OS user-data dir
  tenants.json                   alias index + non-secret metadata (0600)
  <alias>/
    pov_report.json              current aggregated state (source of truth)
    history/<UTCts>.json         one snapshot per sync (what's-new baselines)
    history_archive/             snapshots moved here on pov_reset
    enrichment.json              dated TI facts (koi_enrich)
    xsiam_correlation.json       dated correlation facts (xsiam_correlate)
    deliverables/                report.docx, deck.pptx, report.pdf
    *.json.bak                   pre-reset archives
```

Isolation properties: every tool call is scoped by alias; no tool reads two
tenants; `pov_reset` and `koi_collect` cannot touch a sibling directory. The
v0.1 single-tenant layout is migrated to `default/` on first access.

Nothing under `<workdir>` is ever versioned: it holds customer names,
hostnames and software inventories.

## Data flow of a full PoV cycle

1. `koi_tenant_add` -> `dialog.launch` starts the capture page as a
   subprocess -> the page writes its URL to a temp log and serves the form
   -> the operator submits -> key in the OS store -> `koi_ping` confirms
2. `koi_collect` -> client paginates the Koi API under the per-route rate
   limit (28/min, 500/page, capped by `max_pages`) -> collector aggregates
   into `PoVReport` -> saved + snapshotted
3. `koi_enrich` -> MITRE mapping (static) -> OSV batch (npm/PyPI
   name@version) -> KEV (one fetch) -> EPSS (batched 100) -> NVD detail for
   the top CVEs -> `enrichment.json` with `fetched_at`
4. `xsiam_correlate` (optional) -> Koi hostnames + XSIAM endpoints +
   incidents -> coverage overlap + incidents on Koi-known hosts ->
   `xsiam_correlation.json`
5. `koi_whats_new` -> latest snapshot vs baseline -> deltas + new items only
6. `render_deliverables` -> `pov_report_json` (report + derived + enrichment
   + xsiam) + Claude-written narrative -> verification -> DOCX/PDF/PPTX in
   `deliverables/`, plus the `validation` report

## Koi API specifics encoded in the client

- 30 requests/minute **per route** (client stays at 28, sliding window)
- `page_size` capped at 500; pagination keys vary per endpoint (`devices`,
  `items`, `policies`, `alerts`, `data`, ...)
- agent-activity windows: sessions <= 30 days, events <= 24 hours
- 429 honoured via Retry-After, exponential backoff capped at 60s, 5 retries
- 401 raises a dedicated auth error surfaced as "re-add the key"

## Collector fields the renderers depend on

Worth knowing before writing a section against them:

- `item_id` is present on `action_candidates` only. Items from
  `top_risk_items`, `malicious_items` and `remediated_items` are cited by
  name, and the verification index accepts both forms.
- `finding_frequency` is capped by the collector, so a dimension whose
  findings fall outside the cut totals zero while named items still carry
  them. `supply_chain.py` raises `understated` for exactly that case and the
  renderers print "this snapshot did not record an estate-wide count"
  instead of a zero.
- `items_by_marketplace` does not always cover every item, so channel shares
  are computed against the channel total, never against `items_total`, and
  the exclusion is stated under the table.

## XSIAM authentication

Standard keys: `Authorization: <key>` + `x-xdr-auth-id: <id>`.
Advanced keys: `Authorization: sha256(key + nonce + timestamp)` with
`x-xdr-nonce` (64 hex chars) and `x-xdr-timestamp` (ms) headers. The mode is
chosen at link time (dialog checkbox / `--advanced`). Endpoints used are
read-only: `endpoints/get_endpoint/`, `incidents/get_incidents/`.

## Design decisions

- **Store read at call time**, not at server start: tenants added
  mid-conversation work immediately; Desktop and Claude Code share the same
  store.
- **The capture page reports its URL through a file, not a pipe.** An
  anonymous pipe is dependable from a terminal and is not from inside an MCP
  host on an EDR-managed workstation, where the URL never arrived and the
  tool declared failure while the page waited in the operator's browser.
- **The interpreter is resolved, not assumed.** `sys.executable` is the
  console-script wrapper when a host starts the server through
  `koi-pov-mcp.exe`, so the venv's python is found next to it instead.
- **Synchronous, domain-scoped collection** instead of a job queue: simpler,
  and the skill steers large tenants toward per-domain calls. A job model
  can be added later without breaking the tool surface.
- **Snapshots are cheap and kept**: they are the follow-up story, and disk
  cost is negligible next to their meeting value.
- **Renderer cannot invent**: numbers come from the JSON, narrative from
  arguments, untraceable claims are dropped, absences become placeholders.
  This is the mechanical enforcement of the skill's first two rules.
- **PDF drawn with reportlab, not WeasyPrint**: povplatform renders its PDF
  from HTML through WeasyPrint, which needs system GTK and therefore fails
  on a plain Windows workstation. The same document is drawn with reportlab
  against the same print palette.
- **Curated MITRE mapping**: every technique in a customer document traces
  to a rule a human wrote; `unmapped_findings` feeds the curation loop.
- **Host-level XSIAM correlation first**: item-to-alert joins need
  per-device inventory sweeps (expensive under the rate limit) and are a
  later iteration; until then co-presence is presented as co-presence.
