"""
Structured narrative contract for the customer deliverables.

Everything a model writes reaches the documents through this module. The
renderers never see the raw arguments: they see a normalised narrative whose
evidence has already been checked against the collected data.

The rule reproduced here is the one the PoV platform enforces: a claim that
cannot be traced back to collected data does not ship. Untraceable evidence is
dropped and reported to the operator, and a block left with no evidence at all
is dropped with it. Nothing is silently repaired.
"""

from __future__ import annotations

import re
from typing import Any

EVIDENCE_KINDS = ("inventory_item", "koi_finding", "policy", "metric")

SEVERITIES = ("critical", "high", "medium", "low", "informational")
CONFIDENCES = ("confirmed", "probable", "possible", "observation")
LIKELIHOODS = ("likely", "possible", "unlikely")
EFFORTS = ("low effort", "medium effort", "high effort")

SUBSTRING_FLOOR = 6


def _norm(value: Any) -> str:
    return re.sub(r"[\s_\-]+", " ", str(value or "").strip().lower())


def _names(rows: Any, *keys: str) -> set[str]:
    out: set[str] = set()
    if not isinstance(rows, list):
        return out
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in keys:
            value = row.get(key)
            if isinstance(value, str) and value.strip():
                out.add(_norm(value))
            elif isinstance(value, list):
                for entry in value:
                    if isinstance(entry, str) and entry.strip():
                        out.add(_norm(entry))
    return out


def build_index(data: dict) -> dict[str, set[str]]:
    """Lookup sets of everything a piece of evidence may legitimately cite."""
    items: set[str] = set()
    for key in ("top_risk_items", "action_candidates", "remediated_items"):
        items |= _names(data.get(key), "name")

    findings = _names(data.get("finding_frequency"), "finding")
    for key in ("top_risk_items", "action_candidates"):
        findings |= _names(data.get(key), "findings")

    enrichment = data.get("enrichment") or {}
    findings |= _names(enrichment.get("mitre"), "finding")

    policies = _names(data.get("policies"), "name")
    policies |= _names(data.get("runtime_policies"), "name")

    metrics = {
        _norm(key) for key, value in data.items()
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    }

    return {
        "inventory_item": items,
        "koi_finding": findings,
        "policy": policies,
        "metric": metrics,
    }


def _known(source: str, known: set[str]) -> bool:
    needle = _norm(source)
    if not needle:
        return False
    if needle in known:
        return True
    for candidate in known:
        shorter, longer = sorted((needle, candidate), key=len)
        if len(shorter) >= SUBSTRING_FLOOR and shorter in longer:
            return True
    return False


def _one_of(value: Any, allowed: tuple[str, ...], default: str) -> str:
    norm = _norm(value)
    return norm if norm in allowed else default


def _text(value: Any) -> str:
    return str(value or "").strip()


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_text(entry) for entry in value if _text(entry)]


def _clean_evidence(raw: Any, index: dict, audit: list[str], where: str) -> list[dict]:
    kept: list[dict] = []
    if not isinstance(raw, list):
        return kept
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        kind = _norm(entry.get("kind")).replace(" ", "_")
        source = _text(entry.get("source"))
        if kind not in EVIDENCE_KINDS:
            audit.append(
                f"{where}: evidence kind {entry.get('kind')!r} is not one of "
                f"{', '.join(EVIDENCE_KINDS)}; dropped"
            )
            continue
        if not _known(source, index.get(kind, set())):
            audit.append(
                f"{where}: evidence {source!r} ({kind}) was not found in the "
                "collected data; dropped"
            )
            continue
        kept.append({"kind": kind, "source": source, "detail": _text(entry.get("detail"))})
    return kept


