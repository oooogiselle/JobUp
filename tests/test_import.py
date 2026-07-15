"""Import-jobs tests (offline). CSV/JSON parsing + tailor-through-pipeline."""

from __future__ import annotations

from jobup.import_jobs import import_and_prepare, parse_import
from jobup.llm.client import FakeLLM
from jobup.models import JobSourceType, UserProfile

CSV = (
    "Company,Title,Location,Apply Link,Description\n"
    "Meta,Software Engineer New Grad,Menlo Park,https://metacareers.com/jobs/1,We use Python and React.\n"
    "Google,,NYC,https://google.com/2,missing title -> skipped\n"
    ",Backend Engineer,Remote,https://ex.com/3,no company still ok\n"
)

JSON = (
    '[{"company":"Amazon","title":"SDE I","url":"https://amazon.jobs/4","description":"Java, AWS."},'
    '{"role":"Data Engineer","link":"https://ex.com/5"}]'  # alias keys
)


def test_parse_csv_aliases_and_skips():
    jobs = parse_import(CSV.encode(), "jobs.csv")
    titles = [(j.company, j.title) for j in jobs]
    assert ("Meta", "Software Engineer New Grad") in titles
    assert ("(imported)", "Backend Engineer") in titles     # missing company -> placeholder
    assert all(t != "" for _, t in titles)                  # missing-title row skipped
    assert len(jobs) == 2
    assert jobs[0].source is JobSourceType.IMPORTED
    assert "Python and React" in jobs[0].description_clean


def test_parse_json_with_alias_keys():
    jobs = parse_import(JSON.encode(), "jobs.json")
    assert {j.title for j in jobs} == {"SDE I", "Data Engineer"}
    assert any(j.apply_url.endswith("/4") for j in jobs)


def test_import_and_prepare_tailors(tmp_path):
    from jobup.db import Store
    profile = UserProfile(name="X", skills=["python"])
    llm = FakeLLM(
        parse_fn=lambda user, schema: {"passed": True, "unsupported_claims": [], "notes": ""}
        if "fact" in schema.__name__.lower() else {"needs_heavy_rewrite": False, "rationale": ""},
        generate_fn=lambda user: "# Resume\n- did things",
    )
    store = Store(tmp_path / "t.sqlite3")
    jobs = parse_import(JSON.encode(), "jobs.json")
    apps = import_and_prepare(jobs, profile, {"github": "g"}, llm, store)
    assert len(apps) == 2
    # persisted + reviewable, status prepared (human still applies)
    rows = store.list_applications()
    assert len(rows) == 2 and all(r["status"] == "prepared" for r in rows)
    # re-import is idempotent (already stored)
    assert import_and_prepare(jobs, profile, {}, llm, store) == []
    store.close()
