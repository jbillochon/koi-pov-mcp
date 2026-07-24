"""
koi-pov-mcp server (stdio), multi-tenant.

Exposes Koi PoV collection as MCP tools for Claude Desktop / Claude Code.
Credentials come from the environment, never from the chat:

  KOI_API_KEY               -> tenant alias "default"
  KOI_API_KEY_<ALIAS>       -> tenant alias "<alias>" (lowercased)
  KOI_BASE_URL[_<ALIAS>]    -> optional per-tenant base URL override

Example env block for an SE running several PoVs in parallel:

  "env": {
    "KOI_API_KEY_ACME":   "...",
    "KOI_API_KEY_GLOBEX": "..."
  }

State: one pov_report.json per tenant, under <workdir>/<alias>/
(KOI_POV_WORKDIR, or the OS user-data dir by default). Collection domains
merge into it incrementally, so you can collect in several passes. Tenants
never share state; a deliverable is always built from exactly one tenant.
"""

from __future__ import annotations

import os
import re
from dataclasses import asdict
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from platformdirs import user_data_dir

from .client import KoiAuthError, KoiAPIError, KoiClient
from .collector import PoVCollector, PoVMeta, PoVReport

APP_NAME = "koi-pov-mcp"
KEY_PREFIX = "KOI_API_KEY_"
ALIAS_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")

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


# ---------------------------------------------------------------------- #
# Tenant registry (from environment)
# ---------------------------------------------------------------------- #


def _tenants() -> dict[str, dict[str, str]]:
    """Alias -> {key, base_url} discovered from the environment."""
    found: dict[str, dict[str, str]] = {}
    if os.environ.get("KOI_API_KEY"):
        found["default"] = {
            "key": os.environ["KOI_API_KEY"],
            "base_url": os.environ.get("KOI_BASE_URL", ""),
        }
    for name, value in os.environ.items():
        if not name.startswith(KEY_PREFIX) or not value:
            continue
        alias = name[len(KEY_PREFIX):].lower()
        if not ALIAS_RE.match(alias):
            continue
        found[alias] = {
            "key": value,
            "base_url": os.environ.get(f"KOI_BASE_URL_{alias.upper()}", "")
            or os.environ.get("KOI_BASE_URL", ""),
        }
    return found


def _resolve_tenant(tenant: str) -> tuple[str, dict[str, str]] | dict:
    """Return (alias, creds) or an error dict ready to hand back to the model."""
    alias = (tenant or "default").strip().lower()
    if not ALIAS_RE.match(alias):
        return {"error": f"Invalid tenant alias '{tenant}'."}
    registry = _tenants()
    if not registry:
        return {
            "error": (
                "NOT CONFIGURED: no Koi API key found. Set KOI_API_KEY "
                "(single tenant) or KOI_API_KEY_<ALIAS> entries (multi-tenant) "
                "in the MCP server env block, then restart Claude."
            )
        }
    if alias not in registry:
        return {
            "error": f"Unknown tenant '{alias}'.",
            "configured_tenants": sorted(registry),
        }
    return alias, registry[alias]


def _client_for(creds: dict[str, str]) -> KoiClient:
    return KoiClient(
        api_key=creds["key"],
        base_url=creds["base_url"] or None,
    )


# ---------------------------------------------------------------------- #
# Per-tenant state
# ---------------------------------------------------------------------- #


def _workdir() -> Path:
    p = Path(os.environ.get("KOI_POV_WORKDIR") or user_data_dir(APP_NAME))
    p.mkdir(parents=True, exist_ok=True)
    return p


def _report_path(alias: str) -> Path:
    tenant_dir = _workdir() / alias
    tenant_dir.mkdir(parents=True, exist_ok=True)
    path = tenant_dir / "pov_report.json"
    # One-time migration from the single-tenant layout (v0.1)
    if alias == "default" and not path.exists():
        legacy = _workdir() / "pov_report.json"
        if legacy.exists():
            legacy.replace(path)
    return path


def _load_report(alias: str) -> PoVReport:
    p = _report_path(alias)
    if p.exists():
        return PoVReport.from_json(str(p))
    return PoVReport()


def _save_report(alias: str, report: PoVReport) -> str:
    path = _report_path(alias)
    report.to_json(str(path))
    return str(path)


# ---------------------------------------------------------------------- #
# Tools
# ---------------------------------------------------------------------- #


@mcp.tool()
def koi_tenants() -> dict:
    """List the Koi tenants configured in the server environment, and whether
    each already has a collected report. Call this first when the operator
    manages several PoVs, and ask which tenant to work on if more than one is
    configured. Keys themselves are never returned."""
    registry = _tenants()
    tenants = []
    for alias in sorted(registry):
        report_file = _workdir() / alias / "pov_report.json"
        entry = {"alias": alias, "has_report": report_file.exists()}
        if report_file.exists():
            try:
                entry["customer"] = PoVReport.from_json(str(report_file)).meta.customer_name
            except Exception:  # noqa: BLE001 - listing must not fail on one bad file
                entry["customer"] = "(unreadable report)"
        tenants.append(entry)
    return {
        "tenants": tenants,
        "count": len(tenants),
        "note": (
            "Add tenants with KOI_API_KEY_<ALIAS> entries in the MCP server "
            "env block. Never paste keys in the conversation."
        ),
    }


