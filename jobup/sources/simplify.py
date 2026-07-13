"""Simplify GitHub new-grad connector (LLD §3). Parses a SimplifyJobs repo's
README markdown table (e.g. SimplifyJobs/New-Grad-Positions) into postings.

Note: these community lists give company/role/location/link but NO job
description, so they power discovery + alerts; tailoring against them is limited
(empty JD). Most links point at Greenhouse/Lever/Ashby, which the other
connectors cover in depth."""

from __future__ import annotations

import re

import httpx

from ..models import JobSourceType, RawPosting

RAW_URL = "https://raw.githubusercontent.com/{repo}/{branch}/README.md"
_ROW = re.compile(r"^\s*\|(.+)\|\s*$")
_TR = re.compile(r"<tr>(.*?)</tr>", re.S | re.I)
_TD = re.compile(r"<td>(.*?)</td>", re.S | re.I)
_HREF = re.compile(r'href="([^"]+)"')
_MDLINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_CONT = ("↳", "⤷", "&nbsp;↳", '"', "")


def _clean(cell: str) -> str:
    cell = _MDLINK.sub(r"\1", cell)            # [text](url) -> text
    cell = re.sub(r"</?br\s*/?>", ", ", cell, flags=re.I)
    cell = re.sub(r"[*`]", "", cell)
    cell = re.sub(r"<[^>]+>", " ", cell)       # strip any html
    return " ".join(cell.split()).strip()


def _apply_url(cell: str) -> str:
    hrefs = [h for h in _HREF.findall(cell) if "simplify.jobs" not in h]
    return (hrefs or _HREF.findall(cell) or [""])[0]


def _row(company_cell, role_cell, loc_cell, app_cell, last_company: str):
    """Build one posting from 4 cells; returns (RawPosting|None, new_last_company)."""
    if "🔒" in app_cell:                        # closed listing
        return None, last_company
    company = _clean(company_cell)
    if company in _CONT or not company:
        company = last_company
    role, url = _clean(role_cell), _apply_url(app_cell)
    if not company or not role or not url:
        return None, (company or last_company)
    post = RawPosting(
        source=JobSourceType.SIMPLIFY, source_ref=url, company=company, title=role,
        location=_clean(loc_cell) or None, apply_url=url, canonical_url=url,
        description_raw="",   # community lists carry no JD text
    )
    return post, company


def parse_simplify(text: str) -> list[RawPosting]:
    """Handles both the current HTML-table README and legacy markdown-pipe tables."""
    out: list[RawPosting] = []
    last = ""
    if "</td>" in text.lower():                 # HTML table format
        for tr in _TR.findall(text):
            cells = _TD.findall(tr)
            if len(cells) < 4:
                continue
            post, last = _row(cells[0], cells[1], cells[2], cells[3], last)
            if post:
                out.append(post)
        return out
    # legacy markdown pipes
    in_table = False
    for line in text.splitlines():
        m = _ROW.match(line)
        if not m:
            in_table = False
            continue
        cells = [c.strip() for c in m.group(1).split("|")]
        if len(cells) < 4:
            continue
        if "company" in " ".join(cells).lower() and "role" in " ".join(cells).lower():
            in_table = True
            continue
        if set(cells[0]) <= set("-: ") or not in_table:
            continue
        post, last = _row(cells[0], cells[1], cells[2], cells[3], last)
        if post:
            out.append(post)
    return out


class SimplifyConnector:
    name = "simplify"

    def __init__(self, repo: str, client: httpx.AsyncClient | None = None):
        self.repo = repo
        self._client = client

    async def fetch(self) -> list[RawPosting]:
        headers = {"User-Agent": "JobUp/0.1 (personal job-search assistant)"}
        client = self._client or httpx.AsyncClient(timeout=30, follow_redirects=True)
        try:
            for branch in ("dev", "main", "master"):
                resp = await client.get(RAW_URL.format(repo=self.repo, branch=branch),
                                        headers=headers)
                if resp.status_code == 200:
                    return parse_simplify(resp.text)
            return []
        finally:
            if self._client is None:
                await client.aclose()
