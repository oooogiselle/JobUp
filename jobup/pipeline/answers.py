"""Canonical standard application-question schema (BUILD §E).

A fixed, config-defined question set (NOT a plugin) that every prepared
application is pre-filled against from the reusable answer profile + user
profile. Known values are filled for one-glance review; blanks are flagged
`unanswered` for the human to complete. Nothing is ever submitted — the human
confirms and applies (SECURITY invariant #1). Per-ATS field mapping is v2.

`why_this_company` is per-job (generated on approve), so it starts unanswered
and is not sourced from the reusable profile."""

from __future__ import annotations

from ..models import UserProfile

# The canonical schema. `aliases` are the reusable-answer-profile keys we accept
# for each question (so a user's existing free-form answers still map in). Order
# is the display order in the dashboard.
STANDARD_QUESTIONS: list[dict] = [
    {"key": "work_authorization", "label": "Work authorization",
     "aliases": ["work_authorization", "work_auth", "authorization", "citizenship"]},
    {"key": "needs_sponsorship", "label": "Needs visa sponsorship",
     "aliases": ["needs_sponsorship", "sponsorship", "visa_sponsorship", "requires_sponsorship"]},
    {"key": "willing_to_relocate", "label": "Willing to relocate",
     "aliases": ["willing_to_relocate", "relocate", "relocation"]},
    {"key": "onsite_ok", "label": "Open to onsite / hybrid",
     "aliases": ["onsite_ok", "onsite", "hybrid_ok", "work_mode", "remote_preference"]},
    {"key": "earliest_start_date", "label": "Earliest start date",
     "aliases": ["earliest_start_date", "start_date", "earliest_start", "availability"]},
    {"key": "degree", "label": "Degree",
     "aliases": ["degree", "education", "degree_level", "highest_degree"]},
    {"key": "graduation_date", "label": "Graduation date",
     "aliases": ["graduation_date", "grad_date", "graduation", "grad"]},
    {"key": "salary_expectation", "label": "Salary expectation",
     "aliases": ["salary_expectation", "salary", "desired_salary", "compensation", "pay"]},
    {"key": "why_this_company", "label": "Why this company", "aliases": ["why_this_company"],
     "per_job": True},
]

_KEYS = [q["key"] for q in STANDARD_QUESTIONS]


def _fmt(v) -> str:
    """Normalize a stored value to the string an application form expects."""
    if isinstance(v, bool):
        return "Yes" if v else "No"
    return "" if v is None else str(v).strip()


def answer_source(profile: UserProfile | None, answer_profile: dict | None) -> dict:
    """Merge the profile's authoritative fields into the reusable answer profile
    so the standard schema can prefill from a single dict. Explicit answer-profile
    values win over profile-derived ones."""
    src = dict(answer_profile or {})
    if profile is not None:
        if profile.work_authorization:
            src.setdefault("work_authorization", profile.work_authorization)
        if profile.needs_sponsorship is not None:
            src.setdefault("needs_sponsorship", profile.needs_sponsorship)
    return src


def prefill_answers(answer_profile: dict | None, profile: UserProfile | None = None,
                    questions: list[dict] | None = None) -> tuple[dict, list[str]]:
    """Map the reusable answer profile (+ profile) onto the standard question
    schema. Returns (answers, unanswered): every question key is present in one
    of the two. Per-job questions start unanswered."""
    questions = questions or STANDARD_QUESTIONS
    src = answer_source(profile, answer_profile)
    answers: dict = {}
    unanswered: list[str] = []
    for q in questions:
        if q.get("per_job"):
            unanswered.append(q["key"])
            continue
        val = ""
        for alias in q["aliases"]:
            if alias in src and _fmt(src[alias]) != "":
                val = _fmt(src[alias])
                break
        if val:
            answers[q["key"]] = val
        else:
            unanswered.append(q["key"])
    return answers, unanswered


def question_labels() -> dict[str, str]:
    return {q["key"]: q["label"] for q in STANDARD_QUESTIONS}
