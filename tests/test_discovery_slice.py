"""Offline tests for the discovery slice (LLD §11). No network: exercises the
pure parse -> normalize -> dedup -> seen-store path against a fixture."""

from __future__ import annotations

import json
from pathlib import Path

from jobup.db import Store
from jobup.models import JobSourceType, job_id_for
from jobup.pipeline.dedup import dedup
from jobup.pipeline.normalize import normalize
from jobup.sources.greenhouse import parse_greenhouse

FIXTURE = Path(__file__).parent / "fixtures" / "greenhouse_stripe.json"


def _fixture_jobs():
    payload = json.loads(FIXTURE.read_text())
    raws = parse_greenhouse(payload, company="Stripe")
    return [normalize(r) for r in raws]


def test_parse_greenhouse_strips_html_and_maps_fields():
    payload = json.loads(FIXTURE.read_text())
    raws = parse_greenhouse(payload, company="Stripe")
    assert len(raws) == 3  # includes the duplicate row
    first = raws[0]
    assert first.source is JobSourceType.GREENHOUSE
    assert first.company == "Stripe"
    assert first.title == "New Grad Software Engineer"
    assert first.location == "San Francisco, CA"
    # HTML tags + entities stripped to plain text (untrusted-data hygiene)
    assert "<" not in first.description_raw and "&lt;" not in first.description_raw
    assert "Payments Infra" in first.description_raw


def test_normalize_produces_stable_id_and_remote_flag():
    jobs = _fixture_jobs()
    remote_job = next(j for j in jobs if j.title.startswith("Staff"))
    assert remote_job.remote is True
    # id is deterministic from canonical_url
    assert jobs[0].id == job_id_for(jobs[0].canonical_url)


def test_dedup_within_run_collapses_duplicate(tmp_path):
    store = Store(tmp_path / "t.sqlite3")
    jobs = _fixture_jobs()          # 3 rows, 2 unique
    result = dedup(jobs, store)
    assert len(result.fresh) == 2
    assert result.duplicates == 1
    store.close()


def test_dedup_against_store_is_idempotent(tmp_path):
    db = tmp_path / "t.sqlite3"
    store = Store(db)
    jobs = _fixture_jobs()
    first = dedup(jobs, store)
    for j in first.fresh:
        store.insert(j)
    # second run: everything already seen -> nothing fresh (surface-once, FR5)
    second = dedup(jobs, store)
    assert second.fresh == []
    assert store.count() == 2
    store.close()
