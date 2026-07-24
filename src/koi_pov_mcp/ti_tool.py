"""MCP tool for deterministic TI enrichment; registered onto the shared
FastMCP instance at import time (see server.py bottom)."""

from __future__ import annotations

import json
from dataclasses import asdict

from .enrichment import enrich


def register(mcp, resolve_tenant, load_report, tenant_dir):
    @mcp.tool()
    def koi_enrich(
        tenant: str = "default",
        fetch_cves: bool = True,
        max_cves: int = 15,
    ) -> dict:
        """Threat-intel enrichment of one tenant's collected report:
        MITRE ATT&CK techniques mapped from Koi findings (static, human-curated
        mapping) and CVE records fetched from the NVD (CVSS score/severity,
        CWE, description). Deterministic facts only, no model-generated intel.

        Saves the result as <tenant>/enrichment.json; pov_report_json then
        includes it under 'enrichment'. Use when the operator accepts the
        TI-enrichment option of the deliverable workflow.

        CVE lookups respect NVD rate limits: without an NVD_API_KEY in the
        server env this is ~6.5s per CVE, so 15 CVEs take ~90s. Warn the
        operator before launching if many CVEs are present, or lower max_cves.
        Only cite techniques/CVEs returned here; findings with no mapping stay
        unmapped rather than guessed.
        """
        resolved = resolve_tenant(tenant)
        if isinstance(resolved, dict):
            return resolved
        alias, _ = resolved

        report = load_report(alias)
        if not report.collected_domains:
            return {
                "tenant": alias,
                "error": "Nothing collected yet for this tenant. Run koi_collect first.",
            }

        payload = enrich(asdict(report), fetch_cves=fetch_cves, max_cves=max_cves)
        out_path = tenant_dir(alias) / "enrichment.json"
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)

        return {
            "tenant": alias,
            "enrichment_path": str(out_path),
            "mitre_mapped_findings": len(payload["mitre"]),
            "cves_resolved": len(payload["cves"]),
            "errors": payload["errors"],
            "enrichment": payload,
        }

    return koi_enrich
