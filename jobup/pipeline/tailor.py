"""Resume tailoring (LLD §5, C7) — the careful part.

Flow: light-align (Opus) -> factual verify (Sonnet) -> fit assessment.
The factual verifier is a hard gate: if the tailored resume contains any claim
not supported by the experience library, factual_check_passed is False, the
unsupported claims are recorded, and the resume is flagged — it never reaches the
approval queue as if it were clean (SECURITY.md T2, invariant #2)."""

from __future__ import annotations

from ..llm.client import (
    TAILOR_MODEL,
    TRIAGE_MODEL,
    FactualCheck,
    FitAssessment,
    LLMClient,
)
from ..llm.prompts import (
    FIT_SYSTEM,
    TAILOR_SYSTEM,
    VERIFY_SYSTEM,
    fit_user,
    tailor_user,
    verify_user,
)
from ..models import JobPosting, TailoredResume, UserProfile


def _draft(job: JobPosting, profile: UserProfile, llm: LLMClient, mode: str) -> str:
    return llm.generate(
        model=TAILOR_MODEL,
        system=TAILOR_SYSTEM,
        user=tailor_user(job, profile, mode=mode),
        thinking=True,
    )


def verify_factual(resume_markdown: str, profile: UserProfile,
                   llm: LLMClient) -> FactualCheck:
    """Grounding gate: every concrete claim must trace to the experience library."""
    return llm.parse(
        model=TRIAGE_MODEL,
        system=VERIFY_SYSTEM,
        user=verify_user(resume_markdown, profile.experience_library_text()),
        schema=FactualCheck,
    )


def assess_fit(job: JobPosting, resume_markdown: str, llm: LLMClient) -> FitAssessment:
    return llm.parse(
        model=TRIAGE_MODEL,
        system=FIT_SYSTEM,
        user=fit_user(job, resume_markdown),
        schema=FitAssessment,
    )


def tailor(job: JobPosting, profile: UserProfile, llm: LLMClient,
           mode: str = "light") -> TailoredResume:
    """Produce a grounded, verified tailored resume. Never emits an unverified
    resume as clean — an unsupported-claim result blocks factual_check_passed."""
    draft = _draft(job, profile, llm, mode)
    check = verify_factual(draft, profile, llm)
    fit = assess_fit(job, draft, llm)

    return TailoredResume(
        job_id=job.id,
        mode=mode,
        resume_markdown=draft,
        diff_summary="light alignment: reordered/rephrased grounded bullets"
        if mode == "light" else "heavier truthful rewrite",
        factual_check_passed=check.passed,
        unsupported_claims=check.unsupported_claims,
        needs_heavy_rewrite=(mode == "light" and fit.needs_heavy_rewrite),
        model=TAILOR_MODEL,
    )
