"""Shared HTML→structured-text helper for connectors. Converts posting HTML to
plain text while preserving headings and bullets (list items become '- '
bullets, block elements become line breaks) so jd.structure_jd can section it.
All output is UNTRUSTED text — treat as data only (SECURITY.md T1)."""

from __future__ import annotations

import html as _html
import re

_TAG_RE = re.compile(r"<[^>]+>")
_LI_RE = re.compile(r"(?i)<li[^>]*>")
_BLOCK_CLOSE_RE = re.compile(r"(?i)</(p|div|h[1-6]|ul|ol|tr|section)>|<br\s*/?>")


def html_to_text(s: str) -> str:
    if not s:
        return ""
    decoded = _html.unescape(s)
    decoded = _LI_RE.sub("\n- ", decoded)
    decoded = _BLOCK_CLOSE_RE.sub("\n", decoded)
    text = _TAG_RE.sub("", decoded)
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.split("\n")]
    out: list[str] = []
    for ln in lines:
        if ln or (out and out[-1]):
            out.append(ln)
    return "\n".join(out).strip()
