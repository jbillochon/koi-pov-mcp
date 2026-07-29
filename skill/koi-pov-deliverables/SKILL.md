---
name: koi-pov-deliverables
description: This skill should be used for anything related to running a Koi (Cortex AES) Proof of Value: adding a tenant, linking an XSIAM tenant, syncing tenant data, giving a state of play, preparing a follow-up meeting (what's new), TI enrichment, and producing the customer-facing wrap-up (Word report, PDF, slide deck). Triggers include "add a tenant", "link XSIAM", "sync tenant X", "sync all my Koi tenants", "status of tenant X", "what's new on tenant X", "prepare my PoV follow-up", "generate the report / deck / word / pdf for tenant X", "restitution de PoV", in any language.
version: 3.0.0
---

# Koi PoV operations and deliverables (MCP-backed, multi-tenant)

Run Koi Proofs of Value through the **koi-pov MCP server**: dedicated
environment per tenant, data sync, TI enrichment, optional XSIAM
cross-referencing, follow-up preparation, and rendered deliverables
(report.docx, deck.pptx, report.pdf), all in English, structured around the
success criteria agreed at kickoff.

The deliverable answers one question for the decision-maker:

> **Did Koi meet the success criteria we set, and what is that worth to us?**

## Natural-language command mapping

| Operator says (any phrasing/language) | Do |
|---|---|
| "Add a (new) tenant" | Ask for a short alias if not given. `koi_tenant_add(alias)`: opens a local credential page. Relay the URL verbatim, say it expires in 5 minutes, stop. Confirm with `koi_ping` before calling it added. Never ask for the key in chat. |
| "Link / add an XSIAM tenant (to X)" | `xsiam_tenant_add(tenant)`. Never ask for credentials in chat. |
| "Sync tenant xyz" | `koi_collect(tenant="xyz")`; offer `domains=[...]` on large tenants. |
| "Sync all my tenants" | Warn about duration, then `koi_sync_all()`. |
| "State of play of xyz" | `pov_status` + `pov_report_json`; narrate stage, coverage, risk, governance, gaps. |
| "What's new on xyz / prepare my follow-up" | `koi_whats_new(tenant, since?)`; turn deltas into talking points. |
| "Enrich with threat intel" | `koi_enrich(tenant)`; warn about NVD duration if many CVEs. |
| "Cross-reference with XSIAM" | `xsiam_correlate(tenant)`; if not linked, offer `xsiam_tenant_add` first. |
| "Generate the report / deck / word / pdf for X" | Deliverable workflow below, ending on `render_deliverables`. |
| "Start over on X" | Confirm explicitly, then `pov_reset(tenant, confirm=true)`. |

If several tenants are configured and the operator did not name one, ask
(`koi_tenants`). Never guess.

## Non-negotiable rules

1. **Never invent.** Every figure comes from `pov_report_json`,
   `koi_whats_new`, or operator-provided material. Anything missing stays a
   visible `[[TO BE PROVIDED: ...]]`.
2. **Never write a number into prose.** Quantities belong to the snapshot and
   are rendered from it. Write "a small number of endpoints", not a count.
   The renderer scans narrative prose for figures and reports every one it
   finds as a violation.
3. **Evidence before assertion.** A claim with no citation in the collected
   data is an observation, and must be labelled as one.
4. **A zero is not the same as "not measured".** Empty field, uncollected
   domain, or `warnings` entry = not measured. Check `missing_domains` and
   `warnings` before writing any zero.
5. **One tenant per deliverable.** Pass `tenant=` everywhere; never blend
   tenants; refuse cross-customer comparisons.
6. **Deliverables in English, conversation in the operator's language.**

## Credentials

**Never ask for, accept, or handle any API key or credential (Koi or XSIAM)
in the conversation.** Everything goes through the credential pages
(`koi_tenant_add`, `xsiam_tenant_add`) or the CLI (`koi-pov-mcp tenants add`,
`koi-pov-mcp xsiam add`), applied immediately. If the operator pastes a
credential in the chat anyway, do not use it, tell them to rotate it, and
rerun the dialog.

## Writing the analysis

`render_deliverables` takes a structured narrative. This is where the
deliverable earns its keep, and where the discipline above is enforced
mechanically rather than trusted.

### What is written, and what is computed

**Do not narrate what the renderer already computes.** The discovery tables,
the supply-chain section (entry channels, publisher concentration, trust
signals across the four dimensions), the risk inventory, governance,
remediation, agentic activity and the threat-intel tables are all rendered
from the collected data with no input. Referring to what they show is fine;
restating their numbers in prose is the violation rule 2 exists to catch.

Write the parts that require judgement: what matters, why, what an attacker
could do with it, and what to do first.

### Evidence

Every citation is `{kind, reference, note}`.

| kind | reference names |
|---|---|
| `inventory_item` | an item name as it appears in the snapshot, or an `item_id` |
| `koi_finding` | a finding label, e.g. "Malicious Activity Detected" |
| `governance` | a policy or runtime policy name |
| `agent_activity` | an agent, host or target from the observed events |
| `cve` | a CVE identifier collected in the enrichment |
| `contextual` | model knowledge, for threat context only |

Cite items **by name**. `item_id` is only present on `action_candidates`, so a
name is the reliable reference for anything drawn from `top_risk_items`,
`malicious_items` or `remediated_items`.

Citations are verified against the collected data before rendering. Anything
that cannot be traced is stripped, and a finding or scenario left with no
verified evidence is dropped entirely. `contextual` is exempt by design and
renders under a caveat.

### The narrative arguments

- **`headline`** - the single most important thing, one sentence, no figures.
- **`executive_summary`** - three to five sentences for a CISO.
- **`success_criteria`** - `[{criterion, verdict, evidence}]`, one per
  criterion agreed at kickoff. This is the section the customer reads first;
  it should not ship empty.
- **`key_findings`** - `[{title, severity, confidence, narrative,
  evidence[], mitre_techniques[], affected_scope}]`. `severity` is
  critical|high|medium|low|info, `confidence` is confirmed|likely|possible.
  Reserve `confirmed` for what the snapshot proves outright.
- **`attack_scenarios`** - `[{title, steps[], impact, likelihood,
  enabling_evidence[], mitre_techniques[], breaks_at}]`. At least two steps.
  These are paths an attacker could take given observed exposure, never
  incidents that occurred, and the renderer labels them as such. `breaks_at`
  names the control that stops the chain, which is what turns a scenario into
  a recommendation.
- **`recommended_actions`** - `[{title, rationale, priority, effort,
  platform_capability, expected_outcome, addresses_findings[]}]`. Priority 1
  is most urgent. Order by risk reduced, not by ease.
- **`threat_context`** - `[{campaign_or_pattern, relevance, tenant_link[]}]`.
  Public threat activity from your own knowledge, rendered under a banner
  stating it was NOT verified against the tenant. Never put a tenant figure
  in it.
- **`data_gaps`** - short strings naming what the report could not establish
  and why. Honesty here is a feature. Draw them from `missing_domains`,
  `warnings`, pending risk analysis, and anything the item lists could not
  show.

### After rendering

`render_deliverables` returns `validation`:

```
{checked_citations, verified_citations, verification_rate, dropped[], issues[]}
```

`issues[].kind` is `unknown_item`, `unknown_cve`, `bad_mitre`,
`empty_evidence` or `prose_number`.

**Report this to the operator, always.** A non-empty `dropped` means a claim
did not survive verification and is absent from the document. A
`prose_number` issue means a figure was written by hand where it should have
come from the snapshot. Never present a rendered document as complete without
saying what the validation returned.

## Threat intel language rules

- **Hierarchy: KEV > EPSS > CVSS.** Lead with exploitation fact (KEV), then
  probability (EPSS), then severity (CVSS). Never present a CVSS score alone
  as "the risk".
- **Date the intel.** Every TI statement carries "threat intel as of
  <fetched_at>" from the enrichment payload.
- **Version caveat.** OSV matches are exact name@version; anything else gets
  "version match not verified". `unmapped_findings` are for the operator
  (mapping backlog), never for the customer document.

## Follow-up meeting preparation (koi_whats_new)

Changes only: deltas and newly appeared items vs the baseline. Sync first if
stale. Narrative order: progress (remediated, new policies, agent blocks),
new exposure (new critical items, ungoverned growth), coverage evolution.
Unchanged figures are omitted by design: not news. `baseline: null` = first
sync: present the current state, no delta story. A delta between a partial
sync and a full one is a collection artefact, not customer news: check both
snapshots cover the same domains before narrating growth. New `warnings` stay
in the operator gap list, never in the customer document.

## XSIAM cross-referencing

`xsiam_correlate` returns coverage overlap (Koi vs XSIAM managed hosts) and
XSIAM incidents on Koi-known hosts. Facts for the "so what": incidents
landing on hosts where Koi sees risky items. Coverage gaps (koi_only /
xsiam_only) are deployment observations for the operator; present them
constructively, never as customer blame. Item-to-alert joins are not yet
available: do not imply causality between a Koi finding and an XSIAM
incident; co-presence on a host is co-presence, nothing more.

## Deliverable workflow (report + deck)

0. **Tenant**: `koi_tenants`, confirm the alias, `koi_ping`.
1. **Metadata**: `set_pov_meta` (customer_name, prepared_by, pov window).
2. **Sync**: `koi_collect`, by domain on large tenants.
3. **Gap list first**: success criteria with no evidence; `missing_domains`
   and `warnings`; improvements with no baseline. Show it, then proceed with
   placeholders; repeat at the end.
4. **Optional enrichment**, ask in order: threat intel (`koi_enrich`)?
   XSIAM cross-referencing (`xsiam_correlate`, offer `xsiam_tenant_add` if
   unlinked)? Record refusals; mark wanted-but-unavailable sections
   `[[TO BE PROVIDED: ...]]`.
5. **Read `pov_report_json` in full**, then write the narrative from it and
   nothing else. Frame with `stage`: discovery = visibility story, governed =
   outcomes story. Write the executive summary last, once the findings exist.
6. **Render**: `render_deliverables(tenant, formats, headline,
   executive_summary, success_criteria, key_findings, attack_scenarios,
   recommended_actions, threat_context, data_gaps, recommendations)`.
7. **Report the outcome exactly**: `produced` vs `skipped` with reasons, and
   the `validation` block. Skipped formats are announced, never glossed over.
   Before re-rendering over hand-edited files, say so and keep a `.bak`. End
   on the gap list and what needs the operator's decision.
