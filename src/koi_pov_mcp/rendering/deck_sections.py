"""
Analytical slides for the deck.

The deck already carried the data layer: discovery, risk, governance,
remediation, agentic activity. What it lacked, and what the PoV platform's
deck has, is the layer that says what the data means: where the software comes
from, what the analyst concluded, how an attacker could use it, and what to do
first.

Two rules earned by comparing a first attempt against the platform's deck:

* **Carry the substance, not the label.** Every evidence entry has a reference
  and a note, and the note is where the specificity lives - "Version 7.0.18,
  7.0.17, 7.0.14 and 7.0.13 all carry Malicious Activity Detected" says
  something the bare item name does not. Dropping notes and truncating the
  narrative produced slides that announced a section without carrying it.
* **Lay out to the content, never to a fixed grid.** Blocks placed at fixed
  heights leave a hole when the text is short and overflow when it is long.
  Every block here advances a cursor by its own estimated height.

These are free functions attached to DeckBuilder by attach(), so deck.py keeps
one class and this file can grow without it.

Nothing here computes a figure. Counts come from supply_chain.py, prose from
the verified narrative.
"""

from __future__ import annotations

from pptx.enum.text import MSO_ANCHOR

SEV_TAG = {"critical": "CRITICAL", "high": "HIGH", "medium": "MEDIUM",
           "low": "LOW", "info": "INFO"}

KIND_LABEL = {
    "inventory_item": "inventory item",
    "koi_finding": "koi finding",
    "governance": "governance",
    "agent_activity": "agent activity",
    "cve": "CVE",
    "contextual": "context",
}


def _pal(self):
    """The palette lives in deck.py; fetch it lazily to avoid a cycle."""
    from . import deck as _d
    return _d


