"""Simplify GitHub connector parser tests (offline, representative fixture)."""

from __future__ import annotations

from jobup.models import JobSourceType
from jobup.sources.simplify import parse_simplify

README = """
# New Grad Positions

| Company | Role | Location | Application/Link | Date Posted |
| ------- | ---- | -------- | ---------------- | ----------- |
| **[Stripe](https://simplify.jobs/c/Stripe)** | Software Engineer, New Grad | NYC | <a href="https://stripe.com/jobs/123"><img src="x" alt="Apply"></a> <a href="https://simplify.jobs/p/abc"><img src="y"></a> | Jul 12 |
| ↳ | Backend Engineer | SF</br>Remote | <a href="https://stripe.com/jobs/456">Apply</a> | Jul 11 |
| **[Acme](https://simplify.jobs/c/Acme)** | Data Scientist 🔒 | Boston | <a href="https://acme.com/x">Apply</a> 🔒 | Jul 10 |
| **[Globex](https://simplify.jobs/c/Globex)** | ML Engineer | Remote | <a href="https://globex.com/careers/9">Apply</a> | Jul 9 |

Some other text, not a table.
"""


def test_parse_simplify_rows():
    posts = parse_simplify(README)
    titles = [(p.company, p.title) for p in posts]
    # Stripe row + continuation row (inherits Stripe) + Globex; Acme is closed (🔒)
    assert ("Stripe", "Software Engineer, New Grad") in titles
    assert ("Stripe", "Backend Engineer") in titles          # ↳ inherits company
    assert ("Globex", "ML Engineer") in titles
    assert all(c != "Acme" for c, _ in titles)               # locked row skipped


def test_parse_simplify_prefers_direct_url_over_simplify():
    p = next(p for p in parse_simplify(README) if p.title == "Software Engineer, New Grad")
    assert p.apply_url == "https://stripe.com/jobs/123"      # not the simplify.jobs link
    assert p.source is JobSourceType.SIMPLIFY


def test_parse_simplify_multi_location():
    p = next(p for p in parse_simplify(README) if p.title == "Backend Engineer")
    assert "SF" in p.location and "Remote" in p.location


def test_parse_simplify_empty():
    assert parse_simplify("no table here") == []


# The current README uses HTML <tr>/<td> rows.
HTML_README = """
<table>
<tr><th>Company</th><th>Role</th><th>Location</th><th>Application</th><th>Age</th></tr>
<tr><td><strong><a href="https://simplify.jobs/c/Toast">Toast</a></strong></td><td>Software Engineer, Fullstack</td><td>Toronto, ON</td><td><div align="center"><a href="https://boards.greenhouse.io/embed/job_app?token=8046879">Apply</a></div></td><td>2d</td></tr>
<tr><td>↳</td><td>Backend Engineer</td><td>NYC</td><td><a href="https://jobs.ashbyhq.com/toast/abc/application">Apply</a></td><td>2d</td></tr>
<tr><td><strong><a href="https://simplify.jobs/c/Acme">Acme</a></strong></td><td>Data Scientist</td><td>Boston</td><td>🔒</td><td>5d</td></tr>
</table>
"""


def test_parse_simplify_html_format():
    posts = parse_simplify(HTML_README)
    pairs = [(p.company, p.title) for p in posts]
    assert ("Toast", "Software Engineer, Fullstack") in pairs
    assert ("Toast", "Backend Engineer") in pairs           # ↳ inherits Toast
    assert all(c != "Acme" for c, _ in pairs)               # locked skipped
    toast = next(p for p in posts if p.title == "Backend Engineer")
    assert "ashbyhq.com" in toast.apply_url                 # direct URL, not simplify
