"""Normalize RawPosting -> canonical JobPosting (LLD §2, C4).

`description_clean` here is a light plain-text pass; the LLM-facing injection
sanitizer (guards.sanitize_jd, docs/SECURITY.md T1) lands with the tailoring
slice. Connectors already deliver plain text for v1 sources."""

from __future__ import annotations

from ..models import JobPosting, RawPosting, fingerprint_for, job_id_for


def _detect_remote(raw: RawPosting) -> bool | None:
    hay = f"{raw.location or ''} {raw.title}".lower()
    if "remote" in hay:
        return True
    return None


def normalize(raw: RawPosting) -> JobPosting:
    canonical = raw.canonical_url.strip()
    return JobPosting(
        id=job_id_for(canonical),
        source=raw.source,
        source_ref=raw.source_ref,
        company=raw.company.strip(),
        title=raw.title.strip(),
        location=raw.location,
        remote=_detect_remote(raw),
        description_raw=raw.description_raw,
        description_clean=raw.description_raw,  # v1: sources deliver plain text
        apply_url=raw.apply_url,
        canonical_url=canonical,
        posted_at=raw.posted_at,
        fingerprint=fingerprint_for(raw.company, raw.title, raw.location),
        raw_json={"extra": raw.extra},
    )
