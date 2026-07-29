"""MCP tool for deliverable rendering; registered onto the shared FastMCP
instance (see server.py bottom)."""

from __future__ import annotations

from .rendering import render


def register(mcp, resolve_tenant, report_json_fn, tenant_dir):
    @mcp.tool()
    def render_deliverables(
        tenant: str = "default",
        formats: list[str] | None = None,
        headline: str = "",
        executive_summary: str = "",
        recommendations: str = "",
        success_criteria: list[dict] | None = None,
        findings: list[dict] | None = None,
        attack_scenarios: list[dict] | None = None,
        recommended_actions: list[dict] | None = None,
        threat_context: list[dict] | None = None,
    ) -> dict:
        """Render the customer deliverables for one tenant into its
        deliverables/ directory: report.docx, deck.pptx, and report.pdf when
        WeasyPrint is available. Use when the operator asks to "generate the
        report / deck / word / pdf for tenant X" in any language.

        Every number comes from the tenant's collected JSON (+ enrichment).
        Narrative goes through the arguments and MUST follow the skill's rules:
        write from pov_report_json only, and leave an argument empty rather
        than inventing, because the renderer inserts a visible
        [[TO BE PROVIDED]] placeholder.

        Narrative arguments:
        - headline: one sentence naming the central problem.
        - executive_summary, recommendations: plain text.
        - success_criteria: [{criterion, verdict, evidence}].
        - findings: [{title, severity, confidence, mitre[], narrative, scope,
          evidence[]}]. severity is critical|high|medium|low|informational,
          confidence is confirmed|probable|possible|observation.
        - attack_scenarios: [{title, likelihood, mitre[], chain[], impact,
          breaks_chain, evidence[]}]. likelihood is likely|possible|unlikely,
          chain needs at least two steps. Scenarios are illustrative paths, not
          incidents that occurred, and the renderer says so.
        - recommended_actions: [{rank, title, effort, rationale, outcome,
          capability}]. effort is low|medium|high effort. Rank by risk reduced,
          not by ease.
        - threat_context: [{title, body}]. Public threat activity from model
          knowledge; rendered under a banner stating it was NOT verified
          against the tenant. Never put a tenant figure in it.

        Every evidence entry is {kind, source, detail} where kind is
        inventory_item, koi_finding, policy or metric, and source names
        something that exists in pov_report_json. Evidence that cannot be found
        there is dropped, and a finding or scenario left without evidence is
        dropped with it.

        Report exactly what came back: 'produced' formats with paths, 'skipped'
        formats with the reason, and 'dropped' narrative. A successful call
        with skipped formats is NOT a full delivery. A non-empty 'dropped' list
        means claims did not survive verification and MUST be shown to the
        operator rather than quietly ignored.
        """
        resolved = resolve_tenant(tenant)
        if isinstance(resolved, dict):
            return resolved
        alias, _ = resolved

        data = report_json_fn(alias)
        if not data.get("collected_domains"):
            return {
                "tenant": alias,
                "error": "Nothing collected yet for this tenant. Run koi_collect first.",
            }

        result = render(
            data,
            tenant_dir(alias) / "deliverables",
            formats or ["pptx", "docx", "pdf"],
            executive_summary=executive_summary,
            recommendations=recommendations,
            success_criteria=success_criteria,
            headline=headline,
            findings=findings,
            attack_scenarios=attack_scenarios,
            recommended_actions=recommended_actions,
            threat_context=threat_context,
        )
        result["tenant"] = alias
        return result

    return render_deliverables
