"""Cover-letter generator (grounded + verified). On-demand: many applications
need one, and a targeted letter raises callback rate.

Grounded exactly like tailoring — every claim must trace to the experience
library — and run through the same factual verifier. The untrusted JD is
sanitized + fenced before the LLM sees it (SECURITY.md T1)."""

from __future__ import annotations

from ..llm.client import TAILOR_MODEL, FactualCheck, LLMClient
from ..llm.guards import UNTRUSTED_SYSTEM_RULE, sanitize_jd, wrap_untrusted
from ..models import UserProfile
from .tailor import verify_factual

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


def cover_user(company: str, title: str, jd_text: str, profile: UserProfile) -> str:
    return (
        f"CANDIDATE NAME: {profile.name or '(unknown)'}\n"
        f"EXPERIENCE LIBRARY (the only facts you may use):\n"
        f"{profile.experience_library_text()}\n\n"
        f"TARGET ROLE: {title} at {company}\n"
        f"{wrap_untrusted(sanitize_jd(jd_text))}"
    )


def generate_cover_letter(company: str, title: str, jd_text: str,
                          profile: UserProfile, llm: LLMClient
                          ) -> tuple[str, FactualCheck]:
    letter = llm.generate(
        model=TAILOR_MODEL, system=COVER_SYSTEM,
        user=cover_user(company, title, jd_text, profile),
        max_tokens=2000, thinking=True,
    )
    check = verify_factual(letter, profile, llm)
    return letter, check
