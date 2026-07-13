"""Render a tailored resume (Markdown) to an ATS-friendly PDF (LLD §5, C7).

Uses fpdf2 (pure Python, no system libs). Output is real selectable text with a
standard font, so ATS resume parsers can read it — not an image. The tailored
resumes we produce are simple Markdown (# / ## / ### headings, - bullets,
**bold**), which this renders directly."""

from __future__ import annotations

import re
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos

_BULLET = re.compile(r"^\s*[-*•·]\s+")

# Core PDF fonts are Latin-1 only; map common smart punctuation to ASCII so the
# renderer never crashes on curly quotes / em dashes / bullets from the model.
_SUBS = {
    "’": "'", "‘": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "•": "-", " ": " ",
    "…": "...", "→": "->",
}


def _latin1(s: str) -> str:
    for k, v in _SUBS.items():
        s = s.replace(k, v)
    return s.encode("latin-1", "replace").decode("latin-1")


def _write(pdf: FPDF, h: float, text: str) -> None:
    """Write a full-width line and return the cursor to the left margin on the
    next line (fpdf2 otherwise leaves x at the right edge). Tolerates malformed
    inline markdown by retrying without it."""
    kw = dict(new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    try:
        pdf.multi_cell(0, h, _latin1(text), markdown=True, **kw)
    except Exception:
        pdf.multi_cell(0, h, _latin1(text), **kw)


def _build(md: str) -> FPDF:
    pdf = FPDF(format="letter")
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.set_margins(18, 16, 18)
    pdf.add_page()
    for raw in (md or "").splitlines():
        line = raw.rstrip()
        if not line.strip():
            pdf.ln(2.5)
            continue
        if line.startswith("# "):
            pdf.set_font("Helvetica", "B", 18); _write(pdf, 8, line[2:].strip()); pdf.ln(1)
        elif line.startswith("## "):
            pdf.ln(2); pdf.set_font("Helvetica", "B", 13); _write(pdf, 7, line[3:].strip())
        elif line.startswith("### "):
            pdf.set_font("Helvetica", "B", 11); _write(pdf, 6, line[4:].strip())
        elif _BULLET.match(line):
            pdf.set_font("Helvetica", "", 10.5)
            _write(pdf, 5.5, "-  " + _BULLET.sub("", line))
        else:
            pdf.set_font("Helvetica", "", 10.5); _write(pdf, 5.5, line)
    return pdf


def render_to_bytes(md: str) -> bytes:
    return bytes(_build(md).output())


def render_markdown_pdf(md: str, out_path: str | Path) -> Path:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    _build(md).output(str(out))
    return out
