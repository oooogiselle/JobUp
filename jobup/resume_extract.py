"""Resume upload + extraction (onboarding + autofill grounding).

Extract plain text from an uploaded resume (PDF or text), then structure it with
the LLM into a profile + answer-profile fields. Extraction is grounded: only
facts present in the resume are captured (nothing invented) — the same integrity
rule as tailoring. The result is saved to the git-ignored config files that drive
matching, tailoring, and autofill."""

from __future__ import annotations

import io
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, ValidationError

from .llm.client import TRIAGE_MODEL, LLMClient
from .models import ExperienceItem, UserProfile
from .profile import load_answers


# --- extraction schema (what the LLM returns) ------------------------------

class ExtractedExperience(BaseModel):
    title: str = ""
    org: str = ""
    dates: str = ""
    bullets: list[str] = Field(default_factory=list)


class ResumeExtract(BaseModel):
    name: str = ""
    email: str = ""
    phone: str = ""
    github: str = ""
    linkedin: str = ""
    portfolio: str = ""
    location: str = ""
    summary: str = ""
    work_authorization: str = ""
    skills: list[str] = Field(default_factory=list)
    experience: list[ExtractedExperience] = Field(default_factory=list)


_EXTRACT_SYSTEM = (
    "Extract structured information from this resume as JSON. Capture ONLY what is "
    "present in the text — do not infer, guess, or embellish. Use an empty string "
    "or empty array when a field is absent. Keep experience bullet wording faithful "
    "to the resume; return full URLs for links.\n"
    "Return ONLY a JSON object (no markdown fences, no commentary) with exactly "
    "these keys: name, email, phone, github, linkedin, portfolio, location, "
    "summary, work_authorization, skills (array of strings), and experience (array "
    "of objects each with keys: title, org, dates, bullets [array of strings]).\n"
    "For each experience entry, split the responsibilities/achievements into "
    "SEPARATE bullet strings — one accomplishment per bullet, faithful to the "
    "resume's wording. Do not merge multiple bullets into one string."
)


def _parse_json(raw: str) -> dict:
    """Tolerantly pull a JSON object out of the model's reply (handles code
    fences / stray prose by slicing the outermost braces)."""
    import json
    if not raw:
        return {}
    i, j = raw.find("{"), raw.rfind("}")
    if i == -1 or j == -1 or j < i:
        return {}
    try:
        return json.loads(raw[i:j + 1])
    except json.JSONDecodeError:
        return {}


# --- text extraction -------------------------------------------------------

def extract_text(data: bytes, filename: str = "") -> str:
    """Plain text from an uploaded resume. PDF via pypdf; otherwise decode text."""
    if filename.lower().endswith(".pdf") or data[:5] == b"%PDF-":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    return data.decode("utf-8", errors="replace").strip()


def extract_profile(resume_text: str, llm: LLMClient) -> ResumeExtract:
    """Structure resume text into a ResumeExtract. Uses a JSON-prompt (not the
    strict structured-output API, which rejects this nested schema as 'too
    complex'); parsing is tolerant and validation is lenient."""
    raw = llm.generate(model=TRIAGE_MODEL, system=_EXTRACT_SYSTEM,
                       user=f"RESUME:\n{resume_text}", max_tokens=4096, thinking=False)
    try:
        return ResumeExtract.model_validate(_parse_json(raw))
    except ValidationError:
        return ResumeExtract()


# --- map extract -> profile + answers --------------------------------------

def to_profile(x: ResumeExtract, keep_levels: list[str] | None = None) -> UserProfile:
    return UserProfile(
        name=x.name,
        summary=x.summary,
        locations=[x.location] if x.location else [],
        work_authorization=x.work_authorization,
        levels=keep_levels or ["new-grad", "entry", "junior", "intern"],
        skills=x.skills,
        experience=[ExperienceItem(title=e.title, org=e.org, dates=e.dates,
                                   bullets=e.bullets) for e in x.experience],
    )


def to_answers(x: ResumeExtract, existing: dict | None = None) -> dict:
    """Merge extracted contact/link fields into the answer profile (non-empty
    values win; existing values preserved otherwise)."""
    merged = dict(existing or {})
    for k in ("work_authorization", "github", "linkedin", "portfolio"):
        v = getattr(x, k)
        if v:
            merged[k] = v
    if x.email:
        merged["email"] = x.email
    if x.phone:
        merged["phone"] = x.phone
    if x.name:
        merged["name"] = x.name
    return merged


# --- persistence (git-ignored config) --------------------------------------

def save_profile(profile: UserProfile, path: str | Path = "config/profile.yaml") -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "name": profile.name, "summary": profile.summary,
        "locations": profile.locations, "work_authorization": profile.work_authorization,
        "needs_sponsorship": profile.needs_sponsorship, "levels": profile.levels,
        "skills": profile.skills,
        "experience": [{"title": e.title, "org": e.org, "dates": e.dates,
                        "bullets": e.bullets, "skills": e.skills} for e in profile.experience],
    }
    p.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))


def save_answers(answers: dict, path: str | Path = "config/answer_profile.yaml") -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(answers, sort_keys=False, allow_unicode=True))


def ingest_resume(data: bytes, filename: str, llm: LLMClient,
                  profile_path: str | Path = "config/profile.yaml",
                  answers_path: str | Path = "config/answer_profile.yaml"
                  ) -> tuple[UserProfile, dict]:
    """Full pipeline: bytes -> text -> extract -> save profile + answers."""
    text = extract_text(data, filename)
    x = extract_profile(text, llm)
    profile = to_profile(x)
    answers = to_answers(x, existing=load_answers(answers_path))
    save_profile(profile, profile_path)
    save_answers(answers, answers_path)
    return profile, answers
