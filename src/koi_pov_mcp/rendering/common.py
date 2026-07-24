"""
Shared helpers for the Cortex-themed renderers: null-aware formatting and
the domain map that decides whether a figure was measured at all.
"""

from __future__ import annotations

NOT_MEASURED = "not measured"

# Which collection domain each figure depends on. A figure whose domain was
# never collected is absent, not zero, and must say so on the page.
FIELD_DOMAIN = {
    "devices_total": "devices",
    "devices_active": "devices",
    "devices_by_os": "devices",
    "groups": "groups",
    "items_total": "inventory",
    "unique_publishers": "inventory",
    "items_by_risk": "inventory",
    "items_by_marketplace": "inventory",
    "top_risk_items": "inventory",
    "finding_frequency": "inventory",
    "malicious_items": "inventory",
    "ungoverned_high_risk": "inventory",
    "action_candidates": "inventory",
    "exposed_installs": "inventory",
    "items_by_view": "inventory_views",
    "policies": "policies",
    "policies_enabled": "policies",
    "runtime_policies": "policies",
    "allowlist_count": "lists",
    "blocklist_count": "lists",
    "remediations_total": "remediations",
    "remediations_by_status": "remediations",
    "remediated_items": "remediations",
    "approvals_by_status": "approvals",
    "alerts_total": "alerts",
    "alerts_by_severity": "alerts",
    "agent_sessions_total": "agent_activity",
    "agent_decisions": "agent_activity",
    "agents_seen": "agent_activity",
    "agent_models": "agent_activity",
    "agent_blocked_examples": "agent_activity",
}


class Data:
    """Null-aware accessor over the aggregated PoV dict."""

    def __init__(self, data: dict):
        self.d = data or {}
        self.meta = self.d.get("meta") or {}
        self.enrichment = self.d.get("enrichment") or {}
        self.xsiam = self.d.get("xsiam") or {}
        self.missing = set(self.d.get("missing_domains") or [])

    def measured(self, field: str) -> bool:
        domain = FIELD_DOMAIN.get(field)
        return domain is None or domain not in self.missing

    def raw(self, field: str, default=None):
        value = self.d.get(field)
        return default if value is None else value

    def get(self, field: str, default=None):
        """Value, or None when its domain was never collected."""
        if not self.measured(field):
            return None
        value = self.d.get(field)
        return default if value is None else value

    def num(self, field: str) -> str:
        """Thousands-separated figure, or 'not measured'."""
        if not self.measured(field):
            return NOT_MEASURED
        value = self.d.get(field)
        if value is None:
            return NOT_MEASURED
        try:
            return f"{int(value):,}"
        except (TypeError, ValueError):
            return str(value)

    def mapping(self, field: str) -> dict:
        value = self.get(field) or {}
        return value if isinstance(value, dict) else {}

    def rows(self, field: str) -> list:
        value = self.get(field) or []
        return value if isinstance(value, list) else []

    @property
    def stage(self) -> str | None:
        return (self.d.get("derived") or {}).get("stage")

    @property
    def risk(self) -> dict:
        return self.mapping("items_by_risk")

    @property
    def critical(self) -> int:
        return int(self.risk.get("critical", 0) or 0)

    @property
    def high(self) -> int:
        return int(self.risk.get("high", 0) or 0)

    @property
    def high_and_critical(self) -> str:
        if not self.measured("items_by_risk"):
            return NOT_MEASURED
        return f"{self.critical + self.high:,}"

    @property
    def customer(self) -> str:
        return self.meta.get("customer_name") or "Customer"

    def ti_rows(self, limit: int = 12) -> list[list[str]]:
        """CVEs ordered by exploitation evidence: KEV, then EPSS, then CVSS."""
        cves = (self.enrichment.get("cves") or {}).values()
        ranked = sorted(
            cves,
            key=lambda c: (bool(c.get("kev")), c.get("epss") or 0.0,
                           c.get("cvss_score") or 0.0),
            reverse=True,
        )
        out = []
        for c in ranked[:limit]:
            epss = c.get("epss")
            out.append([
                c.get("id", ""),
                "Yes" if c.get("kev") else "No",
                f"{epss:.1%}" if isinstance(epss, float) else "-",
                (f"{c['cvss_score']:.1f}"
                 if isinstance(c.get("cvss_score"), (int, float)) else "-"),
                (c.get("cvss_severity") or "-").capitalize(),
            ])
        return out

    def osv_rows(self, limit: int = 10) -> list[list[str]]:
        matches = (self.enrichment.get("osv") or {}).get("matches") or {}
        return [[pkg, str(len(ids)), ", ".join(ids[:3])]
                for pkg, ids in list(matches.items())[:limit]]

    def mitre_rows(self, limit: int = 12) -> list[list[str]]:
        out = []
        for finding, payload in (self.enrichment.get("mitre") or {}).items():
            techniques = ", ".join(
                t.get("id", "") for t in payload.get("techniques", [])
            )
            names = ", ".join(
                t.get("name", "") for t in payload.get("techniques", []) if t.get("name")
            )
            out.append([finding.replace("_", " "), techniques, names])
        return out[:limit]

    @property
    def kev_count(self) -> int:
        return sum(1 for c in (self.enrichment.get("cves") or {}).values()
                   if c.get("kev"))
