"""
koi-pov-mcp server (stdio), multi-tenant.

See module docstrings of secrets/dialog/ti_tool/render_tool/xsiam_tool for
details. Credentials never transit through the chat; per-tenant environment
under <workdir>/<alias>/: pov_report.json, history/, enrichment.json,
xsiam_correlation.json, deliverables/.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from . import dialog, render_tool, secrets, ti_tool, xsiam_tool
from .client import KoiAuthError, KoiAPIError, KoiClient
from .collector import PoVCollector, PoVMeta, PoVReport
from .diffing import compute_whats_new

mcp = FastMCP("koi-pov")

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

ADD_HINT = (
    "Add a tenant with the koi_tenant_add tool: it opens a credential page in "
    "the operator's browser (the key goes straight to the OS credential store "
    "and never transits through the conversation). Terminal alternative: "
    "koi-pov-mcp tenants add <alias>. Both apply immediately, no restart. "
    "Never paste keys in the conversation."
)


def _cli_hint(alias: str) -> str:
    return (
        f"koi-pov-mcp tenants add {alias} --test "
        r"(Windows: %USERPROFILE%\.koi-pov-mcp\venv\Scripts\koi-pov-mcp.exe)"
    )


def _resolve_tenant(tenant: str) -> tuple[str, dict[str, str]] | dict:
    alias = (tenant or "default").strip().lower()
    if not secrets.ALIAS_RE.match(alias):
        return {"error": f"Invalid tenant alias '{tenant}'."}
    registry = secrets.all_tenants()
    if not registry:
        return {"error": f"NOT CONFIGURED: no Koi tenant found. {ADD_HINT}"}
    if alias not in registry:
        return {
            "error": f"Unknown tenant '{alias}'. {ADD_HINT}",
            "configured_tenants": sorted(registry),
        }
    return alias, registry[alias]


def _client_for(creds: dict[str, str]) -> KoiClient:
    return KoiClient(api_key=creds["key"], base_url=creds["base_url"] or None)


def _ping_alias(alias: str) -> str:
    registry = secrets.all_tenants()
    if alias not in registry:
        return f"Unknown tenant '{alias}'."
    try:
        _client_for(registry[alias]).ping()
    except KoiAuthError:
        return (
            f"AUTH FAILED for tenant '{alias}': the API key was rejected (401). "
            f"Re-add it (koi_tenant_add or the CLI) to overwrite."
        )
    except KoiAPIError as exc:
        return f"API ERROR for tenant '{alias}': {exc}"
    return f"OK: authenticated against the Koi API for tenant '{alias}'."


def _workdir() -> Path:
    return secrets.store_dir()


def _tenant_dir(alias: str) -> Path:
    d = _workdir() / alias
    (d / "history").mkdir(parents=True, exist_ok=True)
    (d / "deliverables").mkdir(parents=True, exist_ok=True)
    return d


def _report_path(alias: str) -> Path:
    path = _tenant_dir(alias) / "pov_report.json"
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


def _snapshot(alias: str, report: PoVReport) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = _tenant_dir(alias) / "history" / f"{ts}.json"
    data = asdict(report)
    data["derived_stage"] = report.stage
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    return ts


def _snapshots(alias: str) -> list[Path]:
    return sorted((_tenant_dir(alias) / "history").glob("*.json"))


def _report_json(alias: str) -> dict:
    """Aggregated report + derived + enrichment + xsiam. Shared by the
    pov_report_json tool and render_deliverables."""
    report = _load_report(alias)
    data = asdict(report)
    data["tenant"] = alias
    data["derived"] = {
        "stage": report.stage,
        "high_and_critical": report.high_and_critical,
        "pending_analysis": report.pending_analysis,
    }
    for name, key in (("enrichment.json", "enrichment"),
                      ("xsiam_correlation.json", "xsiam")):
        p = _tenant_dir(alias) / name
        if p.exists():
            try:
                with open(p, encoding="utf-8") as fh:
                    data[key] = json.load(fh)
            except (OSError, json.JSONDecodeError):
                data[key] = {"errors": [f"{name} unreadable"]}
    return data


def _collect_one(alias, creds, wanted, max_pages, activity_days) -> dict:
    report = _load_report(alias)
    coll = PoVCollector(_client_for(creds), meta=report.meta, max_pages=max_pages)
    coll.report = report
    before_warnings = len(report.warnings)
    for name in DOMAINS:
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
    snap_ts = _snapshot(alias, report)
    return {
        "tenant": alias,
        "collected": [d for d in DOMAINS if d in wanted],
        "new_warnings": report.warnings[before_warnings:],
        "report_path": path,
        "snapshot": snap_ts,
        "summary": _summary(alias, report),
    }


# ---------------------------------------------------------------------- #
# Tools
# ---------------------------------------------------------------------- #


@mcp.tool()
def koi_tenant_add(alias: str, base_url: str = "") -> str:
    """Open a credential page so the operator can add or update a Koi tenant.

    The page runs locally in their browser; the API key goes straight to the
    OS credential store. It never transits through the conversation and this
    tool never returns it.

    This returns IMMEDIATELY with the page URL: it does NOT wait for the
    operator to fill the form, and nothing is saved yet when it returns.
    Relay the URL verbatim (their browser may not have opened by itself),
    say the page expires in 5 minutes, and stop there. When the operator
    confirms they saved the key, call koi_ping(alias) to verify. Never
    announce the tenant as added before that ping succeeds.

    Use when the operator says e.g. "add a tenant" in any language; ask for
    a short alias first if they did not give one.
    """
    alias = (alias or "").strip().lower()
    if not secrets.ALIAS_RE.match(alias):
        return (f"Invalid alias '{alias}': lowercase letters, digits, '-', '_', "
                "max 40 chars, must start alphanumeric.")

    result = dialog.launch("koi", alias, base_url)
    if result["error"]:
        return (f"Could not open the credential page: {result['error']}. "
                f"Terminal fallback: {_cli_hint(alias)}")
    _tenant_dir(alias)  # provision the environment now; the key follows
    return (
        f"Credential page opened for tenant '{alias}'. If no browser tab "
        f"appeared, open this link: {result['url']} (expires in 5 minutes). "
        "Nothing is saved until the form is submitted; tell me once it is "
        "done and I will verify the connection."
    )


@mcp.tool()
def koi_tenants() -> dict:
    """List configured Koi tenants: alias, source, whether a report exists,
    snapshot count, and whether an XSIAM tenant is linked (xsiam_linked).
    Keys are never returned. Ask which tenant to work on if more than one."""
    registry = secrets.all_tenants()
    xsiam_linked = secrets.xsiam_list()
    tenants = []
    for alias in sorted(registry):
        report_file = _workdir() / alias / "pov_report.json"
        entry = {
            "alias": alias,
            "source": registry[alias]["source"],
            "has_report": report_file.exists(),
            "snapshots": len(_snapshots(alias)) if report_file.exists() else 0,
            "xsiam_linked": alias in xsiam_linked,
        }
        if report_file.exists():
            try:
                entry["customer"] = PoVReport.from_json(str(report_file)).meta.customer_name
            except Exception:  # noqa: BLE001
                entry["customer"] = "(unreadable report)"
        tenants.append(entry)
    return {"tenants": tenants, "count": len(tenants), "note": ADD_HINT}


@mcp.tool()
def koi_ping(tenant: str = "default") -> str:
    """Check Koi API connectivity and key validity for one tenant. Also the
    way to confirm a koi_tenant_add actually completed. If it fails, offer
    koi_tenant_add again (re-adding overwrites the key). Never ask for the
    key in chat."""
    resolved = _resolve_tenant(tenant)
    if isinstance(resolved, dict):
        return resolved.get("error", "unknown error") + (
            f" Configured: {resolved['configured_tenants']}"
            if "configured_tenants" in resolved else "")
    alias, _ = resolved
    return _ping_alias(alias)


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
    Dates free-form, ISO recommended. Merges without touching collected data."""
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
    """Sync one Koi tenant (collect + snapshot). Use for "sync tenant xyz" in
    any language. domains subset of [devices, groups, inventory,
    inventory_views, policies, lists, remediations, approvals, alerts,
    agent_activity]; omit for all. Synchronous; rate limit 30 req/min/route,
    so prefer one or two domains at a time on large tenants (a full sync can
    exceed the host's tool timeout). Domain failures land in `warnings`
    without stopping the others."""
    resolved = _resolve_tenant(tenant)
    if isinstance(resolved, dict):
        return resolved
    alias, creds = resolved
    wanted = domains or list(DOMAINS)
    unknown = [d for d in wanted if d not in DOMAINS]
    if unknown:
        return {"error": f"Unknown domain(s): {unknown}", "valid_domains": list(DOMAINS)}
    return _collect_one(alias, creds, wanted, max_pages, activity_days)


