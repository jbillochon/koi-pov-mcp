---
name: koi-pov-deliverables
description: This skill should be used for anything related to running a Koi (Cortex AES) Proof of Value: adding a tenant, linking an XSIAM tenant, syncing tenant data, giving a state of play, preparing a follow-up meeting (what's new), TI enrichment, and producing the customer-facing wrap-up (Word report, PDF, slide deck). Triggers include "add a tenant", "link XSIAM", "sync tenant X", "sync all my Koi tenants", "status of tenant X", "what's new on tenant X", "prepare my PoV follow-up", "generate the report / deck / word / pdf for tenant X", "restitution de PoV", in any language.
version: 2.6.0
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
| "Add a (new) tenant" | Ask for a short alias if not given. `koi_tenant_add(alias)`: native dialog for the key. Never ask for the key in chat. |
| "Link / add an XSIAM tenant (to X)" | `xsiam_tenant_add(tenant)`: native dialog with API URL, Key ID, key, advanced checkbox. Never ask for credentials in chat. |
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
2. **Evidence before assertion.** A result with no evidence in the collected
   data is an observation, and must be labelled as one.
3. **A zero is not the same as "not measured".** Empty field, uncollected
   domain, or `warnings` entry = not measured. Check `missing_domains` and
   `warnings` before writing any zero.
4. **One tenant per deliverable.** Pass `tenant=` everywhere; never blend
   tenants; refuse cross-customer comparisons.
5. **Deliverables in English, conversation in the operator's language.**

## Credentials

**Never ask for, accept, or handle any API key or credential (Koi or XSIAM)
in the conversation.** Everything goes through the native dialogs
(`koi_tenant_add`, `xsiam_tenant_add`) or the CLI (`koi-pov-mcp tenants add`,
`koi-pov-mcp xsiam add`), applied immediately. If the operator pastes a
credential in the chat anyway, do not use it, tell them to rotate it, and
rerun the dialog.

## Threat intel language rules

- **Hierarchy: KEV > EPSS > CVSS.** Lead with exploitation fact (KEV), then
  probability (EPSS), then severity (CVSS). Never present a CVSS score alone
  as "the risk".
- **Date the intel.** Every TI statement in a deliverable carries
  "threat intel as of <fetched_at>" from the enrichment payload.
- **Version caveat.** OSV matches are exact name@version; anything else gets
  "version match not verified". `unmapped_findings` are for the operator
  (mapping backlog), never for the customer document.

## Follow-up meeting preparation (koi_whats_new)

Changes only: deltas and newly appeared items vs the baseline. Sync first if
stale. Narrative order: progress (remediated, new policies, agent blocks),
new exposure (new critical items, ungoverned growth), coverage evolution.
Unchanged figures are omitted by design: not news. `baseline: null` = first
sync: present the current state, no delta story. New `warnings` stay in the
operator gap list, never in the customer document.

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
1. **Metadata**: `set_pov_meta`.
2. **Sync**: `koi_collect`, by domain on large tenants.
3. **Gap list first**: success criteria with no evidence; `missing_domains`
   and `warnings`; improvements with no baseline. Show it, then proceed with
   placeholders; repeat at the end.
4. **Optional enrichment**, ask in order: threat intel (`koi_enrich`)?
   XSIAM cross-referencing (`xsiam_correlate`, offer `xsiam_tenant_add` if
   unlinked)? Record refusals; mark wanted-but-unavailable sections
   `[[TO BE PROVIDED: ...]]`.
5. **Write the narrative** from `pov_report_json` only: executive summary
   (last), success criteria verdicts ({criterion, verdict, evidence}, every
   evidence traceable), recommendations. Frame with `stage`: discovery =
   visibility story, governed = outcomes story.
6. **Render**: `render_deliverables(tenant, formats, executive_summary,
   recommendations, success_criteria)`. Report exactly `produced` vs
   `skipped` with reasons; skipped formats are announced, never glossed
   over. Before re-rendering over hand-edited files, say so and keep a
   `.bak`. End on the gap list and what needs the operator's decision.
