"""
Diff two PoV report snapshots into "what's new" material for a follow-up
meeting: numeric deltas plus newly appeared items. Additions and progress
only; this is meeting-prep material, not an audit log.

Both inputs are plain dicts (dataclasses.asdict of PoVReport).
"""

from __future__ import annotations

from typing import Any


def _item_key(it: dict) -> tuple:
    return (it.get("name"), it.get("version"), it.get("marketplace"))


def _new_items(current: list[dict], baseline: list[dict], limit: int = 10) -> list[dict]:
    seen = {_item_key(b) for b in baseline or []}
    return [i for i in current or [] if _item_key(i) not in seen][:limit]


def _delta(current: dict, baseline: dict, field: str) -> int:
    return int(current.get(field) or 0) - int(baseline.get(field) or 0)


def _dict_delta(current: dict | None, baseline: dict | None) -> dict[str, int]:
    cur, base = current or {}, baseline or {}
    out = {}
    for k in set(cur) | set(base):
        d = int(cur.get(k) or 0) - int(base.get(k) or 0)
        if d:
            out[k] = d
    return out


def compute_whats_new(current: dict, baseline: dict) -> dict[str, Any]:
    """Return the changes between two report snapshots.

    Every value here is a *difference*; zero-deltas are omitted so the model
    is not tempted to present unchanged figures as news.
    """
    base_names = {p.get("name") for p in baseline.get("policies") or []}
    new_policies = [
        p.get("name") for p in current.get("policies") or []
        if p.get("name") not in base_names
    ]
    base_rt = {p.get("name") for p in baseline.get("runtime_policies") or []}
    new_runtime_policies = [
        p.get("name") for p in current.get("runtime_policies") or []
        if p.get("name") not in base_rt
    ]

    base_remediated = {
        (r.get("name"), r.get("hostname")) for r in baseline.get("remediated_items") or []
    }
    new_remediated = [
        r for r in current.get("remediated_items") or []
        if (r.get("name"), r.get("hostname")) not in base_remediated
    ]

    base_blocked = {
        (e.get("agent"), e.get("host"), e.get("timestamp"))
        for e in baseline.get("agent_blocked_examples") or []
    }
    new_blocked = [
        e for e in current.get("agent_blocked_examples") or []
        if (e.get("agent"), e.get("host"), e.get("timestamp")) not in base_blocked
    ]

    out: dict[str, Any] = {
        "coverage": {
            "devices_total_delta": _delta(current, baseline, "devices_total"),
            "devices_active_delta": _delta(current, baseline, "devices_active"),
        },
        "discovery": {
            "items_total_delta": _delta(current, baseline, "items_total"),
            "items_by_risk_delta": _dict_delta(
                current.get("items_by_risk"), baseline.get("items_by_risk")
            ),
            "new_top_risk_items": _new_items(
                current.get("top_risk_items"), baseline.get("top_risk_items")
            ),
            "new_malicious_items": _new_items(
                current.get("malicious_items"), baseline.get("malicious_items")
            ),
        },
        "exposure": {
            "ungoverned_high_risk_delta": _delta(current, baseline, "ungoverned_high_risk"),
            "exposed_installs_delta": _delta(current, baseline, "exposed_installs"),
            "new_action_candidates": _new_items(
                current.get("action_candidates"), baseline.get("action_candidates")
            ),
        },
        "governance": {
            "policies_enabled_delta": _delta(current, baseline, "policies_enabled"),
            "new_policies": new_policies,
            "new_runtime_policies": new_runtime_policies,
            "allowlist_delta": _delta(current, baseline, "allowlist_count"),
            "blocklist_delta": _delta(current, baseline, "blocklist_count"),
        },
        "remediation": {
            "remediations_total_delta": _delta(current, baseline, "remediations_total"),
            "by_status_delta": _dict_delta(
                current.get("remediations_by_status"),
                baseline.get("remediations_by_status"),
            ),
            "newly_remediated": new_remediated,
        },
        "runtime": {
            "agent_sessions_delta": _delta(current, baseline, "agent_sessions_total"),
            "agent_decisions_delta": _dict_delta(
                current.get("agent_decisions"), baseline.get("agent_decisions")
            ),
            "new_blocked_examples": new_blocked,
            "alerts_total_delta": _delta(current, baseline, "alerts_total"),
            "alerts_by_severity_delta": _dict_delta(
                current.get("alerts_by_severity"), baseline.get("alerts_by_severity")
            ),
        },
        "stage_change": {
            "from": baseline.get("derived_stage") or "",
            "to": current.get("derived_stage") or "",
        },
        "new_warnings": [
            w for w in current.get("warnings") or []
            if w not in (baseline.get("warnings") or [])
        ],
    }
    return out
