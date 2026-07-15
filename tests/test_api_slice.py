"""API + state-machine tests (LLD §11). Uses FastAPI TestClient against a temp
DB seeded with a prepared Application — no network, no LLM. Asserts auth, the
approval flow, illegal-transition rejection, and the no-'applied'-from-'prepared'
invariant (SECURITY.md T3/T9)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from jobup.api.main import create_app
from jobup.db import Store
from jobup.models import (
    Application,
    Enrichment,
    JobPosting,
    JobSourceType,
    MatchResult,
    TailoredResume,
    fingerprint_for,
    job_id_for,
)

TOKEN = "test-token"


def _seed(db_path) -> str:
    from datetime import datetime, timezone
    url = "https://example.com/swe"
    job = JobPosting(
        id=job_id_for(url), source=JobSourceType.GREENHOUSE, source_ref="1",
        company="Acme", title="New Grad SWE", location="Remote",
        description_raw="Build Python services.", description_clean="Build Python services.",
        posted_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        apply_url=url, canonical_url=url,
        fingerprint=fingerprint_for("Acme", "New Grad SWE", "Remote"),
    )
    resume = TailoredResume(job_id=job.id, resume_markdown="# Resume\n- did things.",
                            factual_check_passed=True)
    app = Application(job_id=job.id, tailored_resume=resume,
                      enrichment=Enrichment(job_id=job.id, team="Payments"),
                      answers={"github": "gh"}, unanswered=["portfolio"],
                      apply_url=url)
    store = Store(db_path)
    store.upsert_application(job, app, MatchResult(job_id=job.id, relevant=True, score=0.82))
    store.close()
    return job.id


@pytest.fixture
def client(tmp_path):
    db = tmp_path / "t.sqlite3"
    app_id = _seed(db)
    c = TestClient(create_app(store_path=str(db), token=TOKEN))
    return c, app_id


AUTH = {"X-JobUp-Token": TOKEN}


def test_requires_token(client):
    c, app_id = client
    assert c.get("/api/applications").status_code == 401
    assert c.get("/api/applications", headers=AUTH).status_code == 200


def test_list_and_bundle(client):
    c, app_id = client
    rows = c.get("/api/applications", headers=AUTH).json()
    assert len(rows) == 1 and rows[0]["score"] == 0.82
    bundle = c.get(f"/api/applications/{app_id}", headers=AUTH).json()
    assert bundle["title"] == "New Grad SWE"
    assert bundle["enrichment"]["team"] == "Payments"
    assert "resume_markdown" in bundle["tailored_resume"]


def test_bundle_has_posted_date_and_jd(client):
    c, app_id = client
    b = c.get(f"/api/applications/{app_id}", headers=AUTH).json()
    assert b["posted_at"].startswith("2026-06-01")
    assert "Python services" in b["description"]


def test_filters(client):
    c, app_id = client
    # score filter (seeded score 0.82)
    assert len(c.get("/api/applications?min_score=0.9", headers=AUTH).json()) == 0
    assert len(c.get("/api/applications?min_score=0.8", headers=AUTH).json()) == 1
    # search + company + posted_since
    assert len(c.get("/api/applications?q=grad", headers=AUTH).json()) == 1
    assert len(c.get("/api/applications?q=nomatch", headers=AUTH).json()) == 0
    assert len(c.get("/api/applications?company=Acme", headers=AUTH).json()) == 1
    assert len(c.get("/api/applications?posted_since=2027-01-01", headers=AUTH).json()) == 0
    assert c.get("/api/companies", headers=AUTH).json() == ["Acme"]


def test_resume_markdown_served(client):
    c, app_id = client
    r = c.get(f"/api/applications/{app_id}/resume.md", headers=AUTH)
    assert r.status_code == 200 and "# Resume" in r.text


def test_full_approval_flow(client):
    c, app_id = client
    assert c.post(f"/api/applications/{app_id}/approve", headers=AUTH).json()["status"] == "approved"
    assert c.post(f"/api/applications/{app_id}/mark-applied", headers=AUTH).json()["status"] == "applied"


def test_agent_cannot_jump_prepared_to_applied(client):
    # The invariant: 'applied' is only reachable from 'approved'. A direct
    # prepared -> applied attempt is rejected (409).
    c, app_id = client
    r = c.post(f"/api/applications/{app_id}/mark-applied", headers=AUTH)
    assert r.status_code == 409 and "illegal transition" in r.json()["detail"]


def test_patch_answers_clears_unanswered(client):
    c, app_id = client
    bundle = c.patch(f"/api/applications/{app_id}", headers=AUTH,
                     json={"answers": {"portfolio": "https://me.dev"}}).json()
    assert "portfolio" not in bundle["unanswered"]
    assert bundle["answers"]["portfolio"] == "https://me.dev"


def test_skip_then_no_further_transition(client):
    c, app_id = client
    assert c.post(f"/api/applications/{app_id}/skip", headers=AUTH).json()["status"] == "skipped"
    assert c.post(f"/api/applications/{app_id}/approve", headers=AUTH).status_code == 409


def test_ats_in_bundle(client):
    c, app_id = client
    b = c.get(f"/api/applications/{app_id}", headers=AUTH).json()
    assert "ats" in b and "score" in b["ats"]        # keyword-match computed


def test_stats(client):
    c, app_id = client
    s = c.get("/api/stats", headers=AUTH).json()
    assert s["total"] == 1 and s["by_status"]["prepared"] == 1


def test_bulk_action_approve(client):
    c, app_id = client
    res = c.post("/api/applications/bulk-action", headers=AUTH,
                 json={"action": "approve", "ids": [app_id]}).json()
    assert res[app_id] == "ok"
    assert c.get(f"/api/applications/{app_id}", headers=AUTH).json()["status"] == "approved"


def test_get_profile(client):
    c, _ = client
    d = c.get("/api/profile", headers=AUTH).json()
    assert "profile" in d and "answers" in d


def test_resume_library(client):
    c, _ = client
    assert c.get("/api/resumes", headers=AUTH).json() == []          # empty
    r = c.post("/api/resumes", headers=AUTH, json={"from_profile": True}).json()
    assert len(r["resumes"]) == 1                                    # saved from profile
    rid = r["resumes"][0]["id"]
    assert r["resumes"][0]["is_default"] is True                     # first is auto-default
    body = c.get(f"/api/resumes/{rid}", headers=AUTH).json()
    assert body["markdown"].startswith("#")                          # markdown resume
    assert c.get(f"/api/resumes/{rid}/pdf", headers=AUTH).content[:5] == b"%PDF-"
    assert c.delete(f"/api/resumes/{rid}", headers=AUTH).json()["resumes"] == []


def test_default_resume_switch(client):
    c, _ = client
    a = c.post("/api/resumes", headers=AUTH, json={"name": "A", "markdown": "# A"}).json()["resumes"][0]["id"]
    c.post("/api/resumes", headers=AUTH, json={"name": "B", "markdown": "# B"})
    # first (A) is default; switch default to the second
    lst = c.get("/api/resumes", headers=AUTH).json()
    assert sum(r["is_default"] for r in lst) == 1
    b = next(r["id"] for r in lst if not r["is_default"])
    lst2 = c.post(f"/api/resumes/{b}/default", headers=AUTH).json()["resumes"]
    assert next(r["is_default"] for r in lst2 if r["id"] == b) is True
    assert next(r["is_default"] for r in lst2 if r["id"] == a) is False


def test_needs_attention_and_fit_order(client):
    c, app_id = client
    # seeded resume passed its factual check -> not in the needs-attention bucket
    assert len(c.get("/api/applications?needs_attention=true", headers=AUTH).json()) == 0
    assert len(c.get("/api/applications?needs_attention=false", headers=AUTH).json()) == 1
    # fit ordering is accepted and returns the app
    rows = c.get("/api/applications?order=fit", headers=AUTH).json()
    assert len(rows) == 1


def test_package_zip_download(client):
    c, app_id = client
    r = c.get(f"/api/applications/{app_id}/package.zip", headers=AUTH)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    assert r.content[:2] == b"PK"                    # zip magic
    import io, zipfile
    names = set(zipfile.ZipFile(io.BytesIO(r.content)).namelist())
    assert "checklist.md" in names and "resume.pdf" in names


def test_finalize_approves_and_generates(tmp_path):
    from jobup.llm.client import FakeLLM, FactualCheck
    db = tmp_path / "f.sqlite3"
    app_id = _seed(db)

    def parse_fn(user, schema):
        return {"passed": True, "unsupported_claims": [], "notes": ""}
    llm = FakeLLM(parse_fn=parse_fn,
                  generate_fn=lambda u: "Dear Acme,\nI built Python services.\nRegards")
    c = TestClient(create_app(store_path=str(db), token=TOKEN, llm=llm))
    b = c.post(f"/api/applications/{app_id}/finalize", headers=AUTH).json()
    assert b["status"] == "approved"                 # advanced from prepared
    assert b["cover_letter"].startswith("Dear Acme")
    assert b["why_this_company"]                      # per-job answer generated
    assert "why_this_company" not in b["unanswered"] # moved into answers


def test_run_status_idle(client):
    c, _ = client
    s = c.get("/api/run", headers=AUTH).json()
    assert s["running"] is False


def test_upload_resume_endpoint(tmp_path, monkeypatch):
    from jobup.db import Store as _S
    from jobup.llm.client import FakeLLM
    from jobup.models import UserProfile
    db = tmp_path / "u.sqlite3"; _S(db).close()
    # stub extraction so the endpoint test doesn't touch disk or the network
    monkeypatch.setattr("jobup.api.main.ingest_resume",
                        lambda data, fn, llm: (UserProfile(name="Extracted"), {"github": "g"}))
    app = create_app(store_path=str(db), token=TOKEN, llm=FakeLLM())
    c = TestClient(app)
    r = c.post("/api/profile/upload", headers=AUTH,
               files={"file": ("resume.txt", b"resume text", "text/plain")})
    assert r.status_code == 200
    assert r.json()["profile"]["name"] == "Extracted"
