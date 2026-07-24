---
name: koi-pov-deliverables
description: This skill should be used for anything related to running a Koi (Cortex AES) Proof of Value: adding a tenant, syncing tenant data, giving a state of play, preparing a follow-up meeting (what's new), and producing the customer-facing wrap-up (report and deck). Triggers include "add a tenant", "sync tenant X", "sync all my Koi tenants", "status of tenant X", "what's new on tenant X", "prepare my PoV follow-up", "generate the PoV deliverables", "write the PoV report", "build the restitution deck", "restitution de PoV", in any language.
version: 2.4.0
---

# Koi PoV operations and deliverables (MCP-backed, multi-tenant)

Run Koi Proofs of Value through the **koi-pov MCP server**: dedicated
environment per tenant, data sync, follow-up preparation, and the two closing
artefacts (a **detailed report** and a **restitution deck**, both in English,
structured around the success criteria agreed at kickoff).

The deliverable answers one question for the decision-maker:

> **Did Koi meet the success criteria we set, and what is that worth to us?**

## Natural-language command mapping

The operator speaks in any language; map intent to tools:

| Operator says (any phrasing/language) | Do |
|---|---|
| "Add a (new) tenant" | Ask for a short alias if not given (e.g. acme). Call `koi_tenant_add(alias)`; a native dialog opens on their machine for the key. Never ask for the key in chat. |
| "Sync tenant xyz" / "synchronise les donnees de xyz" | `koi_collect(tenant="xyz")`. Offer `domains=[...]` on large tenants. |
| "Sync all my tenants" | Warn about duration, then `koi_sync_all()`. Summarise per-tenant results and failures. |
| "State of play / etat des lieux of xyz" | `pov_status(tenant="xyz")` + `pov_report_json`, narrate: stage, coverage, risk picture, governance, gaps and warnings. |
| "What's new on xyz / prepare my follow-up meeting" | `koi_whats_new(tenant="xyz")` (use `since=` if they name a date). Turn deltas into meeting talking points. |
| "Generate the report / deck / deliverables for xyz" | Full deliverable workflow below on that tenant. |
| "Start over on xyz / new PoV" | Confirm explicitly, then `pov_reset(tenant="xyz", confirm=true)`. |

If several tenants are configured and the operator did not name one, ask
(`koi_tenants` gives the list). Never guess.

## Non-negotiable rules

1. **Never invent.** Every figure comes from `pov_report_json` /
   `koi_whats_new` for the selected tenant or from material the operator
   provides. Anything missing stays a visible `[[TO BE PROVIDED: ...]]`.
2. **Evidence before assertion.** A result with no evidence in the collected
   data is an observation, and must be labelled as one.
3. **A zero is not the same as "not measured".** An empty field, an
   uncollected domain, or an entry in `warnings` means *not measured*. Check
   `pov_status` `missing_domains` and `warnings` before writing any zero.
4. **One tenant per deliverable.** Pass `tenant=` on every call; never blend
   figures from two tenants; refuse cross-customer comparisons (PoV data is
   confidential to each customer).
5. **Deliverables in English, conversation in the operator's language.**

## Credentials

**Never ask for, accept, or handle a Koi API key in the conversation.**
Adding or fixing a key goes through `koi_tenant_add` (native dialog) or, if
no GUI is available, `koi-pov-mcp tenants add <alias>` in a terminal. Both
apply immediately. If the operator pastes a key in the chat anyway, do not
use it, tell them to rotate it in the Koi console, and rerun the dialog.

## Follow-up meeting preparation (koi_whats_new)

The diff returns **changes only**: deltas and newly appeared items between
the latest snapshot and a baseline (previous sync, or `since=` date).

- Sync first if the data is stale, then diff.
- Build the narrative from: progress (newly remediated, new policies, agent
  blocks), new exposure (new critical/high items, ungoverned growth), and
  coverage evolution (devices, items discovered).
- Unchanged figures are omitted by design: do not present them as news.
- `baseline: null` means first sync: there is no delta story; say so and
  present the current state instead.
- New `warnings` are collection problems, not customer findings; keep them in
  the operator-facing gap list, never in the customer document.

## Deliverable workflow (report + deck)

0. **Tenant**: `koi_tenants`, confirm the alias, `koi_ping(tenant=...)`.
1. **Metadata**: `set_pov_meta(tenant=..., customer_name=..., ...)`.
2. **Sync**: `koi_collect(tenant=...)`, by domain on large tenants.
3. **Gap list first**: from `pov_status` and `pov_report_json`: success
   criteria with no matching evidence; `missing_domains` and `warnings`;
   claimed improvements with no baseline. Show it to the operator, then
   proceed with placeholders; repeat the list at the end.
4. **Optional enrichment**: ask in this order: threat-intel enrichment?
   XSIAM cross-referencing? If the tools are not yet available, record the
   answer and mark the sections `[[TO BE PROVIDED: ...]]`.
5. **Write**: report first (executive summary written last), then the deck as
   a 12-16 slide synthesis. Frame with `stage`: discovery tenant = visibility
   story; governed tenant = outcomes story. Structure: scope and coverage,
   success criteria scorecard, discovery findings, risk analysis, governance
   and remediation outcomes, agentic runtime activity, recommendations,
   appendix.
6. **Render and hand back**: write files into the tenant's `deliverables/`
   directory (path in `pov_status`). If a `render_deliverables` tool is
   available, use it and report exactly which formats (PPTX, DOCX, PDF) it
   produced. If not, deliver Markdown there and state explicitly which
   formats were not rendered and why. End on the gap list and what needs the
   operator's decision.

## Regenerating over existing output

Before overwriting a deliverable file, check whether it was edited by hand
since it was generated. If it was, say so and save the old version as `*.bak`
rather than silently replacing an evening of the operator's edits.
