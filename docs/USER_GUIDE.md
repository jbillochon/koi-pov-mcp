# User guide

Everything here works conversationally in Claude Desktop or Claude Code, in
any language. The phrases below are examples, not fixed commands: the
companion skill maps your intent to the right tools.

## 1. Tenants

### Add a Koi tenant

> "Add a new tenant for the ACME PoV"

Claude asks for a short alias (e.g. `acme`) if you did not give one, then a
**credential page opens in your browser** (served locally on 127.0.0.1, with
a one-time token, expiring after 5 minutes). Paste the Koi API key there and
press Save. The key goes straight to your OS credential store (Windows
Credential Manager, macOS Keychain, Secret Service on Linux); Claude never
sees it. Connectivity is tested immediately and the tenant is usable at
once, no restart.

If no tab opens automatically, Claude gives you the URL: open it manually
and finish there. If Claude says the page is running but has not reported
its URL, **look in your browser first** - the tab is usually already open.
The address is also written to
`%TEMP%\koi-pov-capture-koi-<alias>.log` (`$TMPDIR` elsewhere).

The tenant gets a dedicated environment: its own data file, snapshot
history, and deliverables directory. Nothing is ever shared between tenants.

### List, check, remove

> "What tenants do I have?" / "Ping tenant acme"

Re-adding a tenant with the same alias overwrites its key: that is how you
rotate one. Removal is available from the CLI
(`koi-pov-mcp tenants remove acme`).

### Link an XSIAM tenant (optional)

> "Link an XSIAM tenant to acme"

Same browser page, with three fields: **API URL** (the tenant's
`https://api-...` FQDN), **API Key ID**, and the **API key** (masked), plus
an **Advanced API key** checkbox (hashed authentication). Same rules: stored
locally, tested immediately, never through the chat.

### Terminal alternative

Every credential operation also exists as a CLI, useful on systems without a
browser or graphical session, and as a fallback:

```bash
koi-pov-mcp tenants add acme --test
koi-pov-mcp tenants list
koi-pov-mcp xsiam add acme --advanced --test
```

On Windows use the full path:
`%USERPROFILE%\.koi-pov-mcp\venv\Scripts\koi-pov-mcp.exe`.

## 2. Syncing data

> "Sync tenant acme" / "Synchronise les donnees du tenant acme"

Collects up to ten domains from the Koi API: devices, groups, inventory,
inventory views, policies, allow/blocklists, remediations, approvals, alerts,
agent activity. Each sync merges into the tenant's `pov_report.json` and
takes a timestamped snapshot for later diffs.

The Koi API allows 30 requests/minute per route with 500-item pages, so a
full sync of a large tenant takes minutes. Two ways to go faster:

- scope the domains: *"sync only the inventory and policies of acme"*
- lower the page cap for a first pass: Claude can pass `max_pages`

> "Sync all my Koi tenants"

Sequential loop over every tenant; a failure on one never stops the others.
Claude warns you about the expected duration first.

A domain that fails to collect lands in `warnings` and is treated as **not
measured**, never as zero.

## 3. State of play

> "Give me a state of play of tenant acme" / "Etat des lieux de acme"

Claude narrates from the collected data: lifecycle stage (`discovery` =
visibility story, `governed` = outcomes story), coverage, risk distribution,
governance, remediation, agentic runtime, plus what is missing (uncollected
domains, warnings) as an explicit gap list.

## 4. Follow-up meetings: what's new

> "What's new on acme since my last sync?" /
> "Prepare my next PoV follow-up for acme" /
> "What changed since July 10?"

Compares the latest snapshot against a baseline (the previous sync, or the
last snapshot at/before the date you name) and returns **changes only**:
newly appeared critical items, items remediated since, new policies, agent
blocks, coverage evolution. Unchanged figures are omitted by design so they
cannot be presented as news. On a first sync there is no baseline and Claude
says so instead of inventing a comparison.

Tip: sync right before asking, so the diff covers the full period since your
last customer meeting.

## 5. Threat intel enrichment

> "Enrich acme with threat intel"

Deterministic sources only, no model-generated intel:

- **MITRE ATT&CK**: a human-curated mapping from Koi finding identifiers;
  findings with no mapping are listed as unmapped, never guessed.
