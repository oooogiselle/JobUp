"""Load the user profile + answer profile (LLD §9). These hold PII and are
git-ignored; a safe example lives at config/profile.example.yaml."""

from __future__ import annotations

from pathlib import Path

import yaml

from .models import ExperienceItem, UserProfile


def load_profile(path: str | Path = "config/profile.yaml") -> UserProfile:
    p = Path(path)
    if not p.exists():
        example = p.with_name("profile.example.yaml")
        if example.exists():
            p = example
    data = yaml.safe_load(p.read_text()) or {}
    exp = [ExperienceItem(**e) for e in data.get("experience", [])]
    return UserProfile(
        name=data.get("name", ""),
        summary=data.get("summary", ""),
        locations=data.get("locations", []),
        work_authorization=data.get("work_authorization", ""),
        needs_sponsorship=data.get("needs_sponsorship"),
        levels=data.get("levels", []),
        skills=data.get("skills", []),
        experience=exp,
    )


def load_answers(path: str | Path = "config/answer_profile.yaml") -> dict:
    p = Path(path)
    if not p.exists():
        p = p.with_name("answer_profile.example.yaml")
    if not p.exists():
        return {}
    return yaml.safe_load(p.read_text()) or {}
