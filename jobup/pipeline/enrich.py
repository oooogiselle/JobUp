"""Contact & team enrichment (LLD §4.5, C6b). Extraction-only.

v1 pulls the hiring TEAM from ATS metadata the source already published
(Greenhouse departments live in raw_json.extra). Recruiter/contact is only set
when a source exposes it — never fabricated, never scraped from private profiles
(SECURITY.md T4, invariant #3). An LLM fallback for team extraction from the JD
is a later addition; absent metadata, team stays None."""

from __future__ import annotations

from ..models import Enrichment, JobPosting


def enrich(job: JobPosting) -> Enrichment:
    extra = (job.raw_json or {}).get("extra", {}) or {}
    departments = [d for d in (extra.get("departments") or []) if d]
    team = departments[0] if departments else None

    return Enrichment(
        job_id=job.id,
        team=team,
        team_confidence=0.8 if team else 0.0,
        recruiter_name=None,       # never fabricated; set only from source-published data
        recruiter_role=None,
        contact_channel=None,
        source_of_contact="ats_metadata" if team else "unknown",
        recruiter_known=False,
    )
