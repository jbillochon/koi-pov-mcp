"""
Analytical slides for the deck.

The deck already carried the data layer: discovery, risk, governance,
remediation, agentic activity. What it lacked, and what the PoV platform's
deck has, is the layer that says what the data means.

Three rules earned by putting a first attempt side by side with the
platform's deck:

* **Full-width horizontal bands, several per slide.** A two-column layout with
  one item per slide halves the text measure, so a paragraph that fills three
  lines across the slide sprawls over eight in a narrow column and the other
  half of the slide sits empty. Bands running the full 18.5in carry three
  findings or two scenarios per slide with no dead space.
* **Carry the substance, not the label.** Every evidence entry has a reference
  and a note, and the note is where the specificity lives. Evidence renders as
  one compact inline row, not a card of its own.
* **Lay out to the content.** Blocks advance a cursor by their own estimated
  height rather than sitting on a fixed grid.

These are free functions attached to DeckBuilder by attach(), so deck.py keeps
one class and this file can grow without it.

Nothing here computes a figure. Counts come from supply_chain.py, prose from
the verified narrative.
"""

from __future__ import annotations

from pptx.enum.text import MSO_ANCHOR, PP_ALIGN

SEV_TAG = {"critical": "CRITICAL", "high": "HIGH", "medium": "MEDIUM",
           "low": "LOW", "info": "INFO"}

TOP, BOTTOM = 2.25, 10.6


def _pal(self):
    """The palette lives in deck.py; fetch it lazily to avoid a cycle."""
    from . import deck as _d
    return _d


