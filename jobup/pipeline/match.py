"""Matching (LLD §4, C6). Two stages, cheap-first:
  1. hard_filters — pure rules, no LLM: level, location, sponsorship, years.
  2. triage       — Sonnet structured relevance + score, only if filters pass.
A posting must clear both to proceed."""

from __future__ import annotations

import re

from ..llm.client import TRIAGE_MODEL, LLMClient, TriageDecision
from ..llm.prompts import TRIAGE_SYSTEM, triage_user
from ..models import JobPosting, MatchResult, UserProfile

# Senior-signal words in a title → not a new-grad role.
_SENIOR = re.compile(r"(?i)\b(senior|staff|principal|lead|manager|director|"
                     r"head\s+of|vp|architect|sr\.?)\b")
# "N+ years" experience requirements.
_YEARS = re.compile(r"(?i)(\d+)\+?\s*(?:-\s*\d+\s*)?years?")


def hard_filters(job: JobPosting, profile: UserProfile,
                 target: dict | None = None, max_years: int = 2) -> str | None:
    """Return the name of the first failed filter, or None if all pass.
    `target` (config.yaml → target) adds precise control:
      - exclude: title words that auto-reject (e.g. senior, manager, sales)
      - roles:   if set, the title MUST contain one of these (e.g. engineer, ml)
    Both run before any LLM call, so filtering out unwanted jobs is free."""
    target = target or {}
    title = job.title.lower()

    if _SENIOR.search(job.title):
        return "level_senior_title"
    if any(w.lower() in title for w in target.get("exclude", [])):
        return "excluded_title"
    roles = [w.lower() for w in target.get("roles", [])]
    if roles and not any(w in title for w in roles):
        return "role_mismatch"

    # Years-of-experience requirement in the JD beyond a new grad.
    for m in _YEARS.finditer(job.description_clean):
        try:
            if int(m.group(1)) > max_years:
                return "years_experience"
        except ValueError:
            pass

    # Location: if the candidate lists locations, require overlap or remote.
    if profile.locations and job.location:
        loc = job.location.lower()
        if "remote" not in loc and job.remote is not True:
            if not any(p.lower().split(",")[0] in loc for p in profile.locations):
                return "location_mismatch"

    # Sponsorship: if candidate needs it and the JD rules it out. Match a
    # negation within a short window before "sponsor" (e.g. "do not offer visa
    # sponsorship", "no sponsorship", "unable to sponsor").
    if profile.needs_sponsorship:
        if re.search(
            r"(?i)\b(no|not|without|cannot|can't|unable|don't|do not|does not|"
            r"will not|won't|are not able|not able|not eligible)\b[^.]{0,40}\bsponsor",
            job.description_clean,
        ):
            return "no_sponsorship"

    return None


def triage(job: JobPosting, profile: UserProfile, llm: LLMClient) -> TriageDecision:
    return llm.parse(
        model=TRIAGE_MODEL,
        system=TRIAGE_SYSTEM,
        user=triage_user(job, profile),
        schema=TriageDecision,
    )


def match(job: JobPosting, profile: UserProfile, llm: LLMClient,
          min_score: float = 0.6, target: dict | None = None) -> MatchResult:
    failed = hard_filters(job, profile, target=target)
    if failed:
        return MatchResult(job_id=job.id, relevant=False, score=0.0,
                           reasons=[f"hard filter: {failed}"],
                           hard_filter_failed=failed, model="rules")

    d = triage(job, profile, llm)
    relevant = bool(d.relevant) and d.score >= min_score
    return MatchResult(job_id=job.id, relevant=relevant, score=d.score,
                       reasons=d.reasons, model=TRIAGE_MODEL)
