"""Tests for JD structuring and the assisted-apply fill matcher (offline, pure)."""

from __future__ import annotations

from jobup.apply import fill_plan, is_resume_field, match_field
from jobup.jd import structure_jd
from jobup.render.resume_pdf import render_markdown_pdf, render_to_bytes

JD = (
    "About the team\n"
    "We build payments infrastructure.\n"
    "Responsibilities\n"
    "- Build Python services.\n"
    "- Own reliability.\n"
    "Requirements\n"
    "- Bachelor's degree.\n"
    "- 0-2 years experience.\n"
)


def test_structure_jd_splits_sections_and_bullets():
    secs = structure_jd(JD)
    headings = [s["heading"] for s in secs]
    assert "About the team" in headings
    assert "Responsibilities" in headings
    assert "Requirements" in headings
    resp = next(s for s in secs if s["heading"] == "Responsibilities")
    bullets = [i["text"] for i in resp["items"] if i["type"] == "bullet"]
    assert bullets == ["Build Python services.", "Own reliability."]


def test_structure_jd_empty():
    assert structure_jd("") == []


def test_structure_jd_no_headings_gives_overview():
    secs = structure_jd("Just a paragraph about the role.")
    assert len(secs) == 1 and secs[0]["heading"] == "Overview"


# --- assisted-apply field matching ----------------------------------------

ANSWERS = {
    "work_authorization": "US citizen",
    "requires_sponsorship": "No",
    "github": "https://github.com/me",
    "linkedin": "https://linkedin.com/in/me",
    "portfolio": "",   # empty -> never matched
}


def test_match_field_specific_wins():
    assert match_field("Your LinkedIn profile URL", ANSWERS) == ("linkedin", "https://linkedin.com/in/me")
    assert match_field("GitHub username", ANSWERS) == ("github", "https://github.com/me")


def test_match_field_work_auth_and_sponsorship():
    assert match_field("Are you legally authorized to work in the US?", ANSWERS)[0] == "work_authorization"
    assert match_field("Do you now or in the future require visa sponsorship?", ANSWERS)[0] == "requires_sponsorship"


def test_match_field_skips_empty_answer():
    # portfolio value is empty -> a "Portfolio" field matches nothing to fill
    assert match_field("Portfolio", ANSWERS) is None


def test_match_field_no_match():
    assert match_field("Favorite color", ANSWERS) is None


def test_fill_plan_uses_each_answer_once():
    fields = ["LinkedIn URL", "Another linkedin field", "GitHub", "Work authorization?"]
    plan = fill_plan(fields, ANSWERS)
    keys = [it.key for it in plan]
    assert keys.count("linkedin") == 1          # second linkedin field not double-filled
    assert set(keys) == {"linkedin", "github", "work_authorization"}


def test_is_resume_field():
    assert is_resume_field("Attach your resume (PDF)")
    assert is_resume_field("Upload CV")
    assert not is_resume_field("Cover letter")


# --- PDF rendering ---------------------------------------------------------

RESUME_MD = "# Jane Doe\n\n## Summary\nNew-grad SWE with “smart quotes” — and an em dash.\n\n## Experience\n- Built a **Python** service handling 2k req/s.\n- Cut p99 latency 40%.\n"


def test_render_to_bytes_is_valid_pdf():
    data = render_to_bytes(RESUME_MD)
    assert data[:5] == b"%PDF-"          # real PDF header
    assert len(data) > 800               # non-trivial content


def test_render_handles_unicode_without_crashing():
    # smart quotes + em dash must not raise (latin-1 core font)
    render_to_bytes("# Café ‘résumé’ — build\n- ünïcödë bullet")


def test_render_markdown_pdf_writes_file(tmp_path):
    out = render_markdown_pdf(RESUME_MD, tmp_path / "r.pdf")
    assert out.exists() and out.read_bytes()[:5] == b"%PDF-"
