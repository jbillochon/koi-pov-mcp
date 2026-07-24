"""
Deliverable rendering, Cortex-themed.

Ported from jbillochon/povplatform (rendering/deck.py, rendering/report.py):
same palette, same slide and section structure, same native-shape approach.
The PDF path is the one deliberate departure: povplatform renders it through
WeasyPrint, which needs system GTK and therefore fails on a plain Windows
workstation, so the PDF is drawn with reportlab against the same print
palette.

Additions specific to this project: a success-criteria scorecard, threat
intelligence sections (KEV / EPSS / CVSS, OSV, ATT&CK), and null-awareness -
a figure whose domain was never collected reads "not measured", never 0.
"""

from __future__ import annotations

from pathlib import Path

from .deck import build_deck
from .docx_report import build_docx
from .pdf_report import build_pdf

__all__ = ["render", "build_deck", "build_docx", "build_pdf"]


def render(data: dict, out_dir: Path, formats: list[str],
           executive_summary: str = "", recommendations: str = "",
           success_criteria: list[dict] | None = None) -> dict:
    """Render the requested formats. Returns {'produced': {...}, 'skipped': {...}}."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    produced: dict[str, str] = {}
    skipped: dict[str, str] = {}

    narrative = {
        "executive_summary": (executive_summary or "").strip(),
        "recommendations": (recommendations or "").strip(),
        "success_criteria": success_criteria or [],
    }

    builders = {
        "pptx": ("deck.pptx", build_deck),
        "docx": ("report.docx", build_docx),
        "pdf": ("report.pdf", build_pdf),
    }

    for fmt in formats:
        fmt = fmt.lower().strip()
        if fmt not in builders:
            skipped[fmt] = "unknown format (docx, pptx, pdf)"
            continue
        filename, builder = builders[fmt]
        try:
            builder(data, str(out_dir / filename), narrative)
            produced[fmt] = str(out_dir / filename)
        except ImportError as exc:
            skipped[fmt] = f"missing dependency: {exc}"
        except Exception as exc:  # noqa: BLE001 - one format must not sink the others
            skipped[fmt] = f"{type(exc).__name__}: {exc}"

    return {"produced": produced, "skipped": skipped}