@mcp.tool()
def koi_sync_all(
    domains: list[str] | None = None,
    max_pages: int = 40,
    activity_days: int = 30,
) -> dict:
    """Sync every configured tenant sequentially ("sync all my Koi tenants").
    Independent per tenant; one failure does not stop the rest. With several
    tenants this can exceed the host's tool timeout: warn the operator, and
    prefer scoped domains or per-tenant koi_collect calls when in doubt."""
    registry = secrets.all_tenants()
    if not registry:
        return {"error": f"NOT CONFIGURED: no Koi tenant found. {ADD_HINT}"}
    wanted = domains or list(DOMAINS)
    unknown = [d for d in wanted if d not in DOMAINS]
    if unknown:
        return {"error": f"Unknown domain(s): {unknown}", "valid_domains": list(DOMAINS)}
    results: dict[str, dict] = {}
    for alias in sorted(registry):
        try:
            results[alias] = _collect_one(alias, registry[alias], wanted,
                                          max_pages, activity_days)
        except Exception as exc:  # noqa: BLE001
            results[alias] = {"tenant": alias, "error": f"{type(exc).__name__}: {exc}"}
    return {
        "synced": [a for a, r in results.items() if "error" not in r],
        "failed": {a: r["error"] for a, r in results.items() if "error" in r},
        "results": results,
    }