def _chunk(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _height(text, width_in, size_pt, line_spacing=1.18):
    """Estimate the height a wrapped run of text needs, in inches.

    Deliberately slightly generous: a block that reserves too little space
    overlaps the one after it, which is the defect a reader notices first.
    """
    if not text:
        return 0.0
    chars_per_line = max(12, int(width_in * 72.0 / (size_pt * 0.495)))
    lines = 0
    for paragraph in str(text).split("\n"):
        lines += max(1, -(-len(paragraph) // chars_per_line))
    return lines * (size_pt * line_spacing) / 72.0


def _tag_line(labels):
    return "   \u00b7   ".join(str(x) for x in labels if x)


def _evidence_lines(entries, limit=6):
    """Reference, kind and note on one line each, which is what carries the point."""
    out = []
    for entry in entries[:limit]:
        kind = KIND_LABEL.get(entry.get("kind", ""), entry.get("kind", ""))
        line = f"{entry.get('reference', '')}  ({kind})"
        if entry.get("note"):
            line += "  \u2014  " + str(entry["note"])
        out.append(line)
    return out


# --------------------------------------------------------------- supply chain


def slide_supply_chain(self):
    """Where software enters the estate, and how concentrated its supply is."""
    p = _pal(self)
    view = self.n.get("supply_chain") or {}
    channels = view.get("channels") or []
    profile = view.get("publishers") or {}
    if not channels:
        return

    s = self._slide()
    self._header(s, "Software supply chain \u2014 where it comes from",
                 "Every publisher is a separate trust decision",
                 tag="SUPPLY CHAIN", tag_color=p.TEAL)

    total = sum(c["total"] for c in channels)
    cw = (p.CONTENT_W - 2 * 0.35) / 3
    self._kpi(s, p.M, 2.45, cw, 2.1, f"{profile.get('items', 0):,}",
              "Items in the estate", "across every marketplace", p.MINT)
    self._kpi(s, p.M + cw + 0.35, 2.45, cw, 2.1,
              f"{profile.get('publishers', 0):,}", "Distinct publishers",
              "each one a trust decision", p.TEAL)
    ratio = profile.get("items_per_publisher")
    self._kpi(s, p.M + 2 * (cw + 0.35), 2.45, cw, 2.1,
              f"{ratio:.1f}" if ratio else "\u2014", "Items per publisher",
              "lower means more parties to trust", p.TEAL)

    self._text(s, p.M, 5.0, p.CONTENT_W, 0.32,
               "How software enters the estate", size=16, bold=True, color=p.TEAL)
    self._text(s, p.M, 5.38, p.CONTENT_W, 0.28,
               "Marketplaces grouped by the route they represent. "
               "Each item is counted once, at its source.",
               size=11.5, color=p.TEXT_LO)
    rows = [[c["label"],
             ", ".join(f"{n} ({q:,})" for n, q in c["members"])[:70],
             f"{c['total']:,}",
             f"{100 * c['total'] / total:.1f}%" if total else "\u2014"]
            for c in channels]
    self._table(s, p.M, 5.85, p.CONTENT_W,
                ["Channel", "Sources", "Items", "Share"], rows,
                [4.4, 9.6, 2.3, 2.2], max_rows=8)

    self._footer(s, f"Shares are of the {total:,} items whose source was recorded")
    return s


def slide_supply_chain_items(self):
    """The four supply-chain questions, and the items that answer them."""
    p = _pal(self)
    dims = ((self.n.get("supply_chain") or {}).get("findings") or {}).get(
        "dimensions") or []
    dims = [d for d in dims if d.get("examples")]
    if not dims:
        return

    s = self._slide()
    self._header(s, "Supply chain \u2014 the items behind the numbers",
                 "Findings grouped by the question each one answers",
                 tag="SUPPLY CHAIN", tag_color=p.TEAL)

    cw = (p.CONTENT_W - 0.4) / 2
    ch = 3.95
    for i, dim in enumerate(dims[:4]):
        cx = p.M + (i % 2) * (cw + 0.4)
        cy = 2.45 + (i // 2) * (ch + 0.35)
        self._card(s, cx, cy, cw, ch)
        self._text(s, cx + 0.3, cy + 0.24, cw - 0.6, 0.3, dim["label"],
                   size=15.5, bold=True, color=p.TEAL)
        self._text(s, cx + 0.3, cy + 0.56, cw - 0.6, 0.26, dim["question"],
                   size=11, color=p.TEXT_MID, italic=True)
        if dim.get("understated"):
            count = (f"{dim.get('items_seen', 0)} ranked items \u00b7 "
                     "no estate-wide count recorded for this dimension")
        else:
            count = (f"{dim.get('total', 0):,} findings across the estate \u00b7 "
                     f"{dim.get('items_seen', 0)} ranked items carry one")
        self._text(s, cx + 0.3, cy + 0.86, cw - 0.6, 0.26, count,
                   size=11, color=p.TEXT_LO)
        rows = [[(e.get("name") or "")[:30],
                 (e.get("marketplace") or "")[:16],
                 ", ".join(e.get("matched") or [])[:38],
                 f"{int(e.get('endpoints') or 0):,}"]
                for e in dim["examples"][:4]]
        self._table(s, cx + 0.3, cy + 1.24, cw - 0.6,
                    ["Item", "Source", "Finding", "Hosts"], rows,
                    [(cw - 0.6) * 0.26, (cw - 0.6) * 0.17,
                     (cw - 0.6) * 0.44, (cw - 0.6) * 0.13],
                    row_h=0.52, max_rows=4)

    self._footer(s, "One item can carry several findings")
    return s


# -------------------------------------------------------------------- findings


def slides_findings(self):
    """The analyst's read. One finding per slide, laid out in two columns."""
    p = _pal(self)
    blocks = self.n.get("key_findings") or []
    if not blocks:
        return

    for i, block in enumerate(blocks):
        s = self._slide()
        self._header(
            s, "Findings \u2014 what the data means" if i == 0 else "Findings",
            f"{i + 1} of {len(blocks)}  \u00b7  each claim cites the collected "
            "data it rests on",
            tag="ANALYSIS", tag_color=p.AMBER)
        _finding_body(self, s, block, p)
        self._footer(s)


def _finding_body(self, s, block, p):
    top, bottom = 2.4, 10.5
    accent = {"critical": p.RED, "high": p.AMBER}.get(block["severity"], p.TEAL)

    self._pill(s, p.M, top, 1.55, 0.34, SEV_TAG.get(block["severity"], "MEDIUM"),
               accent, p.BG, 11.5)
    self._text(s, p.M + 1.7, top + 0.02, 8.0, 0.3,
               _tag_line([block["confidence"].upper()]
                         + list(block.get("mitre_techniques") or [])),
               size=11, color=p.TEXT_LO, anchor=MSO_ANCHOR.MIDDLE)

    title_h = _height(block["title"], p.CONTENT_W, 26)
    self._text(s, p.M, top + 0.52, p.CONTENT_W, title_h, block["title"],
               size=26, bold=True)
    y = top + 0.52 + title_h + 0.35

    left_w = p.CONTENT_W * 0.55
    right_x = p.M + left_w + 0.5
    right_w = p.CONTENT_W - left_w - 0.5

    narrative = block.get("narrative") or ""
    if narrative:
        h = min(_height(narrative, left_w, 14), bottom - y - 1.0)
        self._text(s, p.M, y, left_w, h, narrative, size=14,
                   color=p.TEXT_MID, line_spacing=1.25)
        y += h + 0.4
    if block.get("affected_scope"):
        self._card(s, p.M, y, left_w, 0.72, fill=p.BG_MUTED, border=None,
                   radius=0.06)
        self._text(s, p.M + 0.25, y + 0.2, left_w - 0.5, 0.34,
                   "Scope:  " + block["affected_scope"], size=12,
                   color=p.TEXT_LO, italic=True)

    entries = block.get("evidence") or []
    if not entries:
        return
    self._card(s, right_x, top + 0.52, right_w, bottom - top - 0.52)
    self._text(s, right_x + 0.32, top + 0.8, right_w - 0.64, 0.28, "EVIDENCE",
               size=10, bold=True, color=p.TEXT_LO)
    ey = top + 1.2
    for line in _evidence_lines(entries):
        h = _height(line, right_w - 0.95, 12.5)
        if ey + h > bottom - 0.3:
            break
        self._text(s, right_x + 0.32, ey, 0.28, 0.28, "\u25b8", size=12.5,
                   color=p.MINT)
        self._text(s, right_x + 0.68, ey, right_w - 1.0, h, line, size=12.5,
                   color=p.TEXT_MID, line_spacing=1.2)
        ey += h + 0.3


# ----------------------------------------------------------- attack scenarios


def slides_scenarios(self):
    """Illustrative paths, one per slide so the chain reads as a chain."""
    p = _pal(self)
    blocks = self.n.get("attack_scenarios") or []
    if not blocks:
        return

    for i, block in enumerate(blocks):
        s = self._slide()
        self._header(
            s, "Attack scenarios" if i == 0 else "Attack scenarios",
            f"{i + 1} of {len(blocks)}  \u00b7  paths an attacker could take "
            "given the observed exposure. Illustrative, not incidents that occurred.",
            tag="SCENARIOS", tag_color=p.AMBER)
        _scenario_body(self, s, block, p)
        self._footer(s)


def _scenario_body(self, s, block, p):
    top, bottom = 2.4, 10.5
    self._pill(s, p.M, top, 1.7, 0.34, block["likelihood"].upper(), p.AMBER,
               p.BG, 11.5)
    self._text(s, p.M + 1.85, top + 0.02, 8.0, 0.3,
               _tag_line(block.get("mitre_techniques") or []),
               size=11, color=p.TEXT_LO, anchor=MSO_ANCHOR.MIDDLE)

    title_h = _height(block["title"], p.CONTENT_W, 26)
    self._text(s, p.M, top + 0.52, p.CONTENT_W, title_h, block["title"],
               size=26, bold=True)
    y = top + 0.52 + title_h + 0.4

    left_w = p.CONTENT_W * 0.58
    right_x = p.M + left_w + 0.5
    right_w = p.CONTENT_W - left_w - 0.5

    steps = block.get("steps") or []
    for position, step in enumerate(steps[:6], start=1):
        h = max(0.42, _height(step, left_w - 0.75, 13.5))
        self._text(s, p.M, y, 0.5, 0.32, f"{position}.", size=15, bold=True,
                   color=p.MINT)
        self._text(s, p.M + 0.55, y, left_w - 0.75, h, str(step), size=13.5,
                   color=p.TEXT_MID, line_spacing=1.2)
        y += h + 0.34

    cursor = top + 0.52
    if block.get("impact"):
        h = _height(block["impact"], right_w - 0.7, 13) + 0.9
        self._card(s, right_x, cursor, right_w, h, fill=p.BG_CARD)
        self._text(s, right_x + 0.32, cursor + 0.26, right_w - 0.64, 0.28,
                   "IMPACT", size=10, bold=True, color=p.TEXT_LO)
        self._text(s, right_x + 0.32, cursor + 0.62, right_w - 0.64, h - 0.85,
                   block["impact"], size=13, color=p.WHITE, line_spacing=1.2)
        cursor += h + 0.35
    if block.get("breaks_at"):
        h = _height(block["breaks_at"], right_w - 0.7, 13) + 0.9
        self._card(s, right_x, cursor, right_w, h, fill=p.BG_MUTED,
                   border=p.MINT, radius=0.05)
        self._text(s, right_x + 0.32, cursor + 0.26, right_w - 0.64, 0.28,
                   "WHAT BREAKS THIS CHAIN", size=10, bold=True, color=p.MINT)
        self._text(s, right_x + 0.32, cursor + 0.62, right_w - 0.64, h - 0.85,
                   block["breaks_at"], size=13, color=p.MINT, line_spacing=1.2)
        cursor += h + 0.35

    entries = block.get("enabling_evidence") or []
    if entries and cursor < bottom - 1.0:
        self._text(s, right_x, cursor + 0.1, right_w, 0.28, "EVIDENCE",
                   size=10, bold=True, color=p.TEXT_LO)
        cursor += 0.46
        for line in _evidence_lines(entries, limit=4):
            h = _height(line, right_w - 0.4, 11.5)
            if cursor + h > bottom - 0.2:
                break
            self._text(s, right_x, cursor, right_w, h, "\u25b8  " + line,
                       size=11.5, color=p.TEXT_MID, line_spacing=1.15)
            cursor += h + 0.22


# --------------------------------------------------------------------- actions


def slides_actions(self):
    """Recommended actions, ordered by risk reduced, two per slide."""
    p = _pal(self)
    blocks = self.n.get("recommended_actions") or []
    if not blocks:
        return

    for page, pair in enumerate(_chunk(blocks, 2)):
        s = self._slide()
        self._header(
            s, "Recommended actions" if page == 0 else
            "Recommended actions (continued)",
            "Ordered by risk reduced, not by ease of implementation",
            tag="ACTIONS", tag_color=p.MINT)

        cw = (p.CONTENT_W - 0.45) / 2
        for i, block in enumerate(pair):
            _action_card(self, s, p.M + i * (cw + 0.45), 2.45, cw, 8.0, block, p)
        self._footer(s)


def _action_card(self, s, x, y, w, h, block, p):
    self._card(s, x, y, w, h)
    self._text(s, x + 0.35, y + 0.3, 0.9, 0.8, str(block.get("priority", 1)),
               size=40, bold=True, color=p.MINT)
    title_h = _height(block["title"], w - 1.7, 19)
    self._text(s, x + 1.3, y + 0.36, w - 1.7, title_h, block["title"],
               size=19, bold=True)
    self._pill(s, x + 1.3, y + 0.42 + title_h, 2.1, 0.32,
               block["effort"].upper() + " EFFORT", p.BG_MUTED, p.TEXT_MID, 10.5)

    cursor = y + 1.0 + title_h + 0.35
    if block.get("rationale"):
        bh = _height(block["rationale"], w - 0.7, 13.5)
        self._text(s, x + 0.35, cursor, w - 0.7, bh, block["rationale"],
                   size=13.5, color=p.TEXT_MID, line_spacing=1.22)
        cursor += bh + 0.4
    if block.get("expected_outcome"):
        bh = _height(block["expected_outcome"], w - 0.7, 13.5) + 0.85
        self._card(s, x + 0.35, cursor, w - 0.7, bh, fill=p.BG_MUTED,
                   border=None, radius=0.06)
        self._text(s, x + 0.6, cursor + 0.22, w - 1.2, 0.26, "OUTCOME",
                   size=9.5, bold=True, color=p.TEXT_LO)
        self._text(s, x + 0.6, cursor + 0.56, w - 1.2, bh - 0.78,
                   block["expected_outcome"], size=13.5, color=p.WHITE,
                   line_spacing=1.2)
        cursor += bh + 0.35
    if block.get("platform_capability"):
        self._text(s, x + 0.35, y + h - 0.62, w - 0.7, 0.4,
                   "Platform capability:  " + block["platform_capability"],
                   size=11, color=p.TEXT_LO, italic=True)


# -------------------------------------------------------------- threat context


def slide_threat_context(self):
    """Public threat activity, fenced off from anything tenant-derived."""
    p = _pal(self)
    blocks = self.n.get("threat_context") or []
    if not blocks:
        return

    s = self._slide()
    self._header(s, "Threat context", "Related public threat activity",
                 tag="CONTEXT", tag_color=p.TEXT_LO)
    self._card(s, p.M, 2.3, p.CONTENT_W, 0.66, fill=p.BG_MUTED,
               border=p.AMBER, radius=0.05)
    self._text(s, p.M + 0.3, 2.48, p.CONTENT_W - 0.6, 0.34,
               "NOT verified against your tenant. Publicly reported activity, "
               "provided for context only. Every preceding slide is traced to "
               "data collected from your environment.",
               size=12, color=p.AMBER)

    cw = (p.CONTENT_W - 0.4) / 2
    ch = 3.55
    for i, block in enumerate(blocks[:4]):
        cx = p.M + (i % 2) * (cw + 0.4)
        cy = 3.25 + (i // 2) * (ch + 0.35)
        self._card(s, cx, cy, cw, ch)
        th = _height(block["campaign_or_pattern"], cw - 0.6, 16)
        self._text(s, cx + 0.3, cy + 0.28, cw - 0.6, th,
                   block["campaign_or_pattern"], size=16, bold=True, color=p.TEAL)
        self._text(s, cx + 0.3, cy + 0.34 + th + 0.24, cw - 0.6,
                   ch - th - 0.9, block["relevance"], size=12.5,
                   color=p.TEXT_MID, line_spacing=1.22)
    self._footer(s)
    return s


def attach(cls) -> None:
    """Bind the analytical slides onto DeckBuilder."""
    cls.slide_supply_chain = slide_supply_chain
    cls.slide_supply_chain_items = slide_supply_chain_items
    cls.slides_findings = slides_findings
    cls.slides_scenarios = slides_scenarios
    cls.slides_actions = slides_actions
    cls.slide_threat_context = slide_threat_context
