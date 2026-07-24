"""
koi-pov-mcp server (stdio), multi-tenant.

Exposes Koi PoV collection as MCP tools for Claude Desktop / Claude Code.
Credentials never transit through the chat: tenants are added through the
koi_tenant_add tool (native dialog) or the `koi-pov-mcp tenants` CLI, stored
in the OS credential store; env vars (KOI_API_KEY[_<ALIAS>]) remain supported
and take precedence. Store changes apply immediately, no restart.

Per-tenant environment under <workdir>/<alias>/ :
  pov_report.json      current aggregated state (single source of truth)
  history/<ts>.json    snapshot after every sync, used for what's-new diffs
  deliverables/        where report/deck files for this tenant are written

Tenants never share state; a deliverable is always built from exactly one
tenant.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from . import secrets
from .client import KoiAuthError, KoiAPIError, KoiClient
from .collector import PoVCollector, PoVMeta, PoVReport
from .diffing import compute_whats_new

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

ADD_HINT = (
    "Add a tenant with the koi_tenant_add tool (opens a native dialog on the "
    "operator's machine; the key never transits through the conversation), "
    "or from a terminal with: koi-pov-mcp tenants add <alias>. Both apply "
    "immediately, no restart. Never paste keys in the conversation."
)


def _resolve_tenant(tenant: str) -> tuple[str, dict[str, str]] | dict:
    """Return (alias, creds) or an error dict ready to hand back to the model."""
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


# ---------------------------------------------------------------------- #
# Per-tenant state
# ---------------------------------------------------------------------- #


def _workdir() -> Path:
    return secrets.store_dir()


def _tenant_dir(alias: str) -> Path:
    d = _workdir() / alias
    (d / "history").mkdir(parents=True, exist_ok=True)
    (d / "deliverables").mkdir(parents=True, exist_ok=True)
    return d


def _report_path(alias: str) -> Path:
    path = _tenant_dir(alias) / "pov_report.json"
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


def _snapshot(alias: str, report: PoVReport) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = _tenant_dir(alias) / "history" / f"{ts}.json"
    data = asdict(report)
    data["derived_stage"] = report.stage
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    return ts


def _snapshots(alias: str) -> list[Path]:
    hist = _tenant_dir(alias) / "history"
    return sorted(hist.glob("*.json"))


# ---------------------------------------------------------------------- #
# Collection core (shared by koi_collect and koi_sync_all)
# ---------------------------------------------------------------------- #


def _collect_one(
    alias: str,
    creds: dict[str, str],
    wanted: list[str],
    max_pages: int,
    activity_days: int,
) -> dict:
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
    """Add or update a Koi tenant from the Claude interface. Creates the
    tenant's dedicated environment (data, history, deliverables directories).

    Opens a native dialog window on the operator's machine where they paste
    the API key (masked input). The key goes straight from that window to the
    OS credential store; it never transits through the conversation, and this
    tool never returns it. Connectivity is tested automatically on success.

    Use this when the operator says e.g. "add the acme tenant" in any
    language. Ask for the alias if they did not give one. Tell them to look
    for the dialog window (it may open behind other windows). The dialog
    auto-cancels after 3 minutes without input.
    """
    alias = (alias or "").strip().lower()
    if not secrets.ALIAS_RE.match(alias):
        return (
            f"Invalid alias '{alias}': lowercase letters, digits, '-', '_', "
            "max 40 chars, must start alphanumeric."
        )

    python = sys.executable
    if os.name == "nt":
        pythonw = Path(python).with_name("pythonw.exe")
        if pythonw.exists():
            python = str(pythonw)

    try:
        proc = subprocess.run(
            [python, "-m", "koi_pov_mcp.gui", alias, base_url],
            capture_output=True,
            text=True,
            timeout=200,
        )
    except subprocess.TimeoutExpired:
        return "Dialog timed out with no input. Nothing was saved."

    if proc.returncode == 0:
        _tenant_dir(alias)  # provision the dedicated environment
        return f"Tenant '{alias}' saved in the OS credential store. " + _ping_alias(alias)
    if proc.returncode == 2:
        return "Cancelled by the operator. Nothing was saved."
    if proc.returncode == 3:
        return (
            "No graphical dialog available on this system (tkinter missing). "
            f"Fallback: run in a terminal: koi-pov-mcp tenants add {alias}"
        )
    detail = (proc.stderr or "").strip()
    return f"Dialog failed (exit {proc.returncode}). {detail or 'Nothing was saved.'}"


@mcp.tool()
def koi_tenants() -> dict:
    """List the configured Koi tenants and whether each already has a
    collected report. Call this first when the operator manages several PoVs,
    and ask which tenant to work on if more than one is configured. Keys
    themselves are never returned. To add a tenant from the Claude interface,
    use the koi_tenant_add tool (native dialog, key never in chat)."""
    registry = secrets.all_tenants()
    tenants = []
    for alias in sorted(registry):
        report_file = _workdir() / alias / "pov_report.json"
        entry = {
            "alias": alias,
            "source": registry[alias]["source"],
            "has_report": report_file.exists(),
            "snapshots": len(_snapshots(alias)) if report_file.exists() else 0,
        }
        if report_file.exists():
            try:
                entry["customer"] = PoVReport.from_json(str(report_file)).meta.customer_name
            except Exception:  # noqa: BLE001 - listing must not fail on one bad file
                entry["customer"] = "(unreadable report)"
        tenants.append(entry)
    return {"tenants": tenants, "count": len(tenants), "note": ADD_HINT}


@mcp.tool()
def koi_ping(tenant: str = "default") -> str:
    """Check Koi API connectivity and key validity for one tenant.

    Call this before any collection on that tenant. If it fails, offer to run
    koi_tenant_add (re-adding overwrites the key). Never ask for the key in
    chat.
    """
    resolved = _resolve_tenant(tenant)
    if isinstance(resolved, dict):
        return resolved.get("error", "unknown error") + (
            f" Configured: {resolved['configured_tenants']}"
            if "configured_tenants" in resolved else ""
        )
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
    """Sync one Koi tenant: collect PoV evidence and merge it into that
    tenant's pov_report.json, then snapshot it for what's-new diffs.

    Use when the operator says e.g. "sync tenant xyz" in any language.
    tenant: alias from koi_tenants. domains: subset of [devices, groups,
    inventory, inventory_views, policies, lists, remediations, approvals,
    alerts, agent_activity]; omit for all. max_pages: per-endpoint page cap
    (500 items/page); lower it on big tenants for a faster first pass.
    activity_days: window for alerts and agent sessions (agent events are
    always capped at 24h by the API).

    Runs synchronously; a full collection on a large tenant can take several
    minutes because of the API rate limit (30 req/min/route). Failures in one
    domain do not stop the others; they are reported in `warnings`.
    """
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
    """Sync every configured tenant, sequentially. Use when the operator says
    e.g. "sync all my Koi tenants" in any language.

    Each tenant is collected and snapshotted independently; a failure on one
    tenant does not stop the others. With several tenants this can take a
    while (rate limit is per tenant key, but the loop is sequential); consider
    domains=[...] or a lower max_pages for a quick refresh. Warn the operator
    about the duration before launching a full sync of many tenants.
    """
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
            results[alias] = _collect_one(
                alias, registry[alias], wanted, max_pages, activity_days
            )
        except Exception as exc:  # noqa: BLE001 - one tenant must not sink the rest
            results[alias] = {"tenant": alias, "error": f"{type(exc).__name__}: {exc}"}
    return {
        "synced": [a for a, r in results.items() if "error" not in r],
        "failed": {a: r["error"] for a, r in results.items() if "error" in r},
        "results": results,
    }


@mcp.tool()
def koi_whats_new(tenant: str = "default", since: str = "") -> dict:
    """What changed on one tenant since a previous sync: the raw material for
    a PoV follow-up meeting. Use when the operator asks e.g. "what's new on
    tenant abcd" or "prepare my next follow-up" in any language.

    Compares the latest snapshot against a baseline: the snapshot taken just
    before the most recent sync, or, if `since` is given (ISO date or
    YYYYMMDD), the last snapshot at or before that date. Returns deltas and
    newly appeared items only; unchanged figures are omitted on purpose and
    must not be presented as news. If there is no baseline yet (first sync),
    say so: everything is new and no delta story exists.
    """
    resolved = _resolve_tenant(tenant)
    if isinstance(resolved, dict):
        return resolved
    alias, _ = resolved

    snaps = _snapshots(alias)
    if not snaps:
        return {
            "tenant": alias,
            "error": "No snapshot yet. Run koi_collect first (each sync creates one).",
        }

    current_path = snaps[-1]
    baseline_path: Path | None = None
    if since:
        stamp = since.replace("-", "").replace(":", "").replace("T", "")[:8]
        candidates = [s for s in snaps[:-1] if s.stem[:8] <= stamp]
        baseline_path = candidates[-1] if candidates else None
        if baseline_path is None:
            return {
                "tenant": alias,
                "error": f"No snapshot at or before '{since}'. "
                         f"Oldest is {snaps[0].stem}.",
                "available_snapshots": [s.stem for s in snaps],
            }
    elif len(snaps) >= 2:
        baseline_path = snaps[-2]

    if baseline_path is None:
        return {
            "tenant": alias,
            "baseline": None,
            "note": (
                "First collection: no baseline to diff against. Everything in "
                "pov_report_json is 'new'; do not present deltas."
            ),
        }

    with open(current_path, encoding="utf-8") as fh:
        current = json.load(fh)
    with open(baseline_path, encoding="utf-8") as fh:
        baseline = json.load(fh)

    return {
        "tenant": alias,
        "baseline": baseline_path.stem,
        "current": current_path.stem,
        "changes": compute_whats_new(current, baseline),
        "available_snapshots": [s.stem for s in snaps],
    }


@mcp.tool()
def pov_status(tenant: str = "default") -> dict:
    """State of play for one tenant: what was collected, key counts, warnings,
    missing domains, snapshot history, and where deliverables go. Use when
    the operator asks for "an overview / etat des lieux of tenant xyz", and
    to build the gap list before writing any deliverable."""
    resolved = _resolve_tenant(tenant)
    if isinstance(resolved, dict):
        return resolved
    alias, _ = resolved
    report = _load_report(alias)
    missing = [d for d in DOMAINS if d not in report.collected_domains]
    snaps = _snapshots(alias)
    return {
        "tenant": alias,
        "report_path": str(_report_path(alias)),
        "report_exists": _report_path(alias).exists(),
        "deliverables_path": str(_tenant_dir(alias) / "deliverables"),
        "snapshots": [s.stem for s in snaps[-10:]],
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
    """Delete one tenant's pov_report.json and snapshot history to start a new
    PoV on that tenant. Requires confirm=true. Ask the operator before calling
    with confirm. Deliverables and other tenants are untouched."""
    resolved = _resolve_tenant(tenant)
    if isinstance(resolved, dict):
        return resolved.get("error", "unknown error")
    alias, _ = resolved
    if not confirm:
        return "Refused: call again with confirm=true after the operator agrees."
    p = _report_path(alias)
    moved = []
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


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
