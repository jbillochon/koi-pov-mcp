---
name: koi-pov-deliverables
description: This skill should be used when closing out a Koi (Cortex AES) Proof of Value and producing the customer-facing wrap-up. Triggers include "generate the PoV deliverables", "write the PoV report", "build the restitution deck", "collect the PoV data", "PoV wrap-up", "PoV closeout", "restitution de PoV". It collects tenant evidence through the koi-pov MCP server (multi-tenant), reviews gaps, then produces an English report and slide deck organised around the success criteria agreed at kickoff. Also use when reviewing or revising an existing PoV report or deck.
version: 2.1.0
---

# Koi PoV deliverables (MCP-backed, multi-tenant)

Produce the two closing artefacts of a Koi Proof of Value: a **detailed report**
and a **restitution deck**, both in English, both structured around the success
criteria agreed at kickoff. Tenant evidence comes from the **koi-pov MCP
server**; this skill governs how that evidence becomes a customer document.

The deliverable answers one question for the decision-maker:

> **Did Koi meet the success criteria we set, and what is that worth to us?**

Everything else exists to support that answer. A report that reads as a feature
tour has failed even if every fact in it is true.

## Before anything else: this is a real customer document

Five rules, in priority order. They override style, length and completeness.

1. **Never invent.** Every figure comes from `pov_report_json` for the selected
   tenant or from material the operator provides. Anything missing stays a
   visible `[[TO BE PROVIDED: ...]]`. If you are about to type a digit you did
   not read in the collected data, stop and write a placeholder.
2. **Evidence before assertion.** Every result ties to a field of the collected
   report or an operator-supplied artefact. A result with no evidence is an
   observation, and must be labelled as one.
3. **A zero is not the same as "not measured".** An empty field, an uncollected
   domain, or an entry in `warnings` means *not measured*. Reporting
   "0 incidents" for a domain that failed to collect is a fabrication with a
   number attached. Check `pov_status` `missing_domains` and `warnings` before
   writing any zero.
4. **One tenant per deliverable.** The operator may run several PoVs in
   parallel. Confirm the tenant at the start, pass `tenant=` on every tool
   call, and never blend figures from two tenants in one document. If a
   comparison across customers is requested, refuse: PoV data is confidential
   to each customer.
5. **Deliverables in English, conversation with the operator in their
   language.** The report and deck are customer-facing and English. The
   exchange about them is not.

## Credentials

**Never ask for, accept, or handle a Koi API key (or any credential) in the
conversation.** If `koi_ping` reports NOT CONFIGURED or AUTH FAILED, direct the
operator to the `KOI_API_KEY[_<ALIAS>]` entries in the MCP server's env block
(`claude_desktop_config.json`) and to restart Claude. Then stop until it works.

## Workflow

Run these in order. Do not skip step 3: it is what stops a confident-looking
document being built on gaps.

### 0. Tenant and connectivity

Call `koi_tenants`. If more than one tenant is configured, ask the operator
which one this session is about, and use that alias everywhere. Then
`koi_ping(tenant=...)`; only proceed on OK.

### 1. Metadata

Ask the operator for customer name, PoV window, author if not already set, then
call `set_pov_meta(tenant=..., ...)`.

### 2. Collect

Call `koi_collect(tenant=...)`. Prefer one or two domains per call on large
tenants (collection is synchronous and the API rate limit is 30 req/min per
route). Domains: devices, groups, inventory, inventory_views, policies, lists,
remediations, approvals, alerts, agent_activity.

Supplementary material from the operator (kickoff success criteria, meeting
notes, screenshots) is welcome at any point and is evidence like any other.

### 3. Report the gaps before writing anything

From `pov_status(tenant=...)` and `pov_report_json(tenant=...)`, produce a
short gap list **first**, and show it to the operator:

- success criteria from kickoff with no matching collected evidence: the most
  damaging gap, because the scorecard is the deliverable;
- domains listed in `missing_domains` or present in `warnings`;
- baseline ("before") figures missing where an improvement is claimed: an
  improvement with no baseline is not a measurement;
- anything the operator asserted verbally that the tenant data does not show.

Then continue and generate. Do not block on the gaps; carry them through as
placeholders and repeat the list at the end. The operator decides what is
worth chasing.

### 4. Optional enrichment

Ask the operator, in this order, once collection is done:

1. **Threat-intel enrichment** of the top findings?
2. **XSIAM cross-referencing** of endpoints and alerts?

If the corresponding MCP tools are not available (they arrive in a later
version of koi-pov-mcp), say so plainly, record the answer, and mark the
related sections `[[TO BE PROVIDED: TI enrichment]]` /
`[[TO BE PROVIDED: XSIAM correlation]]` if the operator wanted them.

### 5. Write the report, then the deck

Work from `pov_report_json(tenant=...)` as the single source of truth. Use the
tenant `stage` field (`discovery` vs `governed`) to frame the narrative: a
discovery tenant is a visibility story; a governed tenant is an outcomes story.

Report structure: executive summary (written **last**), scope and coverage,
success criteria scorecard, discovery findings, risk analysis, governance and
remediation outcomes, agentic runtime activity, recommendations, appendix.

The deck is a **synthesis, 12 to 16 slides**, not a compressed copy of the
report. If a slide would only make sense to someone who read the report, it
belongs in the report.

### 6. Render and hand back

If a `render_deliverables` MCP tool is available, use it and report exactly
which formats it produced. If not, deliver Markdown files and state explicitly
which formats (PPTX, DOCX, PDF) were not rendered and why. A successful build
claim with unverified formats is a rule-1 violation.

End on the gap list and what needs the operator's decision, not on a summary
of what you did.

## Operator commands

| Command | Effect |
|---|---|
| `Check the tenant` / `Check <alias>` | Steps 0-3 only: ping, collect, gap list. Generate nothing. |
| `Generate the deliverables` | Full workflow on the confirmed tenant. |
| `Generate the report only` / `the deck only` | Partial. |
| `Status` / `Status <alias>` | Call `pov_status` and summarise. |
| `New PoV on <alias>` | Confirm with the operator, then `pov_reset(tenant, confirm=true)`. |

## Regenerating over existing output

Before overwriting a deliverable file, check whether it was edited by hand
since it was generated. If it was, say so and save the old version as `*.bak`
rather than silently replacing an evening of the operator's edits.
