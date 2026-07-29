"""
Structured narrative contract for the customer deliverables.

Everything a model writes reaches the documents through this module, and the
vocabulary is deliberately identical to jbillochon/povplatform
(intelligence/schema.py, intelligence/validation.py) so a section written for
one project can be moved to the other without translation.

The rule both projects enforce: a claim that cannot be traced back to the
collected data does not ship. Citations are checked against an index built
from the snapshot, untraceable ones are stripped, and a finding or scenario
left with no verified evidence is removed rather than shipped with a caveat.
A plausible-sounding invention in a customer report is the failure mode worth
being strict about.

Two exemptions, both deliberate: `contextual` evidence is model knowledge of
public threat activity, so there is nothing to look up and it renders under a
visible caveat; and threat_context blocks are never dropped, only their
tenant links are filtered.

One intentional divergence from povplatform: the substring fallback here
requires the shorter string to reach SUBSTRING_FLOOR characters. The platform
accepts any containment, which lets a short pool entry validate an unrelated
reference. If a legitimate citation is being rejected on a very short item
name, this constant is the place to look.
"""

from __future__ import annotations

import re
from typing import Any

EVIDENCE_KINDS = (
    "inventory_item",
    "koi_finding",
    "governance",
    "agent_activity",
    "cve",
    "contextual",
)

SEVERITIES = ("critical", "high", "medium", "low", "info")
CONFIDENCES = ("confirmed", "likely", "possible")
EFFORTS = ("low", "medium", "high")

MITRE_PATTERN = re.compile(r"^T\d{4}(\.\d{3})?$")
CVE_PATTERN = re.compile(r"^CVE-\d{4}-\d{4,7}$", re.IGNORECASE)

SUBSTRING_FLOOR = 4

POOL_FOR_KIND = {
    "inventory_item": ("items", "inventory"),
    "koi_finding": ("findings", "findings"),
    "governance": ("governance", "policies"),
    "agent_activity": ("agents", "agent activity"),
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _lower(value: Any) -> str:
    return _text(value).lower()


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_text(entry) for entry in value if _text(entry)]


def _one_of(value: Any, allowed: tuple[str, ...], default: str) -> str:
    norm = _lower(value)
    return norm if norm in allowed else default


def build_index(report: dict) -> dict[str, set[str]]:
    """Build the lookup sets a citation can be checked against.

    Item identity is messy across marketplaces, so several forms are accepted:
    the raw item_id, the display name, and "marketplace:item_id".
    """
    items: set[str] = set()
    findings: set[str] = set()

    def absorb(collection: Any) -> None:
        for entry in collection or []:
            if not isinstance(entry, dict):
                continue
            for key in ("item_id", "name", "item_display_name"):
                if entry.get(key):
                    items.add(_lower(entry[key]))
            marketplace = entry.get("marketplace_slug") or entry.get("marketplace")
            item_id = entry.get("item_id")
            if marketplace and item_id:
                items.add(_lower(f"{marketplace}:{item_id}"))
            for finding in entry.get("findings") or []:
                findings.add(
                    _lower(finding if isinstance(finding, str)
                           else finding.get("finding_id", ""))
                )

    for key in ("malicious_items", "top_risk_items", "action_candidates",
                "remediated_items"):
        absorb(report.get(key))

    for row in report.get("finding_frequency") or []:
        if isinstance(row, dict) and row.get("finding"):
            findings.add(_lower(row["finding"]))

    governance: set[str] = set()
    for key in ("policies", "runtime_policies"):
        for policy in report.get(key) or []:
            if isinstance(policy, dict) and policy.get("name"):
                governance.add(_lower(policy["name"]))

    agents: set[str] = set()
    for agent in report.get("agents_seen") or {}:
        agents.add(_lower(agent))
    for event in report.get("agent_blocked_examples") or []:
        if isinstance(event, dict):
            for key in ("agent", "host", "target"):
                if event.get(key):
                    agents.add(_lower(event[key]))

    return {
        "items": items,
        "findings": findings,
        "governance": governance,
        "agents": agents,
    }


def known_cves(enrichment: dict | None) -> set[str]:
    if not enrichment:
        return set()
    return {str(cve).upper() for cve in (enrichment.get("cves") or {})}


def _in_pool(reference: str, pool: set[str]) -> bool:
    needle = _lower(reference)
    if not needle:
        return False
    if needle in pool:
        return True
    for candidate in pool:
        shorter, longer = sorted((needle, candidate), key=len)
        if len(shorter) >= SUBSTRING_FLOOR and shorter in longer:
            return True
    return False