- **OSV.dev**: package vulnerabilities for high-risk npm/PyPI items, exact
  name@version match, batch query.
- **CISA KEV**: is the CVE known-exploited, and since when.
- **FIRST EPSS**: exploitation probability for every CVE in scope.
- **NVD**: CVSS score/severity, CWE, description for the top CVEs (KEV
  members first, then highest EPSS).

The result is dated; deliverables always carry "threat intel as of
&lt;date&gt;". NVD is the slow source (~6.5s per CVE without a key); an
optional `NVD_API_KEY` in the server environment makes it ~5x faster.

In documents, the reading order is **KEV &gt; EPSS &gt; CVSS**: exploitation
fact first, probability second, severity last.

## 6. XSIAM cross-referencing

> "Cross-reference acme with XSIAM"

Requires a linked XSIAM tenant (Claude offers the page if there is none).
Returns two fact sets:

- **Coverage overlap**: hosts managed by Koi, by XSIAM, by both, by only one
  (deployment observations for you, not customer blame).
- **Incidents**: XSIAM incidents from the last N days (default 30) landing
  on hosts that Koi knows, by severity, with the most affected hosts.

Current granularity is host-level co-presence: a risky Koi item and XSIAM
incidents on the same host is a correlation lead, not a causal claim, and
Claude will not present it as one.

## 7. Deliverables

> "Generate the report and deck for acme" / "Generate a Word and PDF for acme"

The workflow always runs in this order:

1. **Gap list first**: success criteria without evidence, uncollected
   domains, improvements without baselines. Shown to you before anything is
   written; generation proceeds with placeholders, and the list is repeated
   at the end so you decide what to chase.
2. Optional enrichment questions (TI, then XSIAM) if not already done.
3. Narrative written from the collected JSON only (executive summary written
   last, success-criteria verdicts each tied to evidence).
4. Rendering into the tenant's `deliverables/` directory: `report.docx`,
   `report.pdf` and `deck.pptx`, all pure Python with no system dependency.

### What is in them

Each document has a data half and an analysis half.

The **data sections** are computed from your tenant with no input at all:
discovery by category and marketplace, the software supply chain (which
marketplaces the software arrives through and their share, how concentrated
the publisher base is, and Koi's findings grouped into four questions -
provenance, maintenance, known vulnerabilities, active compromise), the risk
inventory, governance, remediation, agentic activity and the threat-intel
tables.

The **analysis sections** are written for this tenant: a one-line headline,
the executive summary, findings with a severity and a stated confidence,
attack scenarios with their chain and the control that breaks it,
recommended actions ranked by risk reduced, threat context under an explicit
"not verified against your tenant" banner, and the data gaps.

### How you know it is trustworthy

Every claim in the analysis sections cites the items, findings, policies,
agents or CVEs it rests on, and those citations are checked against your
collected data before the documents are written. Anything that cannot be
traced is removed rather than shipped with a caveat, and narrative prose is
scanned for hand-written figures, because every number you show a customer
must come from their tenant.

Claude reports exactly which formats were produced, which were skipped and
why, and the verification result: how many citations were checked and
verified, and what was dropped. **Ask for that block if it is not shown.** A
claim that did not survive verification is absent from the document, and you
want to know which one and why.

Any narrative section not validated appears as a visible
`[[TO BE PROVIDED: ...]]`: a placeholder is an action item, an invented
number reaching a customer is a lost account.

Deliverables are in **English** (customer-facing); the conversation with you
stays in your language.

### Getting the most out of them

Two things materially change the quality of what comes out:

- **Give the PoV window and the customer name** up front
  (*"set the PoV metadata for acme: customer ACME Corp, 1 to 31 July"*),
  otherwise the documents carry a collection date instead of a bounded
  assessment period.
- **State the success criteria agreed at kickoff.** That section is the
  first thing a customer reads, and it is the only one Claude cannot derive
  from the data.

## 8. Starting a new PoV on a tenant

> "Start over on acme"

Claude asks for explicit confirmation, then archives the report, snapshot
history, enrichment and XSIAM correlation (everything kept as `.bak` /
`history_archive/`). Deliverable files and other tenants are untouched.