def _chunk(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _height(text, width_in, size_pt, line_spacing=1.2):
    """Estimate the height wrapped text needs, in inches. Slightly generous."""
    if not text:
        return 0.0
    chars_per_line = max(12, int(width_in * 72.0 / (size_pt * 0.495)))
    lines = 0
    for paragraph in str(text).split("\n"):
        lines += max(1, -(-len(paragraph) // chars_per_line))
    return lines * (size_pt * line_spacing) / 72.0


def _accent(p, severity):
    return {"critical": p.RED, "high": p.AMBER, "medium": p.TEAL}.get(
        severity, p.TEAL)


def _evidence_row(entries, limit=4):
    """One compact line: the references, then how many were left out."""
    shown = [str(e.get("reference", "")) for e in entries[:limit]
             if e.get("reference")]
    if not shown:
        return ""
    line = "Evidence:   " + "   \u00b7   ".join(shown)
    extra = len(entries) - len(shown)
    if extra > 0:
        line += f"   (+{extra} more)"
    return line


def _bar(self, s, x, y, h, colour):
    """The severity rule down the left edge of a band."""
    sh = s.shapes.add_shape(1, self._in(x), self._in(y), self._in(0.07),
                            self._in(h)) if hasattr(self, "_in") else None
    if sh is None:
        from pptx.enum.shapes import MSO_SHAPE
        from pptx.util import Inches
        sh = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y),
                                Inches(0.07), Inches(h))
    sh.fill.solid()
    sh.fill.fore_color.rgb = colour
    sh.line.fill.background()
    self._no_shadow(sh)
    return sh


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
    """Three findings per slide, each a full-width band."""
    p = _pal(self)
    blocks = self.n.get("key_findings") or []
    if not blocks:
        return

    pages = list(_chunk(blocks, 3))
    for page, group in enumerate(pages):
        s = self._slide()
        title = "Key findings"
        if len(pages) > 1:
            title += f" ({page + 1}/{len(pages)})"
        self._header(s, title, "Each finding cites the collected data it rests on",
                     tag="FINDINGS", tag_color=p.AMBER)

        band_h = (BOTTOM - TOP - 0.3 * (len(group) - 1)) / max(len(group), 1)
        band_h = min(band_h, 3.4)
        for i, block in enumerate(group):
            _finding_band(self, s, TOP + i * (band_h + 0.3), band_h, block, p)
        self._footer(s, "Claims that could not be traced to the data were removed")


def _finding_band(self, s, y, h, block, p):
    accent = _accent(p, block["severity"])
    self._card(s, p.M, y, p.CONTENT_W, h)
    _bar(self, s, p.M, y, h, accent)

    x = p.M + 0.55
    inner = p.CONTENT_W - 1.1

    self._text(s, x, y + 0.24, inner * 0.62, 0.42, block["title"],
               size=19, bold=True)
    self._pill(s, p.M + p.CONTENT_W * 0.655, y + 0.26, 1.45, 0.32,
               SEV_TAG.get(block["severity"], "MEDIUM"), accent, p.BG, 11)
    self._text(s, p.M + p.CONTENT_W * 0.655 + 1.6, y + 0.28, 1.6, 0.3,
               block["confidence"].capitalize(), size=11, color=p.TEXT_MID,
               anchor=MSO_ANCHOR.MIDDLE)
    mitre = block.get("mitre_techniques") or []
    if mitre:
        self._text(s, p.M + p.CONTENT_W - 5.2, y + 0.28, 4.8, 0.3,
                   "   ".join(mitre), size=10.5, color=p.TEAL,
                   align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.MIDDLE)

    cursor = y + 0.78
    narrative = block.get("narrative") or ""
    if narrative:
        nh = min(_height(narrative, inner, 12.5), h - 1.5)
        self._text(s, x, cursor, inner, nh, narrative, size=12.5,
                   color=p.TEXT_MID, line_spacing=1.22)
        cursor += nh + 0.16
    if block.get("affected_scope"):
        self._text(s, x, cursor, inner, 0.28,
                   "Scope:  " + block["affected_scope"], size=11,
                   color=p.TEXT_LO, italic=True)

    row = _evidence_row(block.get("evidence") or [])
    if row:
        self._text(s, x, y + h - 0.52, inner, 0.32, row, size=10.5,
                   color=p.MINT, italic=True)


# ----------------------------------------------------------- attack scenarios


def slides_scenarios(self):
    """Two scenarios per slide, each a full-width band."""
    p = _pal(self)
    blocks = self.n.get("attack_scenarios") or []
    if not blocks:
        return

    pages = list(_chunk(blocks, 2))
    for page, group in enumerate(pages):
        s = self._slide()
        title = "Attack scenarios"
        if len(pages) > 1:
            title += f" ({page + 1}/{len(pages)})"
        self._header(s, title,
                     "Hypothetical paths, built only from exposure observed "
                     "in this tenant", tag="SCENARIOS", tag_color=p.RED)

        band_h = (BOTTOM - TOP - 0.3 * (len(group) - 1)) / max(len(group), 1)
        band_h = min(band_h, 4.4)
        for i, block in enumerate(group):
            _scenario_band(self, s, TOP + i * (band_h + 0.3), band_h, block, p)
        self._footer(s, "Scenarios are illustrative, not observed incidents")


def _scenario_band(self, s, y, h, block, p):
    self._card(s, p.M, y, p.CONTENT_W, h)
    x = p.M + 0.55
    left_w = p.CONTENT_W * 0.56
    right_x = p.M + p.CONTENT_W * 0.60
    right_w = p.CONTENT_W * 0.36

    self._text(s, x, y + 0.24, left_w, 0.42, block["title"], size=19, bold=True)
    self._pill(s, p.M + p.CONTENT_W - 1.9, y + 0.26, 1.5, 0.32,
               block["likelihood"].upper(), p.AMBER, p.BG, 11)
    mitre = block.get("mitre_techniques") or []
    if mitre:
        self._text(s, right_x, y + 0.28, right_w - 1.7, 0.3, "   ".join(mitre),
                   size=10.5, color=p.TEAL, align=PP_ALIGN.RIGHT,
                   anchor=MSO_ANCHOR.MIDDLE)

    cursor = y + 0.85
    for position, step in enumerate(block.get("steps") or [], start=1):
        sh = max(0.3, _height(step, left_w - 0.5, 12))
        if cursor + sh > y + h - 0.7:
            break
        self._text(s, x, cursor, 0.35, 0.28, str(position), size=12.5,
                   bold=True, color=p.RED)
        self._text(s, x + 0.42, cursor, left_w - 0.5, sh, str(step), size=12,
                   color=p.TEXT_MID, line_spacing=1.2)
        cursor += sh + 0.14

    row = _evidence_row(block.get("enabling_evidence") or [])
    if row:
        self._text(s, x, y + h - 0.5, left_w, 0.3, row, size=10.5,
                   color=p.MINT, italic=True)

    ry = y + 0.85
    if block.get("impact"):
        self._text(s, right_x, ry, right_w, 0.26, "IMPACT", size=9.5,
                   bold=True, color=p.RED)
        ih = _height(block["impact"], right_w, 12)
        self._text(s, right_x, ry + 0.32, right_w, ih, block["impact"],
                   size=12, color=p.TEXT_MID, line_spacing=1.2)
        ry += 0.32 + ih + 0.3
    if block.get("breaks_at"):
        bh = _height(block["breaks_at"], right_w - 0.5, 11.5) + 0.72
        bh = min(bh, y + h - ry - 0.3)
        self._card(s, right_x, ry, right_w, bh, fill=p.BG_MUTED,
                   border=p.MINT, radius=0.05)
        self._text(s, right_x + 0.25, ry + 0.18, right_w - 0.5, 0.24,
                   "BREAKS AT", size=9.5, bold=True, color=p.MINT)
        self._text(s, right_x + 0.25, ry + 0.48, right_w - 0.5, bh - 0.6,
                   block["breaks_at"], size=11.5, color=p.WHITE,
                   line_spacing=1.18)


# --------------------------------------------------------------------- actions


def slides_actions(self):
    """Six actions per slide, two columns of three."""
    p = _pal(self)
    blocks = self.n.get("recommended_actions") or []
    if not blocks:
        return

    for page, group in enumerate(_chunk(blocks, 6)):
        s = self._slide()
        self._header(
            s, "Recommended actions" if page == 0 else
            "Recommended actions (continued)",
            "Ordered by risk reduced, not by ease of implementation",
            tag="NEXT STEPS", tag_color=p.MINT)

        cw = (p.CONTENT_W - 0.45) / 2
        rows = -(-len(group) // 2)
        ch = min(2.62, (BOTTOM - TOP - 0.28 * (rows - 1)) / max(rows, 1))
        for i, block in enumerate(group):
            cx = p.M + (i % 2) * (cw + 0.45)
            cy = TOP + (i // 2) * (ch + 0.28)
            _action_card(self, s, cx, cy, cw, ch, block, p)
        self._footer(s)


def _action_card(self, s, x, y, w, h, block, p):
    self._card(s, x, y, w, h)
    self._text(s, x + 0.32, y + 0.2, 0.7, 0.6, str(block.get("priority", 1)),
               size=26, bold=True, color=p.MINT)

    effort_w = 1.75
    title_w = w - 1.15 - effort_w - 0.5
    title_h = _height(block["title"], title_w, 16)
    self._text(s, x + 1.05, y + 0.26, title_w, title_h, block["title"],
               size=16, bold=True)
    self._pill(s, x + w - effort_w - 0.32, y + 0.26, effort_w, 0.3,
               block["effort"].upper() + " EFFORT", p.BG_MUTED, p.TEXT_MID, 9.5)

    cursor = y + 0.34 + max(title_h, 0.36) + 0.18
    body = block.get("rationale") or ""
    if block.get("expected_outcome"):
        body = (body + "  " if body else "") + block["expected_outcome"]
    if body:
        bh = min(_height(body, w - 1.4, 11.5), y + h - cursor - 0.62)
        self._text(s, x + 1.05, cursor, w - 1.4, bh, body, size=11.5,
                   color=p.TEXT_MID, line_spacing=1.2)
    if block.get("platform_capability"):
        self._text(s, x + 1.05, y + h - 0.48, w - 1.4, 0.3,
                   "\u2192  " + block["platform_capability"], size=10.5,
                   color=p.MINT, italic=True)


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
    rows = -(-min(len(blocks), 4) // 2)
    ch = min(3.55, (BOTTOM - 3.25 - 0.35 * (rows - 1)) / max(rows, 1))
    for i, block in enumerate(blocks[:4]):
        cx = p.M + (i % 2) * (cw + 0.4)
        cy = 3.25 + (i // 2) * (ch + 0.35)
        self._card(s, cx, cy, cw, ch)
        th = _height(block["campaign_or_pattern"], cw - 0.6, 15.5)
        self._text(s, cx + 0.3, cy + 0.26, cw - 0.6, th,
                   block["campaign_or_pattern"], size=15.5, bold=True,
                   color=p.TEAL)
        self._text(s, cx + 0.3, cy + 0.32 + th + 0.2, cw - 0.6,
                   ch - th - 0.85, block["relevance"], size=12,
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
