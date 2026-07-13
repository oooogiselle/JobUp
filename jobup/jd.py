"""Structure a plain-text job description into sections for display (dashboard).

Rules-based and offline: it groups lines under detected headings (known JD
headings, or short lines that look like headings) and marks bullets vs prose.
An LLM structurer could replace this later, but rules keep it free and testable."""

from __future__ import annotations

import re

# Common JD section headings (matched case-insensitively, anchored to the line).
_KNOWN = re.compile(
    r"(?i)^(about( the (role|team|company|job))?|the role|who (you are|we are)|"
    r"what you('|)ll do|what you will do|responsibilities|"
    r"(minimum |basic |preferred )?qualifications|requirements|"
    r"nice to have|bonus|skills|experience|benefits|perks|"
    r"compensation|salary|pay range|equal opportunity|eeo|how to apply)\b[:\s]*$"
)
_BULLET = re.compile(r"^\s*[-•*·▪‣]\s+")


def _is_heading(line: str) -> bool:
    if _KNOWN.match(line):
        return True
    # Short, non-bullet, no trailing sentence punctuation, ends with ':' or is
    # title-ish — a reasonable heading heuristic.
    if _BULLET.match(line):
        return False
    if len(line) <= 60 and not line.endswith((".", ",", ";")):
        return line.endswith(":") or (line == line.title() and len(line.split()) <= 6)
    return False


def structure_jd(text: str) -> list[dict]:
    """-> [{"heading": str, "items": [{"type": "bullet"|"text", "text": str}]}].
    Content before the first heading goes under an 'Overview' section."""
    if not text or not text.strip():
        return []
    sections: list[dict] = [{"heading": "Overview", "items": []}]
    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            continue
        if _is_heading(line):
            sections.append({"heading": line.rstrip(":").strip(), "items": []})
            continue
        m = _BULLET.match(line)
        item = {"type": "bullet", "text": line[m.end():].strip()} if m \
            else {"type": "text", "text": line}
        sections[-1]["items"].append(item)
    # Drop an empty leading Overview.
    return [s for s in sections if s["items"]]
