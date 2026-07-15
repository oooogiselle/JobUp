"""Workday connector (LLD §3). Many FAANG+ companies (Nvidia, Salesforce, Adobe,
Disney, Capital One, …) run Workday, which exposes a JSON search endpoint:
    POST https://{tenant}.wdN.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs

Config gives the public careers URL (e.g.
https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite); the tenant,
locale, and site are parsed from it. Like Simplify, the list has no full JD
(that needs a per-job detail call), so these power discovery + alerts."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import httpx

from ..models import JobSourceType, RawPosting


def _parse_careers_url(url: str) -> tuple[str, str, str, str]:
    u = urlparse(url)
    netloc = u.netloc
    tenant = netloc.split(".")[0]
    parts = [p for p in u.path.split("/") if p]
    locale = parts[0] if parts else "en-US"
    site = parts[-1] if parts else ""
    return netloc, tenant, locale, site


def _parse_posted(s: str | None) -> datetime | None:
    if not s:
        return None
    s = s.lower()
    now = datetime.now(timezone.utc)
    if "today" in s:
        return now
    if "yesterday" in s:
        return now - timedelta(days=1)
    m = re.search(r"(\d+)\+?\s*days?", s)
    if m:
        return now - timedelta(days=int(m.group(1)))
    m = re.search(r"(\d+)\+?\s*months?", s)
    if m:
        return now - timedelta(days=30 * int(m.group(1)))
    return None


def parse_workday(payload: dict, netloc: str, locale: str, site: str,
                  company: str) -> list[RawPosting]:
    out: list[RawPosting] = []
    for j in payload.get("jobPostings", []):
        path = j.get("externalPath", "")
        if not path:
            continue
        url = f"https://{netloc}/{locale}/{site}{path}"
        out.append(RawPosting(
            source=JobSourceType.WORKDAY,
            source_ref=path,
            company=company,
            title=(j.get("title") or "").strip(),
            location=j.get("locationsText"),
            apply_url=url,
            canonical_url=url,
            description_raw="",   # list has no JD; detail call needed
            posted_at=_parse_posted(j.get("postedOn")),
        ))
    return out


class WorkdayConnector:
    name = "workday"

    def __init__(self, careers_url: str, company: str | None = None,
                 client: httpx.AsyncClient | None = None, max_jobs: int = 80):
        self.url = careers_url
        self.netloc, self.tenant, self.locale, self.site = _parse_careers_url(careers_url)
        self.company = company or self.tenant.capitalize()
        self._client = client
        self.max_jobs = max_jobs

    async def fetch(self) -> list[RawPosting]:
        cxs = f"https://{self.netloc}/wday/cxs/{self.tenant}/{self.site}/jobs"
        headers = {"Content-Type": "application/json", "Accept": "application/json",
                   "User-Agent": "JobUp/0.1 (personal job-search assistant)"}
        client = self._client or httpx.AsyncClient(timeout=30, follow_redirects=True)
        out: list[RawPosting] = []
        offset = 0
        try:
            while offset < self.max_jobs:
                resp = await client.post(
                    cxs, headers=headers,
                    json={"appliedFacets": {}, "limit": 20, "offset": offset, "searchText": ""})
                resp.raise_for_status()
                payload = resp.json()
                page = parse_workday(payload, self.netloc, self.locale, self.site, self.company)
                if not page:
                    break
                out.extend(page)
                offset += 20
                if offset >= payload.get("total", 0):
                    break
            return out
        finally:
            if self._client is None:
                await client.aclose()
