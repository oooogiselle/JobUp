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
    "You produce a clean, ATS-friendly, one-to-two-page resume in Markdown, "
    "tailored to a specific job and STRICTLY grounded in the candidate's data.\n"
    "STRUCTURE — use exactly this section order; omit a section only if there is "
    "no real content for it:\n"
    "1. `# <Full Name>` as the very first line (from CANDIDATE IDENTITY — the name, "
    "NOT the job title).\n"
    "2. Directly under the name, ONE contact line (the CONTACT value), parts "
    "separated by ' · '. No heading, no bullet.\n"
    "3. `## Summary` — a 1–2 sentence positioning line tuned to this job.\n"
    "4. `## Skills` — grouped and comma-separated (e.g. `**Languages:** ...`), only "
    "skills the candidate genuinely has.\n"
    "5. `## Experience` — each role as `**Title | Org, Location | Dates**` followed "
    "by `- ` bullets (strong verb + concrete impact/metric). Most relevant first.\n"
    "6. `## Education` — from CANDIDATE IDENTITY / library (degree, school, "
    "graduation) when available.\n"
    "7. `## Projects` — only if the library contains real projects.\n"
    "GROUNDING RULES:\n"
    "- Every skill, tool, metric, title, employer, date, and achievement MUST be "
    "supported by the EXPERIENCE LIBRARY or CANDIDATE IDENTITY. Never add, infer, "
    "or embellish. If the job wants something the candidate lacks, omit it.\n"
    "- LIGHT mode reorders/re-emphasizes and aligns vocabulary to the job's real "
    "keywords the candidate genuinely has; it preserves the underlying facts.\n"
    "- Output ONLY the resume Markdown — no commentary, no code fences.\n\n"
    + UNTRUSTED_SYSTEM_RULE
)


def identity_facts(profile: UserProfile, answers: dict | None = None) -> str:
    """Ground-truth identity/education lines (name, location, contact links,
    degree, graduation) drawn from the profile + reusable answers. Fed to the
    tailor as the resume header source AND to the verifier as ground truth, so a
    real degree/link is never flagged as an unsupported fabrication."""
    answers = answers or {}
    facts: list[str] = []
    if profile.name:
        facts.append(f"Name: {profile.name}")
    loc = next((l for l in (profile.locations or []) if l), "")
    if loc:
        facts.append(f"Location: {loc}")
    for label, key in (("Email", "email"), ("Phone", "phone"), ("GitHub", "github"),
                       ("LinkedIn", "linkedin"), ("Portfolio", "portfolio"),
                       ("Degree", "degree"), ("Graduation", "graduation_date")):
        if answers.get(key):
            facts.append(f"{label}: {answers[key]}")
    return "\n".join(facts)


def tailor_user(job: JobPosting, profile: UserProfile, mode: str = "light",
                answers: dict | None = None) -> str:
    depth = ("Do a LIGHT alignment." if mode == "light"
             else "Do a HEAVIER truthful rewrite (deeper restructuring), still "
                  "strictly grounded in the experience library.")
    return (
        f"CANDIDATE IDENTITY (use for the resume header + Education; ground truth):\n"
        f"{identity_facts(profile, answers) or '(name unknown)'}\n\n"
        f"EXPERIENCE LIBRARY (the only professional facts you may use):\n"
        f"{profile.experience_library_text()}\n\n"
        f"TARGET JOB: {job.company} — {job.title} ({job.location})\n"
        f"{_fenced_jd(job)}\n\n{depth}"
    )


# --- resume revision (self-correction after a failed factual check) ---------

TAILOR_REVISE_SYSTEM = (
    "You are revising a candidate's tailored resume that FAILED a factual check: "
    "a strict verifier found claims not supported by the candidate's EXPERIENCE "
    "LIBRARY. Produce a corrected resume that removes or rewrites EVERY flagged "
    "claim so it is fully grounded. RULES:\n"
    "1. Delete or truthfully soften each unsupported claim — do NOT invent new "
    "facts to replace them. Only the experience library is ground truth.\n"
    "2. Keep everything already supported; preserve structure and length.\n"
    "3. Output ONLY the corrected resume in Markdown. No commentary.\n\n"
    + UNTRUSTED_SYSTEM_RULE
)


def tailor_revise_user(job: JobPosting, profile: UserProfile, draft: str,
                       unsupported_claims: list[str]) -> str:
    flagged = "\n".join(f"  - {c}" for c in unsupported_claims) or "  (none listed)"
    return (
        f"EXPERIENCE LIBRARY (the only facts you may use):\n"
        f"{profile.experience_library_text()}\n\n"
        f"TARGET JOB: {job.company} — {job.title} ({job.location})\n"
        f"{_fenced_jd(job)}\n\n"
        f"CURRENT RESUME (failed the factual check):\n{draft}\n\n"
        f"UNSUPPORTED CLAIMS the verifier flagged — fix every one:\n{flagged}"
    )


# --- factual verification --------------------------------------------------

VERIFY_SYSTEM = (
    "You are a strict fact-checker. Given a candidate's EXPERIENCE LIBRARY (ground "
    "truth) and a TAILORED RESUME, list every substantive PROFESSIONAL claim in the "
    "resume — skill, tool, metric, job title, employer, date, achievement — that is "
    "NOT supported by the library. passed=true only if there are zero unsupported "
    "claims. Do not give the benefit of the doubt: an added metric, tool, or employer "
    "the library never mentions is unsupported.\n"
    "Do NOT flag standard resume header / identity fields — the candidate's name, "
    "location or city, email, phone, or LinkedIn/GitHub/portfolio links — as "
    "unsupported. Those are identity, not professional claims. Also do not flag "
    "generic section headings or reworded-but-equivalent phrasings of real bullets."
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
