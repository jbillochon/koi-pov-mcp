"""
Analytical slides for the deck.

The deck already carried the data layer: discovery, risk, governance,
remediation, agentic activity. What it lacked, and what the PoV platform's
deck has, is the layer that says what the data means: where the software comes
from, what the analyst concluded, how an attacker could use it, and what to do
first.

These are written as free functions and attached to DeckBuilder by attach(),
so deck.py keeps one class and this file can grow without it.

Nothing here computes a figure. Counts come from supply_chain.py, prose from
the verified narrative.
"""

from __future__ import annotations

from pptx.enum.text import MSO_ANCHOR, PP_ALIGN

SEV_TAG = {"critical": "CRITICAL", "high": "HIGH", "medium": "MEDIUM",
           "low": "LOW", "info": "INFO"}


def _pal(d):
    """The palette lives in deck.py; fetch it lazily to avoid a cycle."""
    from . import deck as _d
    return _d


def _chunk(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _tag_line(labels):
    return "   \u00b7   ".join(x for x in labels if x)


# --------------------------------------------------------------- supply chain


def slide_supply_chain(self):
    """Where software enters the estate, and how concentrated its supply is."""
    p = _pal(self)
    view = (self.n.get("supply_chain") or {})
    channels = view.get("channels") or []
    profile = view.get("publishers") or {}
    if not channels:
        return

    s = self._slide()
    self._header(s, "Software supply chain \u2014 where it comes from",
                 "Every marketplace is a separate trust decision",
                 tag="SUPPLY CHAIN", tag_color=p.TEAL)

    total = sum(c["total"] for c in channels)
    y = 2.5
    cw = (p.CONTENT_W - 2 * 0.35) / 3
    self._kpi(s, p.M, y, cw, 2.2, f"{profile.get('items', 0):,}",
              "Items in the estate", "across every marketplace", p.MINT)
    self._kpi(s, p.M + cw + 0.35, y, cw, 2.2, f"{profile.get('publishers', 0):,}",
              "Distinct publishers", "each one a trust decision", p.TEAL)
    ratio = profile.get("items_per_publisher")
    self._kpi(s, p.M + 2 * (cw + 0.35), y, cw, 2.2,
              f"{ratio:.1f}" if ratio else "\u2014",
              "Items per publisher", "lower means more parties to trust", p.TEAL)

    y = 5.1
    self._text(s, p.M, y, p.CONTENT_W, 0.32,
               "How software enters the estate", size=15, bold=True, color=p.TEAL)
    rows = [[c["label"],
             ", ".join(n for n, _ in c["members"])[:58],
             f"{c['total']:,}",
             f"{100 * c['total'] / total:.1f}%" if total else "\u2014"]
            for c in channels]
    self._table(s, p.M, y + 0.45, p.CONTENT_W,
                ["Channel", "Sources", "Items", "Share"], rows,
                [5.0, 9.0, 2.4, 2.1], max_rows=8)

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

    y = 2.45
    cw = (p.CONTENT_W - 0.4) / 2
    ch = 3.9
    for i, dim in enumerate(dims[:4]):
        cx = p.M + (i % 2) * (cw + 0.4)
        cy = y + (i // 2) * (ch + 0.35)
        self._card(s, cx, cy, cw, ch)
        self._text(s, cx + 0.3, cy + 0.24, cw - 0.6, 0.3, dim["label"],
                   size=15, bold=True, color=p.TEAL)
        if dim.get("understated"):
            count = (f"{dim.get('items_seen', 0)} ranked items \u00b7 "
                     "no estate-wide count recorded")
        else:
            count = (f"{dim.get('total', 0):,} findings \u00b7 "
                     f"{dim.get('items_seen', 0)} ranked items")
        self._text(s, cx + 0.3, cy + 0.58, cw - 0.6, 0.26, count,
                   size=11, color=p.TEXT_LO)
        rows = [[(e.get("name") or "")[:30],
                 (e.get("marketplace") or "")[:16],
                 ", ".join(e.get("matched") or [])[:34],
                 f"{int(e.get('endpoints') or 0):,}"]
                for e in dim["examples"][:4]]
        self._table(s, cx + 0.3, cy + 0.95, cw - 0.6,
                    ["Item", "Source", "Finding", "Hosts"], rows,
                    [(cw - 0.6) * 0.27, (cw - 0.6) * 0.18,
                     (cw - 0.6) * 0.42, (cw - 0.6) * 0.13],
                    row_h=0.5, max_rows=4)

    self._footer(s, "One item can carry several findings")
    return s


# -------------------------------------------------------------------- findings


def slides_findings(self):
    """The analyst's read, two findings per slide, each carrying its evidence."""
    p = _pal(self)
    blocks = self.n.get("key_findings") or []
    if not blocks:
        return

    for page, pair in enumerate(_chunk(blocks, 2)):
        s = self._slide()
        self._header(
            s, "Findings \u2014 what the data means" if page == 0 else
            "Findings (continued)",
            "Each claim cites the collected data it rests on",
            tag="ANALYSIS", tag_color=p.AMBER)

        cw = (p.CONTENT_W - 0.4) / 2
        for i, block in enumerate(pair):
            cx = p.M + i * (cw + 0.4)
            _finding_card(self, s, cx, 2.45, cw, 8.0, block, p)
        self._footer(s)


def _finding_card(self, s, x, y, w, h, block, p):
    accent = {"critical": p.RED, "high": p.AMBER}.get(block["severity"], p.TEAL)
    self._card(s, x, y, w, h)
    self._pill(s, x + 0.3, y + 0.28, 1.5, 0.32,
               SEV_TAG.get(block["severity"], "MEDIUM"), accent, p.BG, 11)
    self._text(s, x + 1.95, y + 0.3, w - 2.25, 0.3,
               _tag_line([block["confidence"].upper()]
                         + list(block.get("mitre_techniques") or [])),
               size=10, color=p.TEXT_LO, anchor=MSO_ANCHOR.MIDDLE)
    self._text(s, x + 0.3, y + 0.78, w - 0.6, 0.8, block["title"],
               size=17, bold=True)

    cursor = y + 1.7
    if block.get("narrative"):
        self._text(s, x + 0.3, cursor, w - 0.6, 3.1, block["narrative"][:620],
                   size=12, color=p.TEXT_MID, line_spacing=1.15)
        cursor += 3.25
    if block.get("affected_scope"):
        self._text(s, x + 0.3, cursor, w - 0.6, 0.5,
                   "Scope: " + block["affected_scope"][:150],
                   size=11, color=p.TEXT_LO, italic=True)
        cursor += 0.62

    evidence = block.get("evidence") or []
    if evidence:
        self._text(s, x + 0.3, cursor, w - 0.6, 0.26, "EVIDENCE",
                   size=9, bold=True, color=p.TEXT_LO)
        cursor += 0.34
        for entry in evidence[:4]:
            line = "\u25b8  " + str(entry.get("reference", ""))[:66]
            self._text(s, x + 0.3, cursor, w - 0.6, 0.28, line,
                       size=10.5, color=p.TEXT_MID)
            cursor += 0.34


# ----------------------------------------------------------- attack scenarios


def slides_scenarios(self):
    """Illustrative paths, labelled as such, two per slide."""
    p = _pal(self)
    blocks = self.n.get("attack_scenarios") or []
    if not blocks:
        return

    for page, pair in enumerate(_chunk(blocks, 2)):
        s = self._slide()
        self._header(
            s, "Attack scenarios" if page == 0 else "Attack scenarios (continued)",
            "Paths an attacker could take given the observed exposure. "
            "Illustrative, not incidents that occurred.",
            tag="SCENARIOS", tag_color=p.AMBER)

        cw = (p.CONTENT_W - 0.4) / 2
        for i, block in enumerate(pair):
            cx = p.M + i * (cw + 0.4)
            _scenario_card(self, s, cx, 2.45, cw, 8.0, block, p)
        self._footer(s)


def _scenario_card(self, s, x, y, w, h, block, p):
    self._card(s, x, y, w, h)
    self._pill(s, x + 0.3, y + 0.28, 1.6, 0.32, block["likelihood"].upper(),
               p.AMBER, p.BG, 11)
    self._text(s, x + 2.05, y + 0.3, w - 2.35, 0.3,
               _tag_line(block.get("mitre_techniques") or []),
               size=10, color=p.TEXT_LO, anchor=MSO_ANCHOR.MIDDLE)
    self._text(s, x + 0.3, y + 0.78, w - 0.6, 0.7, block["title"],
               size=17, bold=True)

    cursor = y + 1.6
    for position, step in enumerate(block["steps"][:5], start=1):
        self._text(s, x + 0.3, cursor, 0.32, 0.3, str(position) + ".",
                   size=11.5, bold=True, color=p.MINT)
        self._text(s, x + 0.68, cursor, w - 1.0, 0.9, str(step)[:190],
                   size=11.5, color=p.TEXT_MID, line_spacing=1.1)
        cursor += 0.92

    if block.get("impact"):
        self._text(s, x + 0.3, cursor, w - 0.6, 0.8,
                   "Impact.  " + block["impact"][:210],
                   size=11.5, color=p.WHITE, line_spacing=1.1)
        cursor += 0.9
    if block.get("breaks_at"):
        self._card(s, x + 0.3, cursor, w - 0.6, 1.0, fill=p.BG_MUTED,
                   border=p.MINT, radius=0.06)
        self._text(s, x + 0.5, cursor + 0.16, w - 1.0, 0.7,
                   "What breaks this chain.  " + block["breaks_at"][:190],
                   size=11, color=p.MINT, line_spacing=1.1)


# --------------------------------------------------------------------- actions


def slides_actions(self):
    """Recommended actions, ordered by risk reduced."""
    p = _pal(self)
    blocks = self.n.get("recommended_actions") or []
    if not blocks:
        return

    for page, group in enumerate(_chunk(blocks, 4)):
        s = self._slide()
        self._header(
            s, "Recommended actions" if page == 0 else
            "Recommended actions (continued)",
            "Ordered by risk reduced, not by ease of implementation",
            tag="NEXT STEPS", tag_color=p.MINT)

        cw = (p.CONTENT_W - 0.4) / 2
        ch = 3.9
        for i, block in enumerate(group):
            cx = p.M + (i % 2) * (cw + 0.4)
            cy = 2.45 + (i // 2) * (ch + 0.35)
            rank = block.get("priority", i + 1 + page * 4)
            self._card(s, cx, cy, cw, ch)
            self._text(s, cx + 0.32, cy + 0.24, 0.6, 0.5, str(rank),
                       size=30, bold=True, color=p.MINT)
            self._text(s, cx + 1.0, cy + 0.3, cw - 1.3, 0.8, block["title"],
                       size=16, bold=True)
            self._pill(s, cx + 1.0, cy + 1.15, 1.9, 0.3,
                       block["effort"].upper() + " EFFORT", p.BG_MUTED, p.TEXT_MID, 10)
            cursor = cy + 1.65
            if block.get("rationale"):
                self._text(s, cx + 0.32, cursor, cw - 0.64, 1.3,
                           block["rationale"][:290], size=11.5,
                           color=p.TEXT_MID, line_spacing=1.1)
                cursor += 1.4
            if block.get("expected_outcome"):
                self._text(s, cx + 0.32, cursor, cw - 0.64, 0.9,
                           block["expected_outcome"][:200], size=11.5,
                           color=p.WHITE, line_spacing=1.1)
                cursor += 0.95
            if block.get("platform_capability"):
                self._text(s, cx + 0.32, cy + ch - 0.5, cw - 0.64, 0.3,
                           block["platform_capability"][:80],
                           size=10, color=p.TEXT_LO, italic=True)
        self._footer(s)


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
    self._card(s, p.M, 2.3, p.CONTENT_W, 0.62, fill=p.BG_MUTED,
               border=p.AMBER, radius=0.05)
    self._text(s, p.M + 0.3, 2.46, p.CONTENT_W - 0.6, 0.32,
               "NOT verified against your tenant. Publicly reported activity, "
               "for context only. Every preceding slide is traced to collected data.",
               size=11.5, color=p.AMBER)

    cw = (p.CONTENT_W - 0.4) / 2
    ch = 3.6
    for i, block in enumerate(blocks[:4]):
        cx = p.M + (i % 2) * (cw + 0.4)
        cy = 3.2 + (i // 2) * (ch + 0.35)
        self._card(s, cx, cy, cw, ch)
        self._text(s, cx + 0.3, cy + 0.26, cw - 0.6, 0.8,
                   block["campaign_or_pattern"], size=15, bold=True, color=p.TEAL)
        self._text(s, cx + 0.3, cy + 1.15, cw - 0.6, ch - 1.45,
                   block["relevance"][:540], size=11.5, color=p.TEXT_MID,
                   line_spacing=1.15)
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
