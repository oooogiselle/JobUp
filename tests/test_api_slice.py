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
