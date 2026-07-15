"""Deterministically render a UserProfile into a clean, bullet-formatted Markdown
resume (no LLM). Used to seed the resume library from an uploaded/edited profile
and as the base the per-job tailor remakes."""

from __future__ import annotations

from ..models import UserProfile


def profile_to_markdown(profile: UserProfile) -> str:
    lines: list[str] = [f"# {profile.name or 'Resume'}"]
    if profile.summary:
        lines += ["", "## Summary", profile.summary]
    if profile.skills:
        lines += ["", "## Skills", ", ".join(profile.skills)]
    if profile.experience:
        lines += ["", "## Experience"]
        for e in profile.experience:
            header = " | ".join(x for x in (e.title, e.org, e.dates) if x)
            if header:
                lines += ["", f"**{header}**"]
            lines += [f"- {b}" for b in e.bullets]     # preserve bullet-point format
    return "\n".join(lines).strip() + "\n"