class _Verifier:
    """Checks citations and accumulates a report of what failed."""

    def __init__(self, report: dict, enrichment: dict | None):
        self.index = build_index(report)
        self.cves = known_cves(enrichment)
        self.issues: list[dict] = []
        self.dropped: list[str] = []
        self.checked = 0
        self.verified = 0

    def _fail(self, location: str, kind: str, reference: str, detail: str) -> bool:
        self.issues.append({
            "location": location,
            "kind": kind,
            "reference": reference,
            "detail": detail,
        })
        return False

    def check(self, evidence: Any, location: str) -> bool:
        if not isinstance(evidence, dict):
            return False
        self.checked += 1
        kind = _lower(evidence.get("kind")).replace(" ", "_").replace("-", "_")
        reference = _text(evidence.get("reference"))

        if kind not in EVIDENCE_KINDS:
            return self._fail(
                location, "unknown_item", reference or str(evidence.get("kind")),
                "Evidence kind must be one of " + ", ".join(EVIDENCE_KINDS),
            )
        if not reference:
            return self._fail(location, "empty_evidence", "",
                              "Evidence carries no reference")

        if kind == "contextual":
            self.verified += 1
            return True

        if kind == "cve":
            upper = reference.upper()
            if not CVE_PATTERN.match(upper):
                return self._fail(location, "unknown_cve", reference,
                                  "Not a well-formed CVE identifier")
            if self.cves and upper not in self.cves:
                return self._fail(
                    location, "unknown_cve", reference,
                    "CVE was not among those collected for this snapshot",
                )
            self.verified += 1
            return True

        pool_key, human = POOL_FOR_KIND[kind]
        if _in_pool(reference, self.index[pool_key]):
            self.verified += 1
            return True
        return self._fail(location, "unknown_item", reference,
                          f"Not present in the snapshot's {human} data")

    def check_mitre(self, techniques: list[str], location: str) -> list[str]:
        kept = []
        for technique in techniques:
            if MITRE_PATTERN.match(technique.strip()):
                kept.append(technique.strip())
            else:
                self._fail(location, "bad_mitre", technique,
                           "Not a valid MITRE ATT&CK technique identifier")
        return kept

    def clean_evidence(self, raw: Any, location: str) -> list[dict]:
        if not isinstance(raw, list):
            return []
        return [
            {
                "kind": _lower(e.get("kind")).replace(" ", "_").replace("-", "_"),
                "reference": _text(e.get("reference")),
                "note": _text(e.get("note")) or None,
            }
            for e in raw
            if self.check(e, location)
        ]

    def as_dict(self) -> dict:
        rate = (self.verified / self.checked) if self.checked else 1.0
        return {
            "checked_citations": self.checked,
            "verified_citations": self.verified,
            "verification_rate": round(rate, 3),
            "dropped": self.dropped,
            "issues": self.issues,
        }


def numbers_in_text(text: str) -> list[str]:
    """Surface figures written into prose.

    The model is told not to produce numbers; this makes violations visible at
    review time rather than in front of a customer. Small ordinals and years
    are ignored, since "the first step" and "2026" are not the problem.
    """
    if not text:
        return []
    suspicious = []
    for raw in re.findall(r"\b\d[\d\s,.]*\b", text):
        cleaned = raw.strip().replace(" ", "").replace(",", "")
        if not cleaned:
            continue
        try:
            value = float(cleaned)
        except ValueError:
            continue
        if value < 10:
            continue
        if 1990 <= value <= 2100 and "." not in cleaned:
            continue
        suspicious.append(raw.strip())
    return suspicious


def _clean_key_findings(raw: Any, v: _Verifier) -> list[dict]:
    out: list[dict] = []
    for position, block in enumerate(raw or []):
        if not isinstance(block, dict):
            continue
        title = _text(block.get("title"))
        if not title:
            v.dropped.append(f"key_findings[{position}]: no title")
            continue
        location = f"key_findings[{position}] '{title[:60]}'"
        evidence = v.clean_evidence(block.get("evidence"), location)
        if not evidence:
            v.dropped.append(f"finding: {title}")
            continue
        out.append({
            "title": title,
            "severity": _one_of(block.get("severity"), SEVERITIES, "medium"),
            "confidence": _one_of(block.get("confidence"), CONFIDENCES, "possible"),
            "narrative": _text(block.get("narrative")),
            "evidence": evidence,
            "mitre_techniques": v.check_mitre(
                _string_list(block.get("mitre_techniques")), location),
            "affected_scope": _text(block.get("affected_scope")) or None,
        })
    out.sort(key=lambda block: SEVERITIES.index(block["severity"]))
    return out


