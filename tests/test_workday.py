"""Workday connector parser tests (offline)."""

from __future__ import annotations

from jobup.models import JobSourceType
from jobup.sources.workday import _parse_careers_url, parse_workday

PAYLOAD = {
    "total": 2,
    "jobPostings": [
        {"title": "Software Engineer, New Grad", "externalPath": "/job/Santa-Clara/SWE_123",
         "locationsText": "Santa Clara, CA", "postedOn": "Posted 3 Days Ago"},
        {"title": "ML Engineer", "externalPath": "/job/Remote/ML_456",
         "locationsText": "Remote, USA", "postedOn": "Posted Today"},
        {"title": "No path role", "locationsText": "NYC"},   # skipped (no path)
    ],
}


def test_parse_careers_url():
    netloc, tenant, locale, site = _parse_careers_url(
        "https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite")
    assert netloc == "nvidia.wd5.myworkdayjobs.com"
    assert tenant == "nvidia" and locale == "en-US" and site == "NVIDIAExternalCareerSite"


def test_parse_workday_maps_fields():
    posts = parse_workday(PAYLOAD, "nvidia.wd5.myworkdayjobs.com", "en-US",
                          "NVIDIAExternalCareerSite", "NVIDIA")
    assert len(posts) == 2                      # third has no path
    p = posts[0]
    assert p.source is JobSourceType.WORKDAY
    assert p.title == "Software Engineer, New Grad"
    assert p.location == "Santa Clara, CA"
    assert p.apply_url == ("https://nvidia.wd5.myworkdayjobs.com/en-US/"
                           "NVIDIAExternalCareerSite/job/Santa-Clara/SWE_123")
    assert p.posted_at is not None
    assert posts[1].posted_at is not None       # "Posted Today"
