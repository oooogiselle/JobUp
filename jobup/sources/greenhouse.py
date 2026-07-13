"""Greenhouse connector (LLD §3). Public board API, no auth:
    GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true

`parse_greenhouse` is pure (payload -> RawPosting[]) so it is unit-testable
offline against a fixture; `fetch` adds the network I/O."""

from __future__ import annotations

from datetime import datetime

import httpx

from ..models import JobSourceType, RawPosting
from ._html import html_to_text as _strip_html

BOARD_URL = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_greenhouse(payload: dict, company: str) -> list[RawPosting]:
    out: list[RawPosting] = []
    for j in payload.get("jobs", []):
        url = j.get("absolute_url", "")
        if not url:
            continue
        location = (j.get("location") or {}).get("name")
        out.append(
            RawPosting(
                source=JobSourceType.GREENHOUSE,
                source_ref=str(j.get("id", "")),
                company=company,
                title=j.get("title", "").strip(),
                location=location,
                apply_url=url,
                canonical_url=url,
                description_raw=_strip_html(j.get("content", "")),
                posted_at=_parse_dt(j.get("updated_at") or j.get("first_published")),
                extra={
                    "departments": [d.get("name") for d in j.get("departments", [])],
                    "offices": [o.get("name") for o in j.get("offices", [])],
                },
            )
        )
    return out


class GreenhouseConnector:
    name = "greenhouse"

    def __init__(self, token: str, company: str | None = None,
                 client: httpx.AsyncClient | None = None):
        self.token = token
        self.company = company or token.capitalize()
        self._client = client

    async def fetch(self) -> list[RawPosting]:
        url = BOARD_URL.format(token=self.token)
        params = {"content": "true"}
        headers = {"User-Agent": "JobUp/0.1 (personal job-search assistant)"}
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            return parse_greenhouse(resp.json(), self.company)
        finally:
            if self._client is None:
                await client.aclose()