@mcp.tool()
def koi_whats_new(tenant: str = "default", since: str = "") -> dict:
    """What changed since a previous sync: follow-up meeting material.
    Baseline = previous snapshot, or last snapshot at/before `since`
    (ISO/YYYYMMDD). Deltas and new items only; unchanged figures are omitted
    and must not be presented as news. baseline null = first sync, no delta
    story."""
    resolved = _resolve_tenant(tenant)
    if isinstance(resolved, dict):
        return resolved
    alias, _ = resolved
    snaps = _snapshots(alias)
    if not snaps:
        return {"tenant": alias,
                "error": "No snapshot yet. Run koi_collect first (each sync creates one)."}
    current_path = snaps[-1]
    baseline_path: Path | None = None
    if since:
        stamp = since.replace("-", "").replace(":", "").replace("T", "")[:8]
        candidates = [s for s in snaps[:-1] if s.stem[:8] <= stamp]
        baseline_path = candidates[-1] if candidates else None
        if baseline_path is None:
            return {"tenant": alias,
                    "error": f"No snapshot at or before '{since}'. Oldest is {snaps[0].stem}.",
                    "available_snapshots": [s.stem for s in snaps]}
    elif len(snaps) >= 2:
        baseline_path = snaps[-2]
    if baseline_path is None:
        return {"tenant": alias, "baseline": None,
                "note": ("First collection: no baseline to diff against. Everything in "
                         "pov_report_json is 'new'; do not present deltas.")}
    with open(current_path, encoding="utf-8") as fh:
        current = json.load(fh)
    with open(baseline_path, encoding="utf-8") as fh:
        baseline = json.load(fh)
    return {"tenant": alias, "baseline": baseline_path.stem,
            "current": current_path.stem,
            "changes": compute_whats_new(current, baseline),
            "available_snapshots": [s.stem for s in snaps]}


@mcp.tool()
def pov_status(tenant: str = "default") -> dict:
    """State of play for one tenant ("etat des lieux"): collected vs missing
    domains, warnings, snapshots, enrichment and XSIAM presence, deliverables
    path. Feeds the mandatory gap list."""
    resolved = _resolve_tenant(tenant)
    if isinstance(resolved, dict):
        return resolved
    alias, _ = resolved
    report = _load_report(alias)
    return {
        "tenant": alias,
        "report_path": str(_report_path(alias)),
        "report_exists": _report_path(alias).exists(),
        "deliverables_path": str(_tenant_dir(alias) / "deliverables"),
        "enrichment_exists": (_tenant_dir(alias) / "enrichment.json").exists(),
        "xsiam_correlation_exists": (_tenant_dir(alias) / "xsiam_correlation.json").exists(),
        "xsiam_linked": secrets.xsiam_get(alias) is not None,
        "snapshots": [s.stem for s in _snapshots(alias)[-10:]],
        "collected_domains": report.collected_domains,
        "missing_domains": [d for d in DOMAINS if d not in report.collected_domains],
        "warnings": report.warnings,
        "summary": _summary(alias, report),
    }


@mcp.tool()
def pov_report_json(tenant: str = "default") -> dict:
    """Full aggregated report for one tenant, including 'enrichment' (TI) and
    'xsiam' (correlation) when present. Single source of truth: every number
    in a deliverable comes from here or stays a [[TO BE PROVIDED]]
    placeholder. Never mix tenants."""
    resolved = _resolve_tenant(tenant)
    if isinstance(resolved, dict):
        return resolved
    alias, _ = resolved
    return _report_json(alias)


@mcp.tool()
def pov_reset(tenant: str = "default", confirm: bool = False) -> str:
    """Start a new PoV on one tenant: archives pov_report.json, snapshot
    history, enrichment and XSIAM correlation. Requires confirm=true after
    asking the operator. Deliverables and other tenants untouched."""
    resolved = _resolve_tenant(tenant)
    if isinstance(resolved, dict):
        return resolved.get("error", "unknown error")
    alias, _ = resolved
    if not confirm:
        return "Refused: call again with confirm=true after the operator agrees."
    moved = []
    for name in ("pov_report.json", "enrichment.json", "xsiam_correlation.json"):
        p = _tenant_dir(alias) / name
        if p.exists():
            backup = p.with_suffix(".json.bak")
            p.replace(backup)
            moved.append(str(backup))
    hist = _tenant_dir(alias) / "history"
    archive = _tenant_dir(alias) / "history_archive"
    if any(hist.glob("*.json")):
        archive.mkdir(exist_ok=True)
        for s in hist.glob("*.json"):
            s.replace(archive / s.name)
        moved.append(str(archive))
    if moved:
        return f"Reset done for tenant '{alias}'. Previous data kept at: {', '.join(moved)}"
    return f"Nothing to reset: no data for tenant '{alias}'."


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


# Optional-capability tools
ti_tool.register(mcp, _resolve_tenant, _load_report, _tenant_dir)
render_tool.register(mcp, _resolve_tenant, _report_json, _tenant_dir)
xsiam_tool.register(mcp, _resolve_tenant, _tenant_dir)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
