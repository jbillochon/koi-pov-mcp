"""MCP tool for deliverable rendering; registered onto the shared FastMCP
instance (see server.py bottom)."""

from __future__ import annotations

from .rendering import render


def register(mcp, resolve_tenant, report_json_fn, tenant_dir):
    @mcp.tool()
    def render_deliverables(
        tenant: str = "default",
        formats: list[str] | None = None,
        executive_summary: str = "",
        recommendations: str = "",
        success_criteria: list[dict] | None = None,
    ) -> dict:
        """Render the customer deliverables for one tenant into its
        deliverables/ directory: report.docx, deck.pptx, and report.pdf when
        WeasyPrint is available. Use when the operator asks to "generate the
        report / deck / word / pdf for tenant X" in any language.

        Every number comes from the tenant's collected JSON (+ enrichment).
        Narrative goes through the arguments and MUST follow the skill's
        rules: executive_summary and recommendations are plain text written
        from pov_report_json only; success_criteria is a list of
        {criterion, verdict, evidence} where every evidence traces to
        collected data. Leave an argument empty rather than inventing: the
        renderer inserts a visible [[TO BE PROVIDED]] placeholder.

        Report exactly what came back: 'produced' formats with paths, and
        'skipped' formats with the reason. A successful call with skipped
        formats is NOT a full delivery; say which formats are missing.
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
        )
        result["tenant"] = alias
        return result

    return render_deliverables
