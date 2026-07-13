"""Ashby connector (LLD §3). Public job-board posting API, no auth:
    GET https://api.ashbyhq.com/posting-api/job-board/{token}

`parse_ashby` is pure (payload -> RawPosting[]) for offline tests."""

from __future__ import annotations

from datetime import datetime

import httpx

from ..models import JobSourceType, RawPosting
from ._html import html_to_text

BOARD_URL = "https://api.ashbyhq.com/posting-api/job-board/{token}"


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_ashby(payload: dict, company: str) -> list[RawPosting]:
    out: list[RawPosting] = []
    for j in payload.get("jobs", []):
        url = j.get("jobUrl") or j.get("applyUrl")
        if not url:
            continue
        desc = j.get("descriptionPlain") or html_to_text(j.get("descriptionHtml", ""))
        out.append(RawPosting(
            source=JobSourceType.ASHBY,
            source_ref=str(j.get("id", "")),
            company=company,
            title=(j.get("title") or "").strip(),
            location=j.get("location"),
            apply_url=url,
            canonical_url=url,
            description_raw=desc,
            posted_at=_parse_dt(j.get("publishedAt")),
            extra={"team": j.get("team") or j.get("department"),
                   "remote": j.get("isRemote")},
        ))
    return out


class AshbyConnector:
    name = "ashby"

    def __init__(self, token: str, company: str | None = None,
                 client: httpx.AsyncClient | None = None):
        self.token = token
        self.company = company or token.capitalize()
        self._client = client

    async def fetch(self) -> list[RawPosting]:
        url = BOARD_URL.format(token=self.token)
        headers = {"User-Agent": "JobUp/0.1 (personal job-search assistant)"}
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            resp = await client.get(url, params={"includeCompensation": "true"},
                                    headers=headers)
            resp.raise_for_status()
            return parse_ashby(resp.json(), self.company)
        finally:
            if self._client is None:
                await client.aclose()
