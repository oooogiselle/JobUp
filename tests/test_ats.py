"""ATS keyword-match tests (offline, deterministic)."""

from __future__ import annotations

from jobup.ats import keyword_match, keywords_in


def test_keywords_in_detects_tech():
    kw = keywords_in("We use Python, React, and Kubernetes on AWS.")
    assert {"python", "react", "kubernetes", "aws"} <= kw


def test_keyword_match_present_and_missing():
    jd = "Looking for Python, Go, Kubernetes, and distributed systems experience."
    resume = "Built Python services. Comfortable with Go."
    m = keyword_match(jd, resume)
    assert "python" in m.present and "go" in m.present
    assert "kubernetes" in m.missing and "distributed systems" in m.missing
    assert 0 < m.score < 1
    assert m.jd_total == 4


def test_keyword_match_full_coverage():
    m = keyword_match("Python and SQL.", "Python and SQL expert.")
    assert m.score == 1.0 and m.missing == []


def test_keyword_match_no_jd_keywords():
    m = keyword_match("A friendly team that values collaboration.", "Python dev")
    assert m.score == 1.0 and m.jd_total == 0


def test_java_not_matched_by_javascript():
    assert "java" not in keywords_in("We use JavaScript heavily.")
    assert "javascript" in keywords_in("We use JavaScript heavily.")
