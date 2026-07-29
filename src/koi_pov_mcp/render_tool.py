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
        key_findings: list[dict] | None = None,
        attack_scenarios: list[dict] | None = None,
        recommended_actions: list[dict] | None = None,
        threat_context: list[dict] | None = None,
        data_gaps: list[str] | None = None,
    ) -> dict:
        """Render the customer deliverables for one tenant into its
        deliverables/ directory: report.docx, deck.pptx, and report.pdf when
        the PDF engine is available. Use when the operator asks to "generate
        the report / deck / word / pdf for tenant X" in any language.

        Every number comes from the tenant's collected JSON (+ enrichment).
        NEVER write a figure into narrative prose: quantities belong to the
        snapshot, and any number found in prose is reported back as a
        violation. Leave an argument empty rather than inventing, because the
        renderer inserts a visible [[TO BE PROVIDED]] placeholder.

        Narrative arguments:
        - headline: the single most important thing, in one sentence.
        - executive_summary, recommendations: plain text.
        - success_criteria: [{criterion, verdict, evidence}].
        - key_findings: [{title, severity, confidence, narrative, evidence[],
          mitre_techniques[], affected_scope}]. severity is
          critical|high|medium|low|info, confidence is
          confirmed|likely|possible.
        - attack_scenarios: [{title, steps[], impact, likelihood,
          enabling_evidence[], mitre_techniques[], breaks_at}]. At least two
          steps. Hypothetical paths given observed exposure, never incidents
          that occurred, and the renderer labels them as such.
        - recommended_actions: [{title, rationale, priority, effort,
          platform_capability, expected_outcome, addresses_findings[]}].
          priority 1 is most urgent; effort is low|medium|high. Order by risk
          reduced, not by ease.
        - threat_context: [{campaign_or_pattern, relevance, tenant_link[]}].
          Public threat activity from model knowledge, rendered under a caveat
          stating it was NOT verified against the tenant.
        - data_gaps: short strings naming where the data was thin. Honesty
          here is a feature, not an admission.

        Evidence is {kind, reference, note} where kind is inventory_item,
        koi_finding, governance, agent_activity, cve or contextual. reference
        names something present in pov_report_json: an item_id or item name, a
        finding label, a policy name, an agent or host, or a CVE collected in
        the enrichment. Unverifiable evidence is stripped, and a finding or
        scenario left with none is dropped entirely. contextual evidence is
        exempt by design.

        Report exactly what came back: 'produced' formats with paths,
        'skipped' formats with the reason, and 'validation'. A successful call
        with skipped formats is NOT a full delivery. A non-empty
        validation.dropped or validation.issues means claims did not survive
        verification and MUST be shown to the operator, never quietly ignored.
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
            key_findings=key_findings,
            attack_scenarios=attack_scenarios,
            recommended_actions=recommended_actions,
            threat_context=threat_context,
            data_gaps=data_gaps,
        )
        result["tenant"] = alias
        return result

    return render_deliverables
