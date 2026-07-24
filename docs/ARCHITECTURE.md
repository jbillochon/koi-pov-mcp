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
|  gui.py           native credential dialogs (subprocess, tkinter)   |
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
|  rendering.py     DOCX / PPTX / optional PDF renderers              |
|  render_tool.py   render_deliverables                               |
+---------------------------------------------------------------------+
        |                    |                     |
        v                    v                     v
  Koi API v2          TI sources             XSIAM public API
  api.prod.koi.       NVD, OSV.dev,          {tenant FQDN}/public_api/v1
  security            CISA KEV, FIRST EPSS
```

The **skill** (`skill/koi-pov-deliverables/SKILL.md`) is the behavioural
layer: natural-language command mapping, the editorial rules (never invent,
evidence before assertion, zero vs not-measured, one tenant per deliverable),
the TI language hierarchy, and the deliverable workflow. The server supplies
facts and files; the skill governs how Claude turns them into customer
documents.

## Division of labour: why no LLM inside the server

povplatform embedded LLM providers because it was a headless pipeline. Here
the LLM is Claude itself, already in the loop and already governed by the
skill. The server therefore only produces **deterministic, traceable
artifacts**: API aggregates, snapshot diffs, TI facts with a fetch date,
rendered files. Narrative enters the system exclusively through
`render_deliverables` arguments, written by Claude under the skill's rules,
and missing narrative renders as a visible placeholder.

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

## Data flow of a full PoV cycle

1. `koi_tenant_add` -> dialog subprocess -> key in OS store -> auto ping
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
   + xsiam) + Claude-written narrative -> DOCX/PPTX/PDF in `deliverables/`

## Koi API specifics encoded in the client

- 30 requests/minute **per route** (client stays at 28, sliding window)
- `page_size` capped at 500; pagination keys vary per endpoint (`devices`,
  `items`, `policies`, `alerts`, `data`, ...)
- agent-activity windows: sessions <= 30 days, events <= 24 hours
- 429 honoured via Retry-After, exponential backoff capped at 60s, 5 retries
- 401 raises a dedicated auth error surfaced as "re-add the key"

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
- **Synchronous, domain-scoped collection** instead of a job queue: simpler,
  and the skill steers large tenants toward per-domain calls. A job model
  can be added later without breaking the tool surface.
- **Snapshots are cheap and kept**: they are the follow-up story, and disk
  cost is negligible next to their meeting value.
- **Renderer cannot invent**: numbers come from the JSON, narrative from
  arguments, absences become placeholders. This is the mechanical
  enforcement of the skill's rule 1.
- **Curated MITRE mapping**: every technique in a customer document traces
  to a rule a human wrote; `unmapped_findings` feeds the curation loop.
- **Host-level XSIAM correlation first**: item-to-alert joins need
  per-device inventory sweeps (expensive under the rate limit) and are a
  later iteration; until then co-presence is presented as co-presence.
