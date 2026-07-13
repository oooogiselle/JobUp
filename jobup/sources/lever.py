"""Lever connector (LLD §3). Public postings API, no auth:
    GET https://api.lever.co/v0/postings/{token}?mode=json

`parse_lever` is pure (payload -> RawPosting[]) for offline tests."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from ..models import JobSourceType, RawPosting
from ._html import html_to_text

POSTINGS_URL = "https://api.lever.co/v0/postings/{token}"


def _ms_to_dt(ms) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc)
    except (TypeError, ValueError):
        return None


def parse_lever(payload: list, company: str) -> list[RawPosting]:
    out: list[RawPosting] = []
    for j in payload:
        url = j.get("hostedUrl") or j.get("applyUrl")
        if not url:
            continue
        cats = j.get("categories") or {}
        # Opening blurb + each structured list (Responsibilities, Requirements…).
        parts = [j.get("descriptionPlain") or html_to_text(j.get("description", ""))]
        for lst in j.get("lists", []):
            parts.append(lst.get("text", ""))
            parts.append(html_to_text(lst.get("content", "")))
        desc = "\n".join(p for p in parts if p).strip()
        out.append(RawPosting(
            source=JobSourceType.LEVER,
            source_ref=str(j.get("id", "")),
            company=company,
            title=(j.get("text") or "").strip(),
            location=cats.get("location"),
            apply_url=url,
            canonical_url=url,
            description_raw=desc,
            posted_at=_ms_to_dt(j.get("createdAt")),
            extra={"team": cats.get("team"), "commitment": cats.get("commitment")},
        ))
    return out


class LeverConnector:
    name = "lever"

    def __init__(self, token: str, company: str | None = None,
                 client: httpx.AsyncClient | None = None):
        self.token = token
        self.company = company or token.capitalize()
        self._client = client

    async def fetch(self) -> list[RawPosting]:
        url = POSTINGS_URL.format(token=self.token)
        headers = {"User-Agent": "JobUp/0.1 (personal job-search assistant)"}
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            resp = await client.get(url, params={"mode": "json"}, headers=headers)
            resp.raise_for_status()
            return parse_lever(resp.json(), self.company)
        finally:
            if self._client is None:
                await client.aclose()
