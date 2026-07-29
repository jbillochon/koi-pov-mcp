"""
Narrative and supply-chain sections for the PDF report.

Mirror of docx_sections.py against reportlab, so the two documents carry the
same sections in the same order with the same wording. Anything fixed in one
belongs in the other.

Nothing here computes a figure. Counts come from supply_chain.py, which groups
what Koi reported; prose comes from the narrative, whose citations were
verified before it got here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class Kit:
    """The story and the formatting helpers, handed over by build_pdf."""

    story: list
    para: Callable
    table: Callable
    page_break: Callable
    h1: Any
    h2: Any
    body: Any
    lede: Any
    note: Any
    heading: Callable
    tag_style: Any
    palette: dict


def _pct(value: int, total: int) -> str:
    return f"{100 * value / total:.1f}%" if total else "\u2014"


def _tags(kit: Kit, labels: list[str], accent: str | None) -> None:
    labels = [label for label in labels if label]
    if not labels:
        return
    parts = []
    for position, label in enumerate(labels):
        colour = accent if position == 0 and accent else kit.palette.get("muted")
        parts.append(f'<font color="{colour}"><b>{label}</b></font>')
    kit.story.append(kit.tag_style("  \u00b7  ".join(parts)))


def _evidence(kit: Kit, entries: list[dict] | None, label: str = "EVIDENCE") -> None:
    if not entries:
        return
    muted = kit.palette.get("muted")
    kit.story.append(kit.tag_style(f'<font color="{muted}"><b>{label}</b></font>'))
    for entry in entries:
        kind = str(entry.get("kind", "")).replace("_", " ")
        text = f"\u2022 {entry.get('reference', '')} ({kind})"
        if entry.get("note"):
            text += " \u2014 " + entry["note"]
        kit.para(text, kit.note)


# ------------------------------------------------------------ supply chain


def supply_chain(kit: Kit, view: dict) -> None:
    if not view:
        return
    channels = view.get("channels") or []
    dimensions = (view.get("findings") or {}).get("dimensions") or []
    if not channels and not dimensions:
        return

    kit.page_break()
    kit.heading("Software supply chain", 1)
    kit.para("Where this software comes from, and what is known about the "
             "parties behind it.", kit.lede)

    profile = view.get("publishers") or {}
    ratio = profile.get("items_per_publisher")
    if profile.get("publishers"):
        kit.para(
            f"The estate carries {profile['items']:,} items sourced from "
            f"{profile['publishers']:,} distinct third-party publishers, an "
            f"average of {ratio:.1f} items per publisher. Each publisher is a "
            "separate trust decision, and each is a party whose compromise "
            "would reach this estate through software you already run."
        )

    if channels:
        kit.heading("How software enters the estate", 2)
        kit.para("Marketplaces and registries grouped by the route they "
                 "represent. Each item is counted once, at its source.", kit.lede)
        total = sum(c["total"] for c in channels)
        kit.table(
            ["Channel", "Sources", "Items", "Share"],
            [[c["label"],
              ", ".join(f"{n} ({q:,})" for n, q in c["members"])[:80],
              format(c["total"], ","),
              _pct(c["total"], total)]
             for c in channels],
            weights=[2.4, 4.2, 1, 1],
        )
        kit.para(
            "Shares are of the " + format(total, ",") + " items whose source "
            "the platform recorded, so they total 100%. Items with no recorded "
            "marketplace are absent from this table and from those shares.",
            kit.note,
        )

    if dimensions:
        kit.heading("Trust signals by dimension", 2)
        kit.para("Findings reported by Koi, grouped by the supply-chain "
                 "question each one answers. One item can carry several "
                 "findings, so these are counts of findings, not of items.",
                 kit.lede)
        for dim in dimensions:
            _dimension(kit, dim)

    uncategorised = (view.get("findings") or {}).get("uncategorised") or []
    if uncategorised:
        kit.heading("Not yet categorised", 2)
        kit.para("Finding types with no supply-chain dimension yet. Listed "
                 "rather than dropped, so nothing is understated.", kit.lede)
        kit.table(["Finding", "Occurrences"],
                  [[str(r["finding"]).replace("_", " "), format(r["count"], ",")]
                   for r in uncategorised[:10]], weights=[4, 1])


def _dimension(kit: Kit, dim: dict) -> None:
    kit.heading(dim["label"], 2)
    mitre = ", ".join(dim.get("mitre") or [])
    kit.para(dim["question"] + (f"  \u00b7  MITRE {mitre}" if mitre else ""),
             kit.lede)

    seen = dim.get("items_seen") or 0
    if dim.get("understated"):
        kit.para(
            f"{seen} of the ranked items carry a finding in this dimension. "
            "This snapshot did not record an estate-wide count for it, so no "
            "total is shown rather than a misleading zero."
        )
    elif dim.get("total"):
        kit.para(f"{dim['total']:,} findings across the estate; {seen} of the "
                 "ranked items carry one.")
    else:
        kit.para("No finding in this dimension was reported for this estate.")
        return

    if dim.get("findings"):
        kit.table(["Finding", "Occurrences"],
                  [[str(r["finding"]).replace("_", " "), format(r["count"], ",")]
                   for r in dim["findings"][:8]], weights=[4, 1])

    if dim.get("examples"):
        kit.table(
            ["Item", "Publisher", "Source", "Finding", "Endpoints"],
            [[(e.get("name") or "")[:32],
              (e.get("publisher") or "")[:22],
              (e.get("marketplace") or "")[:16],
              ", ".join(e.get("matched") or [])[:40],
              format(int(e.get("endpoints") or 0), ",")]
             for e in dim["examples"]],
            weights=[2.8, 2, 1.6, 3, 0.9],
        )


# ----------------------------------------------------------------- findings


def findings(kit: Kit, blocks: list[dict]) -> None:
    if not blocks:
        return
    kit.page_break()
    kit.heading("Findings", 1)
    kit.para("Each finding cites the collected data it rests on. Confidence "
             "is stated explicitly.", kit.lede)
    for block in blocks:
        kit.heading(block["title"], 2)
        _tags(kit, [block["severity"].upper(), block["confidence"].upper()]
              + list(block.get("mitre_techniques") or []),
              kit.palette.get(block["severity"]))
        if block.get("narrative"):
            kit.para(block["narrative"])
        if block.get("affected_scope"):
            kit.para("Scope: " + block["affected_scope"])
        _evidence(kit, block.get("evidence"))


def scenarios(kit: Kit, blocks: list[dict]) -> None:
    if not blocks:
        return
    kit.page_break()
    kit.heading("Attack scenarios", 1)
    kit.para("Paths an attacker could take given the exposure observed in this "
             "tenant. These are illustrative, not incidents that have "
             "occurred.", kit.lede)
    for block in blocks:
        kit.heading(block["title"], 2)
        _tags(kit, [block["likelihood"].upper()]
              + list(block.get("mitre_techniques") or []), None)
        for position, step in enumerate(block["steps"], start=1):
            kit.para(f"{position}. {step}")
        if block.get("impact"):
            kit.para("Impact. " + block["impact"])
        if block.get("breaks_at"):
            kit.para("What breaks this chain. " + block["breaks_at"])
        _evidence(kit, block.get("enabling_evidence"))


def actions(kit: Kit, blocks: list[dict], fallback: str = "") -> None:
    kit.page_break()
    kit.heading("Recommended actions", 1)
    kit.para("Ordered by risk reduced, not by ease of implementation.", kit.lede)

    if not blocks:
        kit.para(fallback or "[[TO BE PROVIDED: recommended actions]]")
        return

    for position, block in enumerate(blocks, start=1):
        kit.heading(f"{position}. {block['title']}", 2)
        _tags(kit, [block["effort"].upper() + " EFFORT"], None)
        if block.get("rationale"):
            kit.para(block["rationale"])
        if block.get("expected_outcome"):
            kit.para(block["expected_outcome"])
        if block.get("platform_capability"):
            kit.para("Platform capability: " + block["platform_capability"],
                     kit.note)


def threat_context(kit: Kit, blocks: list[dict]) -> None:
    if not blocks:
        return
    kit.page_break()
    kit.heading("Threat context", 1)
    kit.para("Related public threat activity.", kit.lede)
    kit.para("This section was NOT verified against your tenant. It draws on "
             "the analyst's knowledge of publicly reported activity and is "
             "provided for context only. Every preceding section is traced to "
             "data collected from your environment.", kit.note)
    for block in blocks:
        kit.heading(block["campaign_or_pattern"], 2)
        kit.para(block["relevance"])
        _evidence(kit, block.get("tenant_link"), label="WHAT LINKS IT HERE")


def data_gaps(kit: Kit, gaps: list[str]) -> None:
    if not gaps:
        return
    kit.heading("Data gaps", 2)
    kit.para("What this report could not establish, and why.", kit.lede)
    for gap in gaps:
        kit.para("\u2022 " + gap)


def validation_note(kit: Kit, validation: dict | None) -> None:
    if not validation or not validation.get("checked_citations"):
        return
    checked = validation["checked_citations"]
    verified = validation.get("verified_citations", 0)
    dropped = len(validation.get("dropped") or [])
    line = (f"Citation check: {verified} of {checked} citations in the "
            "analytical sections were traced back to the collected data.")
    if dropped:
        line += (f" {dropped} claim(s) could not be traced and were removed "
                 "rather than shipped.")
    kit.para(line, kit.note)
