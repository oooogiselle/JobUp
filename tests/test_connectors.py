"""Parser tests for the Lever and Ashby connectors (offline, inline payloads)."""

from __future__ import annotations

from jobup.models import JobSourceType
from jobup.pipeline.normalize import normalize
from jobup.sources.ashby import parse_ashby
from jobup.sources.lever import parse_lever

LEVER_PAYLOAD = [
    {
        "id": "abc-123",
        "text": "New Grad Software Engineer",
        "categories": {"location": "Remote", "team": "Payments", "commitment": "Full-time"},
        "descriptionPlain": "We hire new grads.",
        "lists": [
            {"text": "Responsibilities", "content": "<li>Build Python services.</li><li>Own reliability.</li>"},
            {"text": "Requirements", "content": "<li>0-2 years experience.</li>"},
        ],
        "hostedUrl": "https://jobs.lever.co/acme/abc-123",
        "createdAt": 1751000000000,
    }
]

ASHBY_PAYLOAD = {
    "apiVersion": "1",
    "jobs": [
        {
            "id": "xyz-789",
            "title": "Software Engineer, New Grad",
            "location": "San Francisco",
            "team": "Infrastructure",
            "isRemote": False,
            "descriptionPlain": "Join our infra team.\nResponsibilities\n- Write Go.",
            "jobUrl": "https://jobs.ashbyhq.com/acme/xyz-789",
            "publishedAt": "2026-06-15T10:00:00Z",
        }
    ],
}


def test_parse_lever_maps_fields_and_lists():
    raws = parse_lever(LEVER_PAYLOAD, company="Acme")
    assert len(raws) == 1
    r = raws[0]
    assert r.source is JobSourceType.LEVER
    assert r.title == "New Grad Software Engineer"
    assert r.location == "Remote"
    assert r.apply_url.endswith("abc-123")
    assert "Responsibilities" in r.description_raw and "Build Python services." in r.description_raw
    assert r.extra["team"] == "Payments"
    assert r.posted_at is not None
    # normalizes cleanly into a JobPosting
    job = normalize(r)
    assert job.company == "Acme" and job.id


def test_parse_ashby_maps_fields():
    raws = parse_ashby(ASHBY_PAYLOAD, company="Acme")
    assert len(raws) == 1
    r = raws[0]
    assert r.source is JobSourceType.ASHBY
    assert r.title == "Software Engineer, New Grad"
    assert r.location == "San Francisco"
    assert "Write Go." in r.description_raw
    assert r.extra["team"] == "Infrastructure"
    assert r.posted_at.year == 2026


def test_parse_skips_postings_without_url():
    assert parse_lever([{"text": "No URL role"}], "Acme") == []
    assert parse_ashby({"jobs": [{"title": "No URL role"}]}, "Acme") == []
