"""Canonical data model (LLD §2). v1 uses pydantic for schemas + sqlite3 for
storage; the JobPosting shape matches the LLD table definition."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class JobSourceType(str, Enum):
    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    ASHBY = "ashby"
    INDEED = "indeed"
    SIMPLIFY = "simplify"
    COMPANY = "company"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def job_id_for(canonical_url: str) -> str:
    """Stable dedup key = sha256(canonical_url) (LLD §2.1, §10)."""
    return hashlib.sha256(canonical_url.strip().encode("utf-8")).hexdigest()


def fingerprint_for(company: str, title: str, location: str | None) -> str:
    """Fuzzy cross-source dedup key: normalized company|title|location."""
    def norm(s: str | None) -> str:
        return " ".join((s or "").lower().split())

    raw = f"{norm(company)}|{norm(title)}|{norm(location)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class RawPosting(BaseModel):
    """What a source connector yields, before normalization (LLD §3)."""

    source: JobSourceType
    source_ref: str
    company: str
    title: str
    location: str | None = None
    apply_url: str
    canonical_url: str
    description_raw: str = ""
    posted_at: datetime | None = None
    extra: dict = Field(default_factory=dict)


class ExperienceItem(BaseModel):
    """One grounded fact well the tailor may draw from. The tailor may reorder,
    rephrase, and emphasize these — never invent beyond them (SECURITY.md T2)."""

    title: str = ""
    org: str = ""
    dates: str = ""
    bullets: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)


class UserProfile(BaseModel):
    """Source of truth for matching + tailoring (LLD §4, §5)."""

    name: str = ""
    summary: str = ""
    locations: list[str] = Field(default_factory=list)
    work_authorization: str = ""
    needs_sponsorship: bool | None = None
    levels: list[str] = Field(default_factory=list)   # e.g. new-grad, entry
    skills: list[str] = Field(default_factory=list)
    experience: list[ExperienceItem] = Field(default_factory=list)

    def experience_library_text(self) -> str:
        """Flatten experience into the grounded fact well handed to the tailor."""
        chunks: list[str] = []
        if self.summary:
            chunks.append(f"SUMMARY: {self.summary}")
        if self.skills:
            chunks.append("SKILLS: " + ", ".join(self.skills))
        for e in self.experience:
            head = " | ".join(x for x in (e.title, e.org, e.dates) if x)
            chunks.append(head)
            chunks.extend(f"  - {b}" for b in e.bullets)
            if e.skills:
                chunks.append("  skills: " + ", ".join(e.skills))
        return "\n".join(chunks)


class MatchResult(BaseModel):
    """Outcome of matching a posting to the profile (LLD §4)."""

    job_id: str
    relevant: bool
    score: float                          # 0..1
    reasons: list[str] = Field(default_factory=list)
    hard_filter_failed: str | None = None
    model: str = ""


class Enrichment(BaseModel):
    """Hiring team/recruiter, extraction-only, never fabricated (LLD §4.5)."""

    job_id: str
    team: str | None = None
    team_confidence: float = 0.0
    recruiter_name: str | None = None
    recruiter_role: str | None = None
    contact_channel: str | None = None
    source_of_contact: str = "unknown"    # ats_metadata | jd_text | unknown
    recruiter_known: bool = False


class TailoredResume(BaseModel):
    """A light/heavy tailored resume, gated by the factual verifier (LLD §5)."""

    job_id: str
    mode: str = "light"                   # light | heavy
    resume_markdown: str = ""
    diff_summary: str = ""
    factual_check_passed: bool = False
    unsupported_claims: list[str] = Field(default_factory=list)
    needs_heavy_rewrite: bool = False
    model: str = ""


class Application(BaseModel):
    """Packaged application awaiting human approval. status never reaches
    'applied' via the agent — only the human sets that (SECURITY.md T3)."""

    job_id: str
    tailored_resume: TailoredResume
    enrichment: Enrichment | None = None
    answers: dict = Field(default_factory=dict)
    unanswered: list[str] = Field(default_factory=list)
    status: str = "prepared"
    apply_url: str = ""
    cover_letter: str = ""
    cover_letter_ok: bool = False       # passed the factual verifier


class JobPosting(BaseModel):
    """Canonical posting (LLD §2.1). `description_raw` is UNTRUSTED text and must
    never be fed to an LLM as instructions (see docs/SECURITY.md T1)."""

    id: str
    source: JobSourceType
    source_ref: str
    company: str
    title: str
    location: str | None = None
    remote: bool | None = None
    description_raw: str = ""
    description_clean: str = ""
    apply_url: str
    canonical_url: str
    posted_at: datetime | None = None
    first_seen_at: datetime = Field(default_factory=_now)
    fingerprint: str
    raw_json: dict = Field(default_factory=dict)