@mcp.tool()
def koi_ping(tenant: str = "default") -> str:
    """Check Koi API connectivity and key validity for one tenant.

    Call this before any collection on that tenant. If it fails with an auth
    error, the operator must fix the corresponding KOI_API_KEY[_<ALIAS>] entry
    in the MCP server environment. Never ask for the key in chat.
    """
    resolved = _resolve_tenant(tenant)
    if isinstance(resolved, dict):
        return resolved.get("error", "unknown error") + (
            f" Configured: {resolved['configured_tenants']}"
            if "configured_tenants" in resolved else ""
        )
    alias, creds = resolved
    try:
        _client_for(creds).ping()
    except KoiAuthError:
        return (
            f"AUTH FAILED for tenant '{alias}': the API key was rejected (401). "
            "Fix the key in the MCP server env and restart Claude."
        )
    except KoiAPIError as exc:
        return f"API ERROR for tenant '{alias}': {exc}"
    return f"OK: authenticated against the Koi API for tenant '{alias}'."


@mcp.tool()
def set_pov_meta(
    customer_name: str,
    tenant: str = "default",
    prepared_by: str = "",
    pov_start: str = "",
    pov_end: str = "",
    tenant_label: str = "",
) -> str:
    """Set PoV metadata (customer name, author, PoV window) for one tenant.

    Dates are free-form strings, ISO (YYYY-MM-DD) recommended.
    Merges into the tenant's existing report without touching collected data.
    """
    resolved = _resolve_tenant(tenant)
    if isinstance(resolved, dict):
        return resolved.get("error", "unknown error")
    alias, _ = resolved
    report = _load_report(alias)
    report.meta = PoVMeta(
        customer_name=customer_name or report.meta.customer_name,
        prepared_by=prepared_by or report.meta.prepared_by,
        pov_start=pov_start or report.meta.pov_start,
        pov_end=pov_end or report.meta.pov_end,
        tenant_label=tenant_label or report.meta.tenant_label or alias,
    )
    path = _save_report(alias, report)
    return f"Meta saved for '{report.meta.customer_name}' (tenant '{alias}'). Report: {path}"


@mcp.tool()
def koi_collect(
    tenant: str = "default",
    domains: list[str] | None = None,
    max_pages: int = 40,
    activity_days: int = 30,
) -> dict:
    """Collect PoV evidence from one Koi tenant and merge it into that
    tenant's pov_report.json.

    tenant: alias from koi_tenants. domains: subset of [devices, groups,
    inventory, inventory_views, policies, lists, remediations, approvals,
    alerts, agent_activity]; omit for all. max_pages: per-endpoint page cap
    (500 items/page); lower it on big tenants for a faster first pass.
    activity_days: window for alerts and agent sessions (agent events are
    always capped at 24h by the API).

    Runs synchronously; a full collection on a large tenant can take several
    minutes because of the API rate limit (30 req/min/route). Prefer
    collecting one or two domains at a time. Failures in one domain do not
    stop the others; they are reported in `warnings`.
    """
    resolved = _resolve_tenant(tenant)
    if isinstance(resolved, dict):
        return resolved
    alias, creds = resolved

    wanted = domains or list(DOMAINS)
    unknown = [d for d in wanted if d not in DOMAINS]
    if unknown:
        return {
            "error": f"Unknown domain(s): {unknown}",
            "valid_domains": list(DOMAINS),
        }

    report = _load_report(alias)
    coll = PoVCollector(_client_for(creds), meta=report.meta, max_pages=max_pages)
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

    path = _save_report(alias, report)
    return {
        "tenant": alias,
        "collected": [d for d in DOMAINS if d in wanted],
        "new_warnings": report.warnings[before_warnings:],
        "report_path": path,
        "summary": _summary(alias, report),
    }


@mcp.tool()
def pov_status(tenant: str = "default") -> dict:
    """Summarise one tenant's pov_report.json: what was collected, key counts,
    warnings, and which domains are still missing. Use this to build the gap
    list before writing any deliverable."""
    resolved = _resolve_tenant(tenant)
    if isinstance(resolved, dict):
        return resolved
    alias, _ = resolved
    report = _load_report(alias)
    missing = [d for d in DOMAINS if d not in report.collected_domains]
    return {
        "tenant": alias,
        "report_path": str(_report_path(alias)),
        "report_exists": _report_path(alias).exists(),
        "collected_domains": report.collected_domains,
        "missing_domains": missing,
        "warnings": report.warnings,
        "summary": _summary(alias, report),
    }


@mcp.tool()
def pov_report_json(tenant: str = "default") -> dict:
    """Return one tenant's full aggregated PoV report as JSON. This is the
    single source of truth for that tenant's deliverables: every number must
    come from here or be a [[TO BE PROVIDED]] placeholder. Never mix data
    from two tenants in one deliverable."""
    resolved = _resolve_tenant(tenant)
    if isinstance(resolved, dict):
        return resolved
    alias, _ = resolved
    report = _load_report(alias)
    data = asdict(report)
    data["tenant"] = alias
    data["derived"] = {
        "stage": report.stage,
        "high_and_critical": report.high_and_critical,
        "pending_analysis": report.pending_analysis,
    }
    return data


@mcp.tool()
def pov_reset(tenant: str = "default", confirm: bool = False) -> str:
    """Delete one tenant's pov_report.json to start a new PoV on that tenant.
    Requires confirm=true. Ask the operator before calling with confirm.
    Other tenants are untouched."""
    resolved = _resolve_tenant(tenant)
    if isinstance(resolved, dict):
        return resolved.get("error", "unknown error")
    alias, _ = resolved
    if not confirm:
        return "Refused: call again with confirm=true after the operator agrees."
    p = _report_path(alias)
    if p.exists():
        backup = p.with_suffix(".json.bak")
        p.replace(backup)
        return f"Reset done for tenant '{alias}'. Previous report kept at {backup}"
    return f"Nothing to reset: no report file for tenant '{alias}'."


def _summary(alias: str, report: PoVReport) -> dict:
    return {
        "tenant": alias,
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
