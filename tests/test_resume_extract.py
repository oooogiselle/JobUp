"""Resume upload + extraction tests (offline; FakeLLM + a real generated PDF)."""

from __future__ import annotations

from jobup.llm.client import FakeLLM
from jobup.profile import load_profile
from jobup.render.resume_pdf import render_markdown_pdf
from jobup.resume_extract import (
    ResumeExtract,
    extract_text,
    ingest_resume,
    to_answers,
    to_profile,
)

EXTRACT = {
    "name": "Jane Doe", "email": "jane@x.com", "github": "https://github.com/jane",
    "linkedin": "https://linkedin.com/in/jane", "location": "San Francisco, CA",
    "summary": "New-grad SWE.", "work_authorization": "US citizen",
    "skills": ["python", "go", "react"],
    "experience": [{"title": "SWE Intern", "org": "Acme", "dates": "2025",
                    "bullets": ["Built a Python service."]}],
}


def _fake_llm():
    import json
    # extraction now uses generate() + JSON parse (the strict schema was too complex)
    return FakeLLM(generate_fn=lambda user: json.dumps(EXTRACT))


def test_extract_text_from_plain_bytes():
    assert "hello resume" in extract_text(b"hello resume", "r.txt")


def test_extract_text_from_pdf_roundtrip(tmp_path):
    pdf = render_markdown_pdf("# Jane Doe\n\n## Skills\nPython, Go", tmp_path / "r.pdf")
    text = extract_text(pdf.read_bytes(), "r.pdf")
    assert "Jane Doe" in text and "Python" in text


def test_to_profile_maps_fields():
    p = to_profile(ResumeExtract(**EXTRACT))
    assert p.name == "Jane Doe"
    assert p.locations == ["San Francisco, CA"]
    assert "python" in p.skills
    assert p.experience[0].org == "Acme"
    assert p.experience[0].bullets == ["Built a Python service."]


def test_to_answers_merges_links_and_preserves_existing():
    ans = to_answers(ResumeExtract(**EXTRACT), existing={"portfolio": "https://me.dev"})
    assert ans["github"] == "https://github.com/jane"
    assert ans["work_authorization"] == "US citizen"
    assert ans["portfolio"] == "https://me.dev"   # preserved
    assert ans["email"] == "jane@x.com"


def test_profile_to_markdown_preserves_bullets():
    from jobup.models import ExperienceItem, UserProfile
    from jobup.render.master_resume import profile_to_markdown
    p = UserProfile(name="Jane Doe", summary="New-grad SWE", skills=["python", "go"],
                    experience=[ExperienceItem(title="Intern", org="Acme", dates="2025",
                                               bullets=["Built a Python service.", "Cut latency 40%."])])
    md = profile_to_markdown(p)
    assert "# Jane Doe" in md and "## Experience" in md and "## Skills" in md
    assert "- Built a Python service." in md and "- Cut latency 40%." in md
    assert "**Intern | Acme | 2025**" in md


def test_ingest_resume_saves_and_reloads(tmp_path):
    pfile = tmp_path / "profile.yaml"
    afile = tmp_path / "answers.yaml"
    profile, answers = ingest_resume(b"resume text", "r.txt", _fake_llm(),
                                     profile_path=pfile, answers_path=afile)
    assert profile.name == "Jane Doe"
    # round-trips through YAML back into a UserProfile
    reloaded = load_profile(pfile)
    assert reloaded.name == "Jane Doe" and "python" in reloaded.skills
    assert answers["github"] == "https://github.com/jane"
