"""
Supply-chain view over a collected snapshot.

Ported from jbillochon/povplatform (rendering/supply_chain.py) unchanged, so
the two projects group and label findings identically. Any fix here belongs
there too.

Koi reports one flat list of findings per item. Flattened into a frequency
table it reads as a pile of unrelated labels ("Unmaintained Item", "Missing
Provenance", "Individual Publisher") and the supply-chain story in it is
invisible: where software enters the estate, whether its origin can be
established, whether anyone is still maintaining it, and whether it is known
to be vulnerable or actively malicious.

Nothing here invents a fact. Every number is a count of findings Koi itself
reported; this module only groups and labels them. Two rules follow from that:

* A finding that matches no dimension is **kept and reported** as
  uncategorised, never dropped. Koi adds finding types over time, and silently
  omitting one would understate the customer's exposure in a document they
  make decisions from.
* An item carrying three findings in one dimension counts three times in that
  dimension's finding total. Findings are counted, not items; the two are
  labelled differently everywhere they are rendered.
"""

from __future__ import annotations

import re

DIMENSIONS: list[dict] = [
    {
        "key": "provenance",
        "label": "Provenance & publisher trust",
        "question": "Can the origin of this software be established?",
        "mitre": ["T1195.002"],
        "matchers": [
            "missing provenance",
            "unverified publisher",
            "individual publisher",
            "publisher has only one item",
            "publisher email in compromised list",
            "transfer of ownership",
            "repository created after item publish date",
            "unpopular github repository",
            "typosquatting",
            "no authentication",
        ],
    },
    {
        "key": "maintenance",
        "label": "Maintenance & lifecycle",
        "question": "Is anyone still maintaining and publishing fixes for it?",
        "mitre": ["T1195.002"],
        "matchers": [
            "unmaintained",
            "removed from marketplace",
            "deprecated marketplace item",
            "archived git repository",
            "communication with expired domain",
        ],
    },
    {
        "key": "vulnerability",
        "label": "Known vulnerabilities",
        "question": "Does it carry defects an attacker can already use?",
        "mitre": ["T1195.001"],
        "matchers": [
            "contains vulnerability",
            "vulnerable dependency",
            "vulnerable to",
        ],
    },
    {
        "key": "compromise",
        "label": "Active compromise indicators",
        "question": "Is there evidence it is already behaving maliciously?",
        "mitre": ["T1195.002", "T1027"],
        "matchers": [
            "malware detected",
            "malicious activity detected",
            "associated with malicious campaign",
            "obfuscated code",
            "hardcoded secret",
            "secrets in code",
            "exfils",
            "data exfiltration",
        ],
    },
]

#: Findings that describe what an item *can do* once trusted, rather than
#: whether it should be trusted at all. Excluded from the supply-chain view on
#: purpose: the risk sections already cover them, and folding them in here
#: would inflate every dimension with permission counts.
RUNTIME_MATCHERS = [
    "permission",
    "collection of",
    "clipboard",
    "screen capture",
    "file creation",
    "process execution",
    "code execution",
    "dynamic code execution",
    "arbitrary code execution",
    "bypasses network control",
    "external communication",
    "unrestricted network access",
    "uses third party ai model",
]

CHANNELS: list[dict] = [
    {
        "key": "browser",
        "label": "Browser extension stores",
        "members": ["chrome web store", "edge add-ons", "firefox add-ons",
                    "office add-ins"],
    },
    {
        "key": "editor",
        "label": "IDE & editor marketplaces",
        "members": ["vs code marketplace", "open vsx", "jetbrains",
                    "visual studio", "cursor", "windsurf", "notepad++",
                    "claude desktop extensions"],
    },
    {
        "key": "registry",
        "label": "Package registries",
        "members": ["npm", "pypi", "homebrew", "chocolatey"],
    },
    {
        "key": "model",
        "label": "Model & container registries",
        "members": ["hugging face", "ollama", "docker"],
    },
    {
        "key": "mcp",
        "label": "MCP registries",
        "members": ["github mcp registry", "mcp registry", "agent skills"],
    },
    {
        "key": "forge",
        "label": "Source forges",
        "members": ["github", "gitlab", "bitbucket"],
    },
    {
        "key": "os",
        "label": "Operating system software",
        "members": ["windows software", "macos software", "linux software",
                    "binaries"],
    },
]


def _norm(label: str) -> str:
    """Normalise a finding or marketplace label for matching."""
    return re.sub(r"[^a-z0-9 ]+", " ", str(label).replace("_", " ").lower()).strip()


def _matches(norm_label: str, matchers: list[str]) -> bool:
    return any(m in norm_label for m in matchers)


# Channel members are written the way the labels read; normalise them once so
# "Firefox Add-ons" matches "firefox add-ons". Comparing a normalised label
# against an unnormalised member silently dropped every hyphenated store into
# "Other sources".
_CHANNEL_MEMBERS = {
    c["key"]: {_norm(m) for m in c["members"]} for c in CHANNELS
}


