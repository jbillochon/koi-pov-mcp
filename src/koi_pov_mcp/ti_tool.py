"""MCP tool for deterministic TI enrichment (v2): curated MITRE mapping,
NVD CVE detail, OSV package vulnerabilities, CISA KEV, FIRST EPSS.
Registered onto the shared FastMCP instance (see server.py bottom)."""

from __future__ import annotations

import json
import re
from dataclasses import asdict

from .enrichment import enrich as nvd_mitre_enrich, extract_cve_ids, FINDING_TO_MITRE
from . import ti_sources


def _all_findings(report: dict) -> set[str]:
    def norm(name: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")
    seen: set[str] = set()
    for entry in report.get("finding_frequency") or []:
        if isinstance(entry, dict) and entry.get("finding"):
            seen.add(norm(entry["finding"]))
    for key in ("top_risk_items", "action_candidates"):
        for item in report.get(key) or []:
            for f in (item or {}).get("findings") or []:
                seen.add(norm(f if isinstance(f, str) else f.get("finding_id", "")))
    return {s for s in seen if s}


def register(mcp, resolve_tenant, load_report, tenant_dir):
    @mcp.tool()
    def koi_enrich(
        tenant: str = "default",
        fetch_cves: bool = True,
        max_cves: int = 15,
        osv: bool = True,
    ) -> dict:
        """Threat-intel enrichment of one tenant's collected report.
        Deterministic facts only, no model-generated intel:
        - MITRE ATT&CK techniques from the curated Koi-finding mapping
          (unmapped findings are listed, never guessed)
        - OSV.dev package vulnerabilities for high-risk npm/PyPI items
          (exact name@version match, batch query)
        - CISA KEV membership (known exploited) and FIRST EPSS scores for
          every CVE in scope
        - NVD detail (CVSS, CWE, description) for the top CVEs, KEV members
          first then highest EPSS

        Saves <tenant>/enrichment.json with a fetched_at date; pov_report_json
        then includes it under 'enrichment'. Deliverables must date the intel
        ("threat intel as of <fetched_at>") and follow the language hierarchy
        KEV > EPSS > CVSS.

        NVD lookups are the slow part (~6.5s/CVE without NVD_API_KEY in the
        server env, ~1.2s with); warn the operator or lower max_cves if many
        CVEs are in scope. OSV/KEV/EPSS are fast batch calls.
        """
        resolved = resolve_tenant(tenant)
        if isinstance(resolved, dict):
            return resolved
        alias, _ = resolved

        report_obj = load_report(alias)
        if not report_obj.collected_domains:
            return {
                "tenant": alias,
                "error": "Nothing collected yet for this tenant. Run koi_collect first.",
            }
        report = asdict(report_obj)
        errors: list[str] = []

        # 1. Curated MITRE mapping + unmapped findings (facts about coverage)
        base = nvd_mitre_enrich(report, fetch_cves=False)
        errors.extend(base.get("errors") or [])
        mapped = set(base.get("mitre") or {})
        unmapped = sorted(_all_findings(report) - mapped - set(FINDING_TO_MITRE))

        # 2. OSV: proactive package lookups (exact version match)
        osv_hits: dict[str, list[str]] = {}
        osv_records: dict[str, dict] = {}
        if osv:
            packages = ti_sources.collect_packages(report)
            osv_hits, osv_errs = ti_sources.osv_query(packages)
            errors.extend(osv_errs)
            distinct_ids = sorted({vid for ids in osv_hits.values() for vid in ids})
            for vid in distinct_ids[:15]:
                rec = ti_sources.osv_details(vid)
                if rec:
                    osv_records[vid] = rec

        # 3. CVE universe: mentioned in findings + resolved from OSV aliases
        cve_ids = set(extract_cve_ids(report, limit=40))
        for rec in osv_records.values():
            cve_ids.update(rec.get("aliases") or [])
        cve_ids = sorted(cve_ids)

        # 4. KEV + EPSS for the whole universe (cheap batch calls)
        kev, kev_errs = ti_sources.fetch_kev()
        errors.extend(kev_errs)
        epss, epss_errs = ti_sources.fetch_epss(cve_ids)
        errors.extend(epss_errs)

        # 5. NVD detail for the top CVEs: KEV members first, then EPSS desc
        cves: dict[str, dict] = {}
        if fetch_cves and cve_ids:
            ranked = sorted(
                cve_ids,
                key=lambda c: (
                    c in kev,
                    epss.get(c, {}).get("epss", 0.0),
                ),
                reverse=True,
            )
            nvd = nvd_mitre_enrich(
                {"finding_frequency": [{"finding": " ".join(ranked[:max_cves])}]},
                fetch_cves=True,
                max_cves=max_cves,
            )
            cves = nvd.get("cves") or {}
            errors.extend(e for e in nvd.get("errors") or [] if "mitre" not in e)

        # 6. Overlay KEV/EPSS on every CVE we know about
        for cid in cve_ids:
            entry = cves.setdefault(cid, {"id": cid})
            entry["kev"] = cid in kev
            if cid in kev:
                entry["kev_date_added"] = kev[cid]
            if cid in epss:
                entry["epss"] = epss[cid]["epss"]
                entry["epss_percentile"] = epss[cid]["percentile"]

        payload = {
            "fetched_at": ti_sources.now_iso(),
            "mitre": base.get("mitre") or {},
            "unmapped_findings": unmapped,
            "cves": cves,
            "osv": {
                "matches": osv_hits,
                "records": osv_records,
            },
            "kev_catalog_size": len(kev),
            "errors": errors,
        }

        out_path = tenant_dir(alias) / "enrichment.json"
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)

        return {
            "tenant": alias,
            "enrichment_path": str(out_path),
            "fetched_at": payload["fetched_at"],
            "mitre_mapped_findings": len(payload["mitre"]),
            "unmapped_findings": unmapped,
            "osv_packages_hit": len(osv_hits),
            "cves_in_scope": len(cve_ids),
            "kev_hits": sorted(c for c in cves if cves[c].get("kev")),
            "errors": errors,
        }

    return koi_enrich
