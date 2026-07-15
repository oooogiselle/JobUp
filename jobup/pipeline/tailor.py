"""Resume tailoring (LLD §5, C7) — the careful part.

Flow: light-align (Opus) -> factual verify (Sonnet) -> [revise if unsupported]
-> re-verify -> fit assessment. The verify->revise->re-verify critic loop is
bounded (MAX_REVISIONS): a draft that flags unsupported claims is fed back to the
model with those claims as feedback and re-checked. If it still fails after the
cap, factual_check_passed stays False, the unsupported claims are recorded, and
the resume is flagged for the "needs attention" bucket — it never reaches the
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
    TAILOR_REVISE_SYSTEM,
    TAILOR_SYSTEM,
    VERIFY_SYSTEM,
    fit_user,
    identity_facts,
    tailor_revise_user,
    tailor_user,
    verify_user,
)
from ..models import JobPosting, TailoredResume, UserProfile

# Bounded critic+retry (BUILD §C): at most this many revise iterations after a
# failed factual check. Deterministic — not a planner/researcher/writer swarm.
MAX_REVISIONS = 2


def _draft(job: JobPosting, profile: UserProfile, llm: LLMClient, mode: str,
           answers: dict | None) -> str:
    return llm.generate(
        model=TAILOR_MODEL,
        system=TAILOR_SYSTEM,
        user=tailor_user(job, profile, mode=mode, answers=answers),
        thinking=True,
    )


def _revise(job: JobPosting, profile: UserProfile, draft: str,
            claims: list[str], llm: LLMClient) -> str:
    return llm.generate(
        model=TAILOR_MODEL,
        system=TAILOR_REVISE_SYSTEM,
        user=tailor_revise_user(job, profile, draft, claims),
        thinking=True,
    )


def verify_factual(resume_markdown: str, profile: UserProfile, llm: LLMClient,
                   answers: dict | None = None) -> FactualCheck:
    """Grounding gate: every concrete claim must trace to the experience library
    OR the candidate's identity facts (name/location/links/degree/graduation),
    which are legitimate ground truth for a resume header + Education section."""
    library = profile.experience_library_text()
    extra = identity_facts(profile, answers)
    if extra:
        library = f"{library}\n\nIDENTITY / EDUCATION (also ground truth):\n{extra}"
    return llm.parse(
        model=TRIAGE_MODEL,
        system=VERIFY_SYSTEM,
        user=verify_user(resume_markdown, library),
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
           mode: str = "light", answers: dict | None = None,
           max_revisions: int = MAX_REVISIONS) -> TailoredResume:
    """Produce a grounded, verified tailored resume with a proper header (name +
    contact + Education from `answers`). Runs a bounded draft->verify->revise->
    re-verify loop: a failed check feeds the flagged claims back for correction
    (up to max_revisions). Never emits an unverified resume as clean — if it
    still fails after the cap, factual_check_passed is False and it's flagged."""
    draft = _draft(job, profile, llm, mode, answers)
    check = verify_factual(draft, profile, llm, answers)
    revisions = 0
    while not check.passed and revisions < max_revisions:
        draft = _revise(job, profile, draft, check.unsupported_claims, llm)
        check = verify_factual(draft, profile, llm, answers)
        revisions += 1
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
        revisions=revisions,
        model=TAILOR_MODEL,
    )