def classify_findings(finding_frequency: list[dict] | None) -> dict:
    """
    Group a finding frequency table into supply-chain dimensions.

    Returns the dimensions in their declared order, each with the findings that
    landed in it and their total, plus `uncategorised` for anything that
    matched no dimension and is not a runtime-capability finding.
    """
    rows = [
        {"finding": f.get("finding"), "count": int(f.get("count") or 0)}
        for f in (finding_frequency or [])
        if f.get("finding")
    ]

    buckets: dict[str, list[dict]] = {d["key"]: [] for d in DIMENSIONS}
    uncategorised: list[dict] = []
    runtime_total = 0

    for row in rows:
        norm = _norm(row["finding"])
        for dim in DIMENSIONS:
            if _matches(norm, dim["matchers"]):
                buckets[dim["key"]].append(row)
                break
        else:
            if _matches(norm, RUNTIME_MATCHERS):
                runtime_total += row["count"]
            else:
                uncategorised.append(row)

    out = []
    for dim in DIMENSIONS:
        found = sorted(buckets[dim["key"]], key=lambda r: -r["count"])
        out.append({
            "key": dim["key"],
            "label": dim["label"],
            "question": dim["question"],
            "mitre": dim["mitre"],
            "findings": found,
            "total": sum(r["count"] for r in found),
        })

    supply_total = sum(d["total"] for d in out)
    return {
        "dimensions": out,
        "uncategorised": sorted(uncategorised, key=lambda r: -r["count"]),
        "supply_chain_total": supply_total,
        "runtime_total": runtime_total,
        # Only the findings the collector returned: it caps the frequency
        # table, so this is not the estate-wide total and is never labelled as
        # one.
        "reported_total": sum(r["count"] for r in rows),
    }


def channel_breakdown(items_by_marketplace: dict | None) -> list[dict]:
    """
    Group marketplaces into the channels software arrives through.

    A marketplace that matches no channel is carried under "Other sources"
    rather than dropped, so the channel totals always reconcile with the
    marketplace table.
    """
    entries = list((items_by_marketplace or {}).items())
    if not entries:
        return []

    grouped: dict[str, list[tuple[str, int]]] = {c["key"]: [] for c in CHANNELS}
    other: list[tuple[str, int]] = []

    for name, count in entries:
        norm = _norm(name)
        for channel in CHANNELS:
            # Exact match on the normalised label: "github" must not swallow
            # "github mcp registry", which is a different route in.
            if norm in _CHANNEL_MEMBERS[channel["key"]]:
                grouped[channel["key"]].append((name, int(count or 0)))
                break
        else:
            other.append((name, int(count or 0)))

    out = []
    for channel in CHANNELS:
        members = grouped[channel["key"]]
        if not members:
            continue
        out.append({
            "key": channel["key"],
            "label": channel["label"],
            "total": sum(c for _, c in members),
            "members": sorted(members, key=lambda m: -m[1]),
        })
    if other:
        out.append({
            "key": "other",
            "label": "Other sources",
            "total": sum(c for _, c in other),
            "members": sorted(other, key=lambda m: -m[1]),
        })
    return sorted(out, key=lambda c: -c["total"])


def publisher_profile(report: dict) -> dict:
    """
    How concentrated the estate's software supply is.

    A high item-per-publisher ratio means few suppliers to assess; a ratio near
    one means the estate depends on almost as many distinct third parties as it
    has pieces of software, and each is a separate trust decision.
    """
    items = int(report.get("items_total") or 0)
    publishers = int(report.get("unique_publishers") or 0)
    return {
        "items": items,
        "publishers": publishers,
        "items_per_publisher": (items / publishers) if publishers else None,
    }


def supply_chain_view(report: dict) -> dict:
    """
    Everything the report and the deck need, computed once.

    Each dimension carries **two independent counts**, because they answer
    different questions and one of them can be misleadingly absent:

    * ``total`` - findings of this kind across the estate, from the frequency
      table. Snapshots whose collector capped that table to the most frequent
      finding types render a dimension outside the cut as 0.
    * ``items_seen`` - how many of the ranked items Koi returned carry a
      finding in this dimension. Computed from the item lists, so it is exact
      for those lists whatever the frequency table was truncated to.

    ``understated`` marks a dimension whose findings appear on named items but
    not in the frequency table. Rendering a bare 0 there would tell a customer
    they have no active compromise indicators while critical items in the same
    document carry "Malicious Activity Detected".
    """
    findings = classify_findings(report.get("finding_frequency"))
    for dim in findings["dimensions"]:
        matching = top_items_for(report, dim["key"], limit=None)
        dim["items_seen"] = len(matching)
        dim["examples"] = matching[:6]
        dim["understated"] = dim["total"] == 0 and bool(matching)
    return {
        "findings": findings,
        "channels": channel_breakdown(report.get("items_by_marketplace")),
        "publishers": publisher_profile(report),
    }


def top_items_for(
    report: dict, dimension_key: str, limit: int | None = 6
) -> list[dict]:
    """
    Named items carrying a finding in this dimension, worst blast radius first.

    Drawn from the item lists the collector already ranked, so every item named
    here is one Koi returned with that finding attached, never inferred from
    the aggregate counts.
    """
    dim = next((d for d in DIMENSIONS if d["key"] == dimension_key), None)
    if dim is None:
        return []

    seen: set[tuple] = set()
    out: list[dict] = []
    for key in ("malicious_items", "top_risk_items", "action_candidates"):
        for item in report.get(key) or []:
            hits = [
                f for f in (item.get("findings") or [])
                if _matches(_norm(f), dim["matchers"])
            ]
            if not hits:
                continue
            ident = (item.get("name"), item.get("publisher"))
            if ident in seen:
                continue
            seen.add(ident)
            out.append({
                "name": item.get("name"),
                "publisher": item.get("publisher"),
                "marketplace": item.get("marketplace"),
                "version": item.get("version"),
                "risk": item.get("risk"),
                "risk_level": item.get("risk_level"),
                "endpoints": item.get("endpoints") or 0,
                "matched": hits,
            })

    out.sort(key=lambda i: (i.get("endpoints") or 0, i.get("risk") or 0), reverse=True)
    return out if limit is None else out[:limit]
