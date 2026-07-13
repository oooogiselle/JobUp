"""Versioned prompt templates (LLD §6). All untrusted JD text is fenced via
guards.wrap_untrusted and every system prompt that shows it carries
UNTRUSTED_SYSTEM_RULE."""

from __future__ import annotations

from ..models import JobPosting, UserProfile
from .guards import UNTRUSTED_SYSTEM_RULE, sanitize_jd, wrap_untrusted


def _fenced_jd(job: JobPosting) -> str:
    """Sanitize the untrusted JD, then fence it. Every LLM prompt that shows JD
    text goes through here (SECURITY.md T1)."""
    return wrap_untrusted(sanitize_jd(job.description_clean))

# --- matching / triage -----------------------------------------------------

TRIAGE_SYSTEM = (
    "You assess whether a job posting is a good match for a specific new-grad "
    "candidate. Return relevant=true only when the role is realistically "
    "appropriate for the candidate's level, location, and skills. Be strict: a "
    "senior/staff role, a wrong-location role, or one needing years of experience "
    "the candidate lacks is NOT relevant. score is 0..1 overall fit. Give concise "
    "reasons.\n\n" + UNTRUSTED_SYSTEM_RULE
)


def triage_user(job: JobPosting, profile: UserProfile) -> str:
    return (
        f"CANDIDATE PROFILE:\n{profile.experience_library_text()}\n"
        f"Target levels: {', '.join(profile.levels) or 'new-grad'}\n"
        f"Target locations: {', '.join(profile.locations) or 'any'}\n"
        f"Needs visa sponsorship: {profile.needs_sponsorship}\n\n"
        f"JOB:\ncompany={job.company}  title={job.title}  location={job.location}\n"
        f"{_fenced_jd(job)}"
    )


# --- resume tailoring ------------------------------------------------------

TAILOR_SYSTEM = (
    "You lightly tailor a candidate's resume to a specific job. RULES:\n"
    "1. GROUNDING: every skill, tool, metric, title, and achievement in your "
    "output MUST be directly supported by the EXPERIENCE LIBRARY provided. Do NOT "
    "add, infer, or embellish. If the job wants something the candidate lacks, "
    "omit it — never invent it.\n"
    "2. LIGHT alignment by default: reorder and re-emphasize existing bullets, "
    "align vocabulary to the job's real keywords the candidate genuinely has, and "
    "tune the summary line. Preserve overall structure and length.\n"
    "3. Output ONLY the tailored resume in Markdown. No commentary.\n\n"
    + UNTRUSTED_SYSTEM_RULE
)


def tailor_user(job: JobPosting, profile: UserProfile, mode: str = "light") -> str:
    depth = ("Do a LIGHT alignment." if mode == "light"
             else "Do a HEAVIER truthful rewrite (deeper restructuring), still "
                  "strictly grounded in the experience library.")
    return (
        f"EXPERIENCE LIBRARY (the only facts you may use):\n"
        f"{profile.experience_library_text()}\n\n"
        f"TARGET JOB: {job.company} — {job.title} ({job.location})\n"
        f"{_fenced_jd(job)}\n\n{depth}"
    )


# --- factual verification --------------------------------------------------

VERIFY_SYSTEM = (
    "You are a strict fact-checker. Given a candidate's EXPERIENCE LIBRARY (ground "
    "truth) and a TAILORED RESUME, list every concrete claim in the resume — "
    "skill, tool, metric, job title, employer, date — that is NOT supported by the "
    "library. passed=true only if there are zero unsupported claims. Do not give "
    "the benefit of the doubt: an added metric, tool, or employer the library "
    "never mentions is unsupported."
)


def verify_user(resume_markdown: str, experience_library: str) -> str:
    return (
        f"EXPERIENCE LIBRARY (ground truth):\n{experience_library}\n\n"
        f"TAILORED RESUME to check:\n{resume_markdown}"
    )


# --- fit assessment (light enough?) ----------------------------------------

FIT_SYSTEM = (
    "You judge whether a LIGHT resume alignment leaves material fit on the table "
    "for a job — i.e. whether a heavier (still truthful) rewrite would materially "
    "improve the candidate's chances. needs_heavy_rewrite=true only when the gap "
    "is real and a truthful deeper rewrite could close much of it.\n\n"
    + UNTRUSTED_SYSTEM_RULE
)


def fit_user(job: JobPosting, resume_markdown: str) -> str:
    return (
        f"TARGET JOB: {job.company} — {job.title}\n"
        f"{_fenced_jd(job)}\n\n"
        f"CURRENT (lightly-aligned) RESUME:\n{resume_markdown}"
    )
