"""
koi-pov-mcp server (stdio).

Exposes Koi PoV collection as MCP tools for Claude Desktop / Claude Code.
Credentials come from the environment (KOI_API_KEY), never from the chat.

State: a single pov_report.json in the working directory
(KOI_POV_WORKDIR, or the OS user-data dir by default). Collection domains
merge into it incrementally, so you can collect in several passes.
"""

from __future__ import annotations

import os
from dataclasses import asdict
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from platformdirs import user_data_dir

from .client import KoiAuthError, KoiAPIError, KoiClient
from .collector import PoVCollector, PoVMeta, PoVReport

APP_NAME = "koi-pov-mcp"

mcp = FastMCP("koi-pov")

# Domain name -> collector method name. Order matters for collect order.
DOMAINS = {
    "devices": "collect_devices",
    "groups": "collect_groups",
    "inventory": "collect_inventory",
    "inventory_views": "collect_inventory_by_view",
    "policies": "collect_policies",
    "lists": "collect_lists",
    "remediations": "collect_remediations",
    "approvals": "collect_approvals",
    "alerts": "collect_alerts",
    "agent_activity": "collect_agent_activity",
}


def _workdir() -> Path:
    p = Path(os.environ.get("KOI_POV_WORKDIR") or user_data_dir(APP_NAME))
    p.mkdir(parents=True, exist_ok=True)
    return p


def _report_path() -> Path:
    return _workdir() / "pov_report.json"


def _load_report() -> PoVReport:
    p = _report_path()
    if p.exists():
        return PoVReport.from_json(str(p))
    return PoVReport()


def _save_report(report: PoVReport) -> str:
    path = _report_path()
    report.to_json(str(path))
    return str(path)


def _client() -> KoiClient:
    # Raises ValueError with a clear message if KOI_API_KEY is missing.
    return KoiClient()


# ---------------------------------------------------------------------- #
# Tools
# ---------------------------------------------------------------------- #


@mcp.tool()
def koi_ping() -> str:
    """Check Koi API connectivity and that KOI_API_KEY is valid.

    Call this first, before any collection. If it fails with an auth error,
    the operator must set KOI_API_KEY in the MCP server environment
    (claude_desktop_config.json env block). Never ask for the key in chat.
    """
    try:
        _client().ping()
    except ValueError as exc:
        return f"NOT CONFIGURED: {exc}"
    except KoiAuthError:
        return (
            "AUTH FAILED: the API key was rejected (401). "
            "Fix KOI_API_KEY in the MCP server env and restart Claude."
        )
    except KoiAPIError as exc:
        return f"API ERROR: {exc}"
    return "OK: authenticated against the Koi API."


@mcp.tool()
def set_pov_meta(
    customer_name: str,
    prepared_by: str = "",
    pov_start: str = "",
    pov_end: str = "",
    tenant_label: str = "",
) -> str:
    """Set PoV metadata (customer name, author, PoV window, tenant label).

    Dates are free-form strings, ISO (YYYY-MM-DD) recommended.
    Merges into the existing report without touching collected data.
    """
    report = _load_report()
    report.meta = PoVMeta(
        customer_name=customer_name or report.meta.customer_name,
        prepared_by=prepared_by or report.meta.prepared_by,
        pov_start=pov_start or report.meta.pov_start,
        pov_end=pov_end or report.meta.pov_end,
        tenant_label=tenant_label or report.meta.tenant_label,
    )
    path = _save_report(report)
    return f"Meta saved for '{report.meta.customer_name}'. Report: {path}"


@mcp.tool()
def koi_collect(
    domains: list[str] | None = None,
    max_pages: int = 40,
    activity_days: int = 30,
) -> dict:
    """Collect PoV evidence from the Koi tenant and merge it into pov_report.json.

    domains: subset of [devices, groups, inventory, inventory_views, policies,
    lists, remediations, approvals, alerts, agent_activity]. Omit for all.
    max_pages: per-endpoint page cap (500 items/page). Lower it on big tenants
    for a faster first pass. activity_days: window for alerts and agent
    sessions (agent events are always capped at 24h by the API).

    Runs synchronously; a full collection on a large tenant can take several
    minutes because of the API rate limit (30 req/min/route). Prefer collecting
    one or two domains at a time. Failures in one domain do not stop the
    others; they are reported in `warnings`.
    """
    wanted = domains or list(DOMAINS)
    unknown = [d for d in wanted if d not in DOMAINS]
    if unknown:
        return {
            "error": f"Unknown domain(s): {unknown}",
            "valid_domains": list(DOMAINS),
        }

    report = _load_report()
    try:
        client = _client()
    except ValueError as exc:
        return {"error": f"NOT CONFIGURED: {exc}"}

    coll = PoVCollector(client, meta=report.meta, max_pages=max_pages)
    coll.report = report
    before_warnings = len(report.warnings)

    for name in DOMAINS:  # canonical order, filtered
        if name not in wanted:
            continue
        method = getattr(coll, DOMAINS[name])
        if name in ("alerts", "agent_activity"):
            coll._safe(name, method, activity_days)
        else:
            coll._safe(name, method)
        if name not in report.collected_domains:
            report.collected_domains.append(name)

    path = _save_report(report)
    return {
        "collected": [d for d in DOMAINS if d in wanted],
        "new_warnings": report.warnings[before_warnings:],
        "report_path": path,
        "summary": _summary(report),
    }


@mcp.tool()
def pov_status() -> dict:
    """Summarise the current pov_report.json: what was collected, key counts,
    warnings, and which domains are still missing. Use this to build the gap
    list before writing any deliverable."""
    report = _load_report()
    missing = [d for d in DOMAINS if d not in report.collected_domains]
    return {
        "report_path": str(_report_path()),
        "report_exists": _report_path().exists(),
        "collected_domains": report.collected_domains,
        "missing_domains": missing,
        "warnings": report.warnings,
        "summary": _summary(report),
    }


@mcp.tool()
def pov_report_json() -> dict:
    """Return the full aggregated PoV report as JSON. This is the single
    source of truth for writing the report and deck: every number in a
    deliverable must come from here or be a [[TO BE PROVIDED]] placeholder."""
    report = _load_report()
    data = asdict(report)
    data["derived"] = {
        "stage": report.stage,
        "high_and_critical": report.high_and_critical,
        "pending_analysis": report.pending_analysis,
    }
    return data


@mcp.tool()
def pov_reset(confirm: bool = False) -> str:
    """Delete the current pov_report.json to start a new PoV.
    Requires confirm=true. Ask the operator before calling with confirm."""
    if not confirm:
        return "Refused: call again with confirm=true after the operator agrees."
    p = _report_path()
    if p.exists():
        backup = p.with_suffix(".json.bak")
        p.replace(backup)
        return f"Reset done. Previous report kept at {backup}"
    return "Nothing to reset: no report file found."


def _summary(report: PoVReport) -> dict:
    return {
        "customer": report.meta.customer_name,
        "stage": report.stage,
        "devices_total": report.devices_total,
        "devices_active": report.devices_active,
        "items_total": report.items_total,
        "high_and_critical": report.high_and_critical,
        "ungoverned_high_risk": report.ungoverned_high_risk,
        "policies_enabled": report.policies_enabled,
        "remediations_total": report.remediations_total,
        "alerts_total": report.alerts_total,
        "agent_sessions_total": report.agent_sessions_total,
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
