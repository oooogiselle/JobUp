"""Packager (LLD §9, C9). Assembles a prepared Application from the tailored
resume, enrichment, and pre-filled answers. status starts at 'prepared' and the
agent never advances it to 'applied' (SECURITY.md invariant #1/#3)."""

from __future__ import annotations

from ..models import Application, Enrichment, JobPosting, TailoredResume


def prefill_answers(profile_answers: dict) -> tuple[dict, list[str]]:
    """Autofill (LLD §4 filler, C8): map the reusable answer profile onto the
    application's standard questions. Known values are pre-filled for one-glance
    review; empty ones are flagged as `unanswered` for the human to complete.
    Nothing is submitted — the human confirms and applies (SECURITY invariant #1)."""
    known = {k: v for k, v in (profile_answers or {}).items() if v not in (None, "")}
    unanswered = [k for k, v in (profile_answers or {}).items() if v in (None, "")]
    return known, unanswered


def build_application(job: JobPosting, resume: TailoredResume,
                      enrichment: Enrichment | None,
                      profile_answers: dict | None = None) -> Application:
    answers, unanswered = prefill_answers(profile_answers or {})
    return Application(
        job_id=job.id,
        tailored_resume=resume,
        enrichment=enrichment,
        answers=answers,
        unanswered=unanswered,
        status="prepared",
        apply_url=job.apply_url,
    )