def _clean_findings(raw: Any, index: dict, audit: list[str]) -> list[dict]:
    out: list[dict] = []
    for position, block in enumerate(raw or [], start=1):
        if not isinstance(block, dict):
            continue
        title = _text(block.get("title"))
        if not title:
            audit.append(f"finding #{position}: no title; dropped")
            continue
        where = f"finding {title!r}"
        evidence = _clean_evidence(block.get("evidence"), index, audit, where)
        if not evidence:
            audit.append(f"{where}: no traceable evidence left; the finding was dropped")
            continue
        out.append({
            "title": title,
            "severity": _one_of(block.get("severity"), SEVERITIES, "medium"),
            "confidence": _one_of(block.get("confidence"), CONFIDENCES, "observation"),
            "mitre": _string_list(block.get("mitre")),
            "narrative": _text(block.get("narrative")),
            "scope": _text(block.get("scope")),
            "evidence": evidence,
        })
    out.sort(key=lambda block: SEVERITIES.index(block["severity"]))
    return out


def _clean_scenarios(raw: Any, index: dict, audit: list[str]) -> list[dict]:
    out: list[dict] = []
    for position, block in enumerate(raw or [], start=1):
        if not isinstance(block, dict):
            continue
        title = _text(block.get("title"))
        if not title:
            audit.append(f"attack scenario #{position}: no title; dropped")
            continue
        where = f"attack scenario {title!r}"
        chain = _string_list(block.get("chain"))
        if len(chain) < 2:
            audit.append(f"{where}: fewer than two steps in the chain; dropped")
            continue
        evidence = _clean_evidence(block.get("evidence"), index, audit, where)
        if not evidence:
            audit.append(f"{where}: no traceable evidence left; the scenario was dropped")
            continue
        out.append({
            "title": title,
            "likelihood": _one_of(block.get("likelihood"), LIKELIHOODS, "possible"),
            "mitre": _string_list(block.get("mitre")),
            "chain": chain,
            "impact": _text(block.get("impact")),
            "breaks_chain": _text(block.get("breaks_chain")),
            "evidence": evidence,
        })
    out.sort(key=lambda block: LIKELIHOODS.index(block["likelihood"]))
    return out


def _clean_actions(raw: Any, audit: list[str]) -> list[dict]:
    out: list[dict] = []
    for position, block in enumerate(raw or [], start=1):
        if not isinstance(block, dict):
            continue
        title = _text(block.get("title"))
        if not title:
            audit.append(f"recommended action #{position}: no title; dropped")
            continue
        try:
            rank = int(block.get("rank") or position)
        except (TypeError, ValueError):
            rank = position
        out.append({
            "rank": rank,
            "title": title,
            "effort": _one_of(block.get("effort"), EFFORTS, "medium effort"),
            "rationale": _text(block.get("rationale")),
            "outcome": _text(block.get("outcome")),
            "capability": _text(block.get("capability")),
        })
    out.sort(key=lambda block: block["rank"])
    for position, block in enumerate(out, start=1):
        block["rank"] = position
    return out


def _clean_threat_context(raw: Any, audit: list[str]) -> list[dict]:
    out: list[dict] = []
    for position, block in enumerate(raw or [], start=1):
        if not isinstance(block, dict):
            continue
        title = _text(block.get("title"))
        body = _text(block.get("body"))
        if not title or not body:
            audit.append(f"threat context #{position}: title or body missing; dropped")
            continue
        out.append({"title": title, "body": body})
    return out


def normalise(
    data: dict,
    *,
    headline: str = "",
    executive_summary: str = "",
    recommendations: str = "",
    success_criteria: list[dict] | None = None,
    findings: list[dict] | None = None,
    attack_scenarios: list[dict] | None = None,
    recommended_actions: list[dict] | None = None,
    threat_context: list[dict] | None = None,
) -> tuple[dict, list[str]]:
    """Normalise and verify the narrative. Returns (narrative, audit).

    The audit lists everything that was dropped and why. It is meant for the
    operator, never for the customer document, and it must be reported rather
    than swallowed: a silent drop is exactly the failure mode this guards
    against.
    """
    audit: list[str] = []
    index = build_index(data)

    narrative = {
        "headline": _text(headline),
        "executive_summary": _text(executive_summary),
        "recommendations": _text(recommendations),
        "success_criteria": success_criteria or [],
        "findings": _clean_findings(findings, index, audit),
        "attack_scenarios": _clean_scenarios(attack_scenarios, index, audit),
        "recommended_actions": _clean_actions(recommended_actions, audit),
        "threat_context": _clean_threat_context(threat_context, audit),
    }
    return narrative, audit
