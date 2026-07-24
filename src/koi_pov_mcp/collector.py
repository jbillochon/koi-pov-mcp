"""
Collects data from the Koi API and aggregates it into a PoV report model.

The model is deliberately decoupled from both the API shape and the rendering
layer, so either side can change independently.

Origin: adapted from jbillochon/povplatform (connectors/koi/collector.py).
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timedelta, timezone
from typing import Any

log = logging.getLogger(__name__)

# Marketplace slug -> human label
MARKETPLACE_LABELS = {
    "chrome_web_store": "Chrome Web Store",
    "edge_add_ons": "Edge Add-ons",
    "firefox_add_ons": "Firefox Add-ons",
    "vscode": "VS Code Marketplace",
    "cursor": "Cursor",
    "windsurf": "Windsurf",
    "open_vsx_registry": "Open VSX",
    "jetbrains": "JetBrains",
    "visual_studio": "Visual Studio",
    "npm": "npm",
    "pypi": "PyPI",
    "homebrew": "Homebrew",
    "chocolatey": "Chocolatey",
    "hugging_face": "Hugging Face",
    "ollama": "Ollama",
    "github_mcp_registry": "GitHub MCP Registry",
    "mcp_registry": "MCP Registry",
    "claude_desktop_extensions": "Claude Desktop Extensions",
    "office_add_ins": "Office Add-ins",
    "notepad++": "Notepad++",
    "docker": "Docker",
    "github": "GitHub",
    "gitlab": "GitLab",
    "bitbucket": "Bitbucket",
    "skill": "Agent Skills",
    "binaries": "Binaries",
    "mac": "macOS Software",
    "windows": "Windows Software",
    "linux": "Linux Software",
}

# Inventory "view" slugs -> label. These map to the platform's own grouping.
VIEWS = {
    "extensions": "Browser & IDE Extensions",
    "code_packages": "Code Packages",
    "mcp_servers": "MCP Servers",
    "ai_models": "AI Models",
    "agentic_ai": "Agentic AI",
    "os_packages": "OS Packages",
    "software": "Software",
    "repositories": "Repositories",
}

RISK_ORDER = ["critical", "high", "medium", "low", "pending"]


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


@dataclass
class PoVMeta:
    customer_name: str = "Customer"
    prepared_by: str = ""
    pov_start: str | None = None
    pov_end: str | None = None
    generated_at: str = field(default_factory=lambda: _iso(datetime.now(timezone.utc)))
    tenant_label: str = ""


@dataclass
class PoVReport:
    """Everything the deliverable builder needs, already aggregated."""

    meta: PoVMeta = field(default_factory=PoVMeta)

    # Coverage
    devices_total: int = 0
    devices_active: int = 0
    devices_by_os: dict[str, int] = field(default_factory=dict)
    groups: list[dict] = field(default_factory=list)

    # Discovery
    items_total: int = 0
    items_by_view: dict[str, int] = field(default_factory=dict)
    items_by_marketplace: dict[str, int] = field(default_factory=dict)
    unique_publishers: int = 0

    # Risk
    items_by_risk: dict[str, int] = field(default_factory=dict)
    top_risk_items: list[dict] = field(default_factory=list)
    finding_frequency: list[dict] = field(default_factory=list)
    malicious_items: list[dict] = field(default_factory=list)
    ungoverned_high_risk: int = 0
    action_candidates: list[dict] = field(default_factory=list)
    exposed_installs: int = 0

    # Governance
    policies: list[dict] = field(default_factory=list)
    policies_enabled: int = 0
    runtime_policies: list[dict] = field(default_factory=list)
    allowlist_count: int = 0
    blocklist_count: int = 0

    # Remediation
    remediations_by_status: dict[str, int] = field(default_factory=dict)
    remediations_total: int = 0
    remediated_items: list[dict] = field(default_factory=list)

    # Approvals
    approvals_by_status: dict[str, int] = field(default_factory=dict)

    # Agentic runtime
    agent_sessions_total: int = 0
    agent_decisions: dict[str, int] = field(default_factory=dict)
    agents_seen: dict[str, int] = field(default_factory=dict)
    agent_models: dict[str, int] = field(default_factory=dict)
    agent_blocked_examples: list[dict] = field(default_factory=list)

    # Alerts
    alerts_total: int = 0
    alerts_by_severity: dict[str, int] = field(default_factory=dict)

    # Collection diagnostics
    warnings: list[str] = field(default_factory=list)
    collected_domains: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------ #
    # Derived state
    # ------------------------------------------------------------------ #

    @property
    def stage(self) -> str:
        """
        Where this tenant sits in the PoV lifecycle.

        'discovery' - visibility only, nothing configured or enforced yet.
        'governed'  - policies and/or remediation are in play.
        """
        has_governance = bool(
            self.policies or self.runtime_policies
            or self.allowlist_count or self.blocklist_count
        )
        has_outcomes = bool(
            self.remediations_total or self.alerts_total
            or self.agent_decisions.get("block") or self.agent_decisions.get("ask")
        )
        return "governed" if (has_governance or has_outcomes) else "discovery"

    @property
    def high_and_critical(self) -> int:
        return (
            self.items_by_risk.get("critical", 0) + self.items_by_risk.get("high", 0)
        )

    @property
    def pending_analysis(self) -> int:
        return self.items_by_risk.get("pending", 0)

    def to_json(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(asdict(self), fh, indent=2, ensure_ascii=False)

    @classmethod
    def from_json(cls, path: str) -> "PoVReport":
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, raw: dict) -> "PoVReport":
        """Build from a dict, ignoring unknown keys and derived properties."""
        data = dict(raw)
        meta = PoVMeta(**data.pop("meta", {}))
        known = {f.name for f in fields(cls)} - {"meta"}
        clean = {k: v for k, v in data.items() if k in known}
        return cls(meta=meta, **clean)


class PoVCollector:
    """Pulls from the Koi API and builds a PoVReport."""

    def __init__(self, client, meta: PoVMeta | None = None,
                 top_n: int = 10, max_pages: int | None = 40):
        self.client = client
        self.meta = meta or PoVMeta()
        self.top_n = top_n
        self.max_pages = max_pages
        self.report = PoVReport(meta=self.meta)

    # -- helpers -------------------------------------------------------- #

    def _safe(self, label: str, fn, *args, **kwargs):
        """Run a collection step, converting failures into warnings."""
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - deliverables must still build
            msg = f"{label}: {type(exc).__name__}: {exc}"
            log.warning("Collection step failed - %s", msg)
            self.report.warnings.append(msg)
            return None

    # -- steps ---------------------------------------------------------- #

    def collect_devices(self) -> None:
        devices = list(self.client.iter_devices(max_pages=self.max_pages))
        self.report.devices_total = len(devices)
        self.report.devices_active = sum(
            1 for d in devices if (d.get("status") or "").lower() == "active"
        )
        os_counter = Counter((d.get("os") or "unknown").lower() for d in devices)
        self.report.devices_by_os = dict(os_counter.most_common())
        log.info("Devices: %d total, %d active", self.report.devices_total,
                 self.report.devices_active)

    def collect_groups(self) -> None:
        groups = list(self.client.iter_groups(max_pages=5))
        self.report.groups = [
            {"name": g.get("name"), "device_count": len(g.get("devices") or [])}
            for g in groups
        ]

    def collect_inventory(self) -> None:
        """Full inventory sweep: totals, risk distribution, top items, findings."""
        items = list(self.client.iter_inventory(max_pages=self.max_pages))
        self.report.items_total = len(items)

        mk = Counter()
        risk = Counter()
        publishers = set()
        finding_counter = Counter()

        for it in items:
            mk[it.get("marketplace") or "unknown"] += 1
            risk[(it.get("risk_level") or "pending").lower()] += 1
            if it.get("publisher_name"):
                publishers.add(it["publisher_name"])
            for f in it.get("findings") or []:
                # findings on the list endpoint are plain strings
                finding_counter[f if isinstance(f, str) else f.get("finding_id", "?")] += 1

        self.report.items_by_marketplace = {
            MARKETPLACE_LABELS.get(k, k): v for k, v in mk.most_common(12)
        }
        self.report.items_by_risk = {k: risk.get(k, 0) for k in RISK_ORDER if risk.get(k)}
        self.report.unique_publishers = len(publishers)
        self.report.finding_frequency = [
            {"finding": k, "count": v} for k, v in finding_counter.most_common(12)
        ]

        # Top risk items, sorted by numeric risk score
        ranked = sorted(
            (i for i in items if i.get("risk") is not None),
            key=lambda i: (i.get("risk") or 0, i.get("endpoint_count") or 0),
            reverse=True,
        )
        self.report.top_risk_items = [
            {
                "name": i.get("item_display_name"),
                "publisher": i.get("publisher_name"),
                "marketplace": MARKETPLACE_LABELS.get(
                    i.get("marketplace"), i.get("marketplace")
                ),
                "version": i.get("version"),
                "risk": i.get("risk"),
                "risk_level": (i.get("risk_level") or "").lower(),
                "endpoints": i.get("endpoint_count") or 0,
                "findings": i.get("findings") or [],
                "status": i.get("status"),
            }
            for i in ranked[: self.top_n]
        ]

        # Malicious / critical subset
        self.report.malicious_items = [
            t for t in self.report.top_risk_items if t["risk_level"] == "critical"
        ][: self.top_n]

        # High/critical items with no governing policy
        ungoverned = [
            i
            for i in items
            if (i.get("risk_level") or "").lower() in ("high", "critical")
            and not i.get("governed_details")
        ]
        self.report.ungoverned_high_risk = len(ungoverned)

        # Ranked by blast radius: risk score weighted by fleet footprint
        ungoverned.sort(
            key=lambda i: (
                (i.get("endpoint_count") or 0) * (i.get("risk") or 0),
                i.get("risk") or 0,
            ),
            reverse=True,
        )
        self.report.action_candidates = [
            {
                "item_id": i.get("item_id"),
                "name": i.get("item_display_name"),
                "publisher": i.get("publisher_name"),
                "marketplace_slug": i.get("marketplace"),
                "marketplace": MARKETPLACE_LABELS.get(
                    i.get("marketplace"), i.get("marketplace")
                ),
                "version": i.get("version"),
                "risk": i.get("risk"),
                "risk_level": (i.get("risk_level") or "").lower(),
                "endpoints": i.get("endpoint_count") or 0,
                "findings": i.get("findings") or [],
            }
            for i in ungoverned[: self.top_n]
        ]
        self.report.exposed_installs = sum(
            (i.get("endpoint_count") or 0) for i in ungoverned
        )

    def collect_inventory_by_view(self) -> None:
        """Per-view counts. One cheap call per view (page_size=1 -> total_count)."""
        counts: dict[str, int] = {}
        for slug, label in VIEWS.items():
            try:
                payload = self.client._get(
                    "/inventory", {"view": slug, "page": 1, "page_size": 1}
                )
                total = (payload or {}).get("total_count", 0)
                if total:
                    counts[label] = total
            except Exception as exc:  # noqa: BLE001
                log.debug("view %s failed: %s", slug, exc)
        self.report.items_by_view = dict(
            sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
        )

    def collect_policies(self) -> None:
        policies = list(self.client.iter_policies(max_pages=10))
        self.report.policies = [
            {
                "name": p.get("name"),
                "action": p.get("action"),
                "enabled": bool(p.get("enabled")),
                "description": p.get("description"),
                "groups": len(p.get("group_ids") or []),
            }
            for p in policies
        ]
        self.report.policies_enabled = sum(1 for p in self.report.policies if p["enabled"])

        rt = list(self.client.iter_runtime_policies(max_pages=10))
        self.report.runtime_policies = [
            {
                "name": p.get("display_name"),
                "mode": p.get("enforcement_mode"),
                "enabled": bool(p.get("enabled")),
                "agents": p.get("agents") or [],
                "rule_types": [r.get("type") for r in (p.get("rules") or [])],
            }
            for p in rt
        ]

    def collect_lists(self) -> None:
        self.report.allowlist_count = len(self.client.get_allowlist() or [])
        self.report.blocklist_count = len(self.client.get_blocklist() or [])

    def collect_remediations(self) -> None:
        rems = list(self.client.iter_remediations(max_pages=self.max_pages))
        self.report.remediations_total = len(rems)
        status_counter = Counter((r.get("status") or "unknown").lower() for r in rems)
        self.report.remediations_by_status = dict(status_counter.most_common())

        done = [r for r in rems if (r.get("status") or "").lower() == "remediated"]
        self.report.remediated_items = [
            {
                "name": r.get("item_display_name"),
                "hostname": r.get("hostname"),
                "platform": r.get("platform"),
                "risk_level": (r.get("risk_level") or "").lower(),
                "reason": r.get("reason"),
                "version": r.get("version"),
            }
            for r in done[: self.top_n]
        ]

    def collect_approvals(self) -> None:
        reqs = list(self.client.iter_approval_requests(max_pages=20))
        counter = Counter((r.get("approval_status") or "unknown").lower() for r in reqs)
        self.report.approvals_by_status = dict(counter.most_common())

    def collect_alerts(self, days: int = 30) -> None:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
        alerts = list(
            self.client.iter_alerts(
                created_at_gte=_iso(start), created_at_lte=_iso(end), max_pages=20
            )
        )
        self.report.alerts_total = len(alerts)
        sev = Counter((a.get("severity") or "unknown") for a in alerts)
        self.report.alerts_by_severity = dict(sev.most_common())

    def collect_agent_activity(self, days: int = 30) -> None:
        """Sessions support a 30-day window; events are capped at 24h."""
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=min(days, 30))
        sessions = list(
            self.client.iter_agent_sessions(
                created_at_gte=_iso(start),
                created_at_lte=_iso(end),
                max_pages=self.max_pages,
            )
        )
        self.report.agent_sessions_total = len(sessions)

        decisions = Counter()
        agents = Counter()
        models = Counter()
        for s in sessions:
            agents[s.get("agent") or "unknown"] += 1
            for m in s.get("models") or []:
                models[m] += 1
            for k, v in (s.get("decisions") or {}).items():
                decisions[k] += int(v or 0)

        self.report.agent_decisions = dict(decisions)
        self.report.agents_seen = dict(agents.most_common())
        self.report.agent_models = dict(models.most_common(8))

        # Blocked events from the last 24h (API window limit)
        ev_start = end - timedelta(hours=24)
        events = list(
            self.client.iter_agent_events(
                created_at_gte=_iso(ev_start), created_at_lte=_iso(end), max_pages=10
            )
        )
        blocked = [e for e in events if (e.get("verdict") or "").lower() == "block"]
        self.report.agent_blocked_examples = [
            {
                "agent": e.get("agent"),
                "host": e.get("host"),
                "action": (e.get("hits") or [{}])[0].get("action"),
                "target": (e.get("hits") or [{}])[0].get("target"),
                "timestamp": e.get("timestamp"),
            }
            for e in blocked[: self.top_n]
        ]