def _clean_scenarios(raw: Any, v: _Verifier) -> list[dict]:
    out: list[dict] = []
    for position, block in enumerate(raw or []):
        if not isinstance(block, dict):
            continue
        title = _text(block.get("title"))
        if not title:
            v.dropped.append(f"attack_scenarios[{position}]: no title")
            continue
        location = f"attack_scenarios[{position}] '{title[:60]}'"
        steps = _string_list(block.get("steps"))
        if len(steps) < 2:
            v.dropped.append(f"scenario: {title} (fewer than two steps)")
            continue
        # The schema field is enabling_evidence, but "evidence" is the obvious
        # thing to write and findings use exactly that. Accept both on input
        # rather than silently dropping a whole scenario over a field name.
        raw_evidence = block.get("enabling_evidence")
        if raw_evidence is None:
            raw_evidence = block.get("evidence")
        evidence = v.clean_evidence(raw_evidence, location)
        if not evidence:
            v.dropped.append(f"scenario: {title}")
            continue
        out.append({
            "title": title,
            "steps": steps[:8],
            "impact": _text(block.get("impact")),
            "likelihood": _one_of(block.get("likelihood"), CONFIDENCES, "possible"),
            "enabling_evidence": evidence,
            "mitre_techniques": v.check_mitre(
                _string_list(block.get("mitre_techniques")), location),
            "breaks_at": _text(block.get("breaks_at")) or None,
        })
    out.sort(key=lambda block: CONFIDENCES.index(block["likelihood"]))
    return out


def _clean_actions(raw: Any, v: _Verifier) -> list[dict]:
    out: list[dict] = []
    for position, block in enumerate(raw or []):
        if not isinstance(block, dict):
            continue
        title = _text(block.get("title"))
        if not title:
            v.dropped.append(f"recommended_actions[{position}]: no title")
            continue
        try:
            priority = int(block.get("priority") or block.get("rank") or position + 1)
        except (TypeError, ValueError):
            priority = position + 1
        out.append({
            "title": title,
            "rationale": _text(block.get("rationale")),
            "priority": max(1, min(priority, 10)),
            "effort": _one_of(block.get("effort"), EFFORTS, "medium"),
            "platform_capability": _text(block.get("platform_capability")) or None,
            "expected_outcome": _text(block.get("expected_outcome")) or None,
            "addresses_findings": _string_list(block.get("addresses_findings"))[:10],
        })
    out.sort(key=lambda block: block["priority"])
    return out


def _clean_threat_context(raw: Any, v: _Verifier) -> list[dict]:
    out: list[dict] = []
    for position, block in enumerate(raw or []):
        if not isinstance(block, dict):
            continue
        campaign = _text(block.get("campaign_or_pattern"))
        relevance = _text(block.get("relevance"))
        if not campaign or not relevance:
            v.dropped.append(
                f"threat_context[{position}]: campaign_or_pattern or relevance missing")
            continue
        location = f"threat_context[{position}] '{campaign[:60]}'"
        out.append({
            "campaign_or_pattern": campaign,
            "relevance": relevance,
            "tenant_link": v.clean_evidence(block.get("tenant_link"), location),
        })
    return out


def _audit_prose(narrative: dict, v: _Verifier) -> None:
    def scan(text: str | None, location: str) -> None:
        for number in numbers_in_text(text or ""):
            v.issues.append({
                "location": location,
                "kind": "prose_number",
                "reference": number,
                "detail": (
                    "Figure written into prose. Every number shown to a customer "
                    "must come from the snapshot, not the model."
                ),
            })

    scan(narrative["headline"], "headline")
    scan(narrative["executive_summary"], "executive_summary")
    scan(narrative["recommendations"], "recommendations")
    for i, block in enumerate(narrative["key_findings"]):
        scan(block["narrative"], f"key_findings[{i}].narrative")
    for i, block in enumerate(narrative["attack_scenarios"]):
        scan(block["impact"], f"attack_scenarios[{i}].impact")
    for i, block in enumerate(narrative["recommended_actions"]):
        scan(block["rationale"], f"recommended_actions[{i}].rationale")


def normalise(
    report: dict,
    *,
    headline: str = "",
    executive_summary: str = "",
    recommendations: str = "",
    success_criteria: list[dict] | None = None,
    key_findings: list[dict] | None = None,
    attack_scenarios: list[dict] | None = None,
    recommended_actions: list[dict] | None = None,
    threat_context: list[dict] | None = None,
    data_gaps: list[str] | None = None,
) -> tuple[dict, dict]:
    """Normalise and verify the narrative. Returns (narrative, validation).

    The validation dict lists what was dropped, what could not be verified, and
    the share of citations that checked out. It is for the operator, never for
    the customer document, and it must be surfaced rather than swallowed: a
    silent drop is exactly the failure this guards against.
    """
    v = _Verifier(report, report.get("enrichment"))

    narrative = {
        "headline": _text(headline),
        "executive_summary": _text(executive_summary),
        "recommendations": _text(recommendations),
        "success_criteria": success_criteria or [],
        "key_findings": _clean_key_findings(key_findings, v),
        "attack_scenarios": _clean_scenarios(attack_scenarios, v),
        "recommended_actions": _clean_actions(recommended_actions, v),
        "threat_context": _clean_threat_context(threat_context, v),
        "data_gaps": _string_list(data_gaps)[:8],
    }
    _audit_prose(narrative, v)
    return narrative, v.as_dict()
