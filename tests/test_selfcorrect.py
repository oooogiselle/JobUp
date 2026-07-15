"""Offline coverage for the new self-correction + package pieces (BUILD C/D/E/F).
Uses FakeLLM — no network, no API key.

Covers: the bounded tailor revise loop (fails -> revise -> passes; and stays
failed past the cap), the cover-letter revise loop, the per-job why-this-company
generator, the canonical answer schema, and apply-package assembly."""

from __future__ import annotations

import io
import zipfile

from jobup.llm.client import FactualCheck, FitAssessment, FakeLLM, TriageDecision
from jobup.models import ExperienceItem, JobPosting, JobSourceType, UserProfile, \
    fingerprint_for, job_id_for
from jobup.pipeline.answers import STANDARD_QUESTIONS, prefill_answers
from jobup.pipeline.cover_letter import generate_cover_letter, generate_why_this_company
from jobup.pipeline.package import assemble_package, build_checklist, build_application
from jobup.pipeline.tailor import tailor


def _profile() -> UserProfile:
    return UserProfile(
        name="Test", summary="New-grad SWE.", locations=["Remote"],
        work_authorization="US citizen", needs_sponsorship=False, levels=["new-grad"],
        skills=["python"],
        experience=[ExperienceItem(title="SWE Intern", org="Acme", dates="2025",
                                   bullets=["Built a Python service."])],
    )


def _job() -> JobPosting:
    url = "https://example.com/swe"
    return JobPosting(
        id=job_id_for(url), source=JobSourceType.GREENHOUSE, source_ref="1",
        company="Acme", title="New Grad SWE", location="Remote",
        description_raw="Python.", description_clean="Python.",
        apply_url=url, canonical_url=url,
        fingerprint=fingerprint_for("Acme", "New Grad SWE", "Remote"))


class _StatefulLLM:
    """FakeLLM-shaped double: factual check fails the first `fail_n` times, then
    passes. Lets us exercise the verify->revise->re-verify loop deterministically."""

    def __init__(self, fail_n: int):
        self.fail_n = fail_n
        self.verify_calls = 0
        self.generate_calls = 0

    def generate(self, **kw):
        self.generate_calls += 1
        return "# Resume\n- Built a Python service."

    def parse(self, *, model, system, user, schema, max_tokens=2048):
        if schema is FactualCheck:
            self.verify_calls += 1
            if self.verify_calls <= self.fail_n:
                return FactualCheck(passed=False, unsupported_claims=["invented metric"])
            return FactualCheck(passed=True, unsupported_claims=[])
        if schema is FitAssessment:
            return FitAssessment(needs_heavy_rewrite=False)
        if schema is TriageDecision:
            return TriageDecision(relevant=True, score=0.9, reasons=[])
        raise AssertionError(schema)


# --- C: tailor revise loop -------------------------------------------------

def test_tailor_revises_then_passes():
    llm = _StatefulLLM(fail_n=1)          # first check fails, revise, then passes
    t = tailor(_job(), _profile(), llm, max_revisions=2)
    assert t.factual_check_passed is True
    assert t.revisions == 1
    assert llm.generate_calls == 2        # draft + one revise


def test_tailor_gives_up_after_cap():
    llm = _StatefulLLM(fail_n=99)         # never passes
    t = tailor(_job(), _profile(), llm, max_revisions=2)
    assert t.factual_check_passed is False
    assert t.revisions == 2               # capped
    assert "invented metric" in t.unsupported_claims


# --- D: cover letter revise loop + why-this-company ------------------------

def test_cover_letter_revises_then_passes():
    llm = _StatefulLLM(fail_n=1)
    letter, check = generate_cover_letter("Acme", "SWE", "Python.", _profile(), llm)
    assert check.passed is True
    assert llm.generate_calls == 2        # draft + one revise


def test_why_this_company_generated_and_checked():
    llm = _StatefulLLM(fail_n=0)          # passes immediately
    text, check = generate_why_this_company("Acme", "SWE", "Python.", _profile(), llm)
    assert text and check.passed is True


# --- E: canonical answer schema --------------------------------------------

def test_prefill_maps_standard_schema():
    answers, unanswered = prefill_answers(
        {"work_auth": "US citizen", "salary": "$120k"}, _profile())
    assert answers["work_authorization"] == "US citizen"   # via alias
    assert answers["salary_expectation"] == "$120k"        # via alias
    assert answers["needs_sponsorship"] == "No"            # from profile bool
    assert "degree" in unanswered
    assert "why_this_company" in unanswered                # per-job, always blank


def test_every_question_is_answered_or_unanswered():
    answers, unanswered = prefill_answers({}, None)
    keys = set(answers) | set(unanswered)
    assert keys == {q["key"] for q in STANDARD_QUESTIONS}


# --- F: apply package assembly ---------------------------------------------

def _bundle(**over):
    b = {"id": "x", "company": "Acme", "title": "New Grad SWE", "location": "Remote",
         "apply_url": "https://example.com/swe", "score": 0.85,
         "tailored_resume": {"resume_markdown": "# Resume\n- Built a Python service.",
                             "factual_check_passed": True},
         "answers": {"work_authorization": "US citizen"},
         "unanswered": ["salary_expectation"]}
    b.update(over)
    return b


def test_checklist_lists_apply_url_and_answers():
    md = build_checklist(_bundle())
    assert "https://example.com/swe" in md
    assert "Work authorization: US citizen" in md
    assert "NEEDS YOUR ANSWER" in md            # salary flagged


def test_package_zip_contains_expected_files():
    data = assemble_package(_bundle(cover_letter="Dear Acme,\nHi.\nRegards"))
    names = set(zipfile.ZipFile(io.BytesIO(data)).namelist())
    assert {"checklist.md", "resume.md", "resume.pdf", "cover_letter.md", "answers.md"} <= names


def test_build_application_uses_standard_schema():
    from jobup.models import TailoredResume
    r = TailoredResume(job_id=_job().id, resume_markdown="# R", factual_check_passed=True)
    app = build_application(_job(), r, None, {"degree": "BS CS"}, profile=_profile())
    assert app.answers["degree"] == "BS CS"
    assert "salary_expectation" in app.unanswered
