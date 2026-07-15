"""Cover-letter + per-job "why this company" generators (grounded + verified).

On-demand / on-approve: a targeted letter raises callback rate, so we spend
Opus tokens only when the user approves a job (BUILD §D). Both run the SAME
bounded draft -> verify -> revise -> re-verify grounding loop as tailoring — every
claim must trace to the experience library — and the untrusted JD is sanitized +
fenced before the LLM sees it (SECURITY.md T1, invariant #2)."""

from __future__ import annotations

from ..llm.client import TAILOR_MODEL, FactualCheck, LLMClient
from ..llm.guards import UNTRUSTED_SYSTEM_RULE, sanitize_jd, wrap_untrusted
from ..models import UserProfile
from .tailor import MAX_REVISIONS, verify_factual

COVER_SYSTEM = (
    "Write a concise, professional cover letter (about 200-280 words) for the "
    "candidate applying to this role. RULES:\n"
    "1. GROUNDING: every claim about the candidate MUST be supported by their "
    "EXPERIENCE LIBRARY. Do NOT invent employers, titles, skills, metrics, or "
    "achievements. If the role wants something the candidate lacks, don't claim it.\n"
    "2. Be specific to the company and role; show genuine fit using real experience.\n"
    "3. Output ONLY the letter: a greeting, 2-3 short paragraphs, and a sign-off. "
    "No bracketed placeholders — use the candidate's name if provided.\n\n"
    + UNTRUSTED_SYSTEM_RULE
)

COVER_REVISE_SYSTEM = (
    "You are revising a cover letter that FAILED a factual check: a strict "
    "verifier flagged claims about the candidate not supported by their "
    "EXPERIENCE LIBRARY. Rewrite the letter so EVERY flagged claim is removed or "
    "truthfully softened. Do NOT invent new facts to replace them — only the "
    "experience library is ground truth. Keep it concise and professional. "
    "Output ONLY the corrected letter.\n\n" + UNTRUSTED_SYSTEM_RULE
)

WHY_SYSTEM = (
    "Write a short, sincere answer (2-4 sentences) to the application question "
    "\"Why do you want to work at this company?\" for this candidate and role. "
    "RULES:\n"
    "1. GROUNDING: any claim about the candidate's own background MUST be "
    "supported by their EXPERIENCE LIBRARY — do not invent experience. You may "
    "reference the company/role from the job description.\n"
    "2. Specific and genuine, not generic flattery. Output ONLY the answer text.\n\n"
    + UNTRUSTED_SYSTEM_RULE
)


def _profile_and_jd(company: str, title: str, jd_text: str, profile: UserProfile) -> str:
    return (
        f"CANDIDATE NAME: {profile.name or '(unknown)'}\n"
        f"EXPERIENCE LIBRARY (the only facts you may use):\n"
        f"{profile.experience_library_text()}\n\n"
        f"TARGET ROLE: {title} at {company}\n"
        f"{wrap_untrusted(sanitize_jd(jd_text))}"
    )


def cover_user(company: str, title: str, jd_text: str, profile: UserProfile) -> str:
    return _profile_and_jd(company, title, jd_text, profile)


def _cover_revise_user(company: str, title: str, jd_text: str, profile: UserProfile,
                       letter: str, claims: list[str]) -> str:
    flagged = "\n".join(f"  - {c}" for c in claims) or "  (none listed)"
    return (
        f"{_profile_and_jd(company, title, jd_text, profile)}\n\n"
        f"CURRENT LETTER (failed the factual check):\n{letter}\n\n"
        f"UNSUPPORTED CLAIMS the verifier flagged — fix every one:\n{flagged}"
    )


def generate_cover_letter(company: str, title: str, jd_text: str,
                          profile: UserProfile, llm: LLMClient,
                          max_revisions: int = MAX_REVISIONS
                          ) -> tuple[str, FactualCheck]:
    """Draft -> verify -> (revise -> re-verify)* a grounded cover letter, bounded
    at max_revisions. Returns the best letter and its final factual check; a still
    -failing check means the caller must flag it, not present it as clean."""
    letter = llm.generate(
        model=TAILOR_MODEL, system=COVER_SYSTEM,
        user=cover_user(company, title, jd_text, profile),
        max_tokens=2000, thinking=True,
    )
    check = verify_factual(letter, profile, llm)
    revisions = 0
    while not check.passed and revisions < max_revisions:
        letter = llm.generate(
            model=TAILOR_MODEL, system=COVER_REVISE_SYSTEM,
            user=_cover_revise_user(company, title, jd_text, profile,
                                    letter, check.unsupported_claims),
            max_tokens=2000, thinking=True,
        )
        check = verify_factual(letter, profile, llm)
        revisions += 1
    return letter, check


def generate_why_this_company(company: str, title: str, jd_text: str,
                              profile: UserProfile, llm: LLMClient
                              ) -> tuple[str, FactualCheck]:
    """Per-job "why this company" answer, grounded + verified like the letter."""
    text = llm.generate(
        model=TAILOR_MODEL, system=WHY_SYSTEM,
        user=cover_user(company, title, jd_text, profile),
        max_tokens=600, thinking=True,
    )
    check = verify_factual(text, profile, llm)
    return text.strip(), check
