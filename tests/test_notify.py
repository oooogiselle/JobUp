"""Notifier tests (offline). Covers alert formatting, threshold filtering,
idempotency (no re-notify), and SMTP message construction — no network."""

from __future__ import annotations

from jobup.db import Store
from jobup.models import (
    Application,
    JobPosting,
    JobSourceType,
    MatchResult,
    TailoredResume,
    fingerprint_for,
    job_id_for,
)
from jobup.notify.base import ConsoleNotifier, format_alert
from jobup.notify.email_smtp import SmtpEmailNotifier
from jobup.notify.notifier import notify_new_applications


class FakeNotifier:
    name = "fake"

    def __init__(self):
        self.sent = []

    def send(self, n):
        self.sent.append(n)


def _seed(store: Store, title: str, score: float, ok: bool = True) -> str:
    url = f"https://ex.com/{title}".replace(" ", "-")
    job = JobPosting(id=job_id_for(url), source=JobSourceType.GREENHOUSE, source_ref="1",
                     company="Stripe", title=title, location="Remote",
                     apply_url=url, canonical_url=url,
                     fingerprint=fingerprint_for("Stripe", title, "Remote"))
    resume = TailoredResume(job_id=job.id, resume_markdown="# r", factual_check_passed=ok)
    app = Application(job_id=job.id, tailored_resume=resume, apply_url=url)
    store.upsert_application(job, app, MatchResult(job_id=job.id, relevant=True, score=score))
    return job.id


# --- formatting ------------------------------------------------------------

def test_format_alert_content():
    n = format_alert([
        {"title": "New Grad SWE", "company": "Stripe", "location": "Remote",
         "score": 0.86, "team": "Payments", "factual_check_passed": True,
         "apply_url": "https://x/1"},
        {"title": "Full-Stack", "company": "Stripe", "location": "Remote",
         "score": 0.71, "team": "Growth", "factual_check_passed": False,
         "apply_url": "https://x/2"},
    ])
    assert n.count == 2 and "2 new match" in n.subject
    assert "New Grad SWE" in n.body and "https://x/1" in n.body
    assert "FACTUAL CHECK" in n.body          # the failed one is flagged
    assert "never submits" in n.body


# --- orchestration ---------------------------------------------------------

def test_notify_sends_batched_then_idempotent(tmp_path):
    store = Store(tmp_path / "t.sqlite3")
    _seed(store, "New Grad SWE", 0.86)
    _seed(store, "Backend Engineer", 0.74)
    fake = FakeNotifier()

    sent = notify_new_applications(store, fake, min_score_alert=0.7)
    assert sent == 2 and len(fake.sent) == 1 and fake.sent[0].count == 2  # one batched alert

    # rerun: nothing new -> no alert (idempotent)
    assert notify_new_applications(store, fake, min_score_alert=0.7) == 0
    assert len(fake.sent) == 1
    store.close()


def test_notify_respects_threshold(tmp_path):
    store = Store(tmp_path / "t.sqlite3")
    _seed(store, "Strong Match", 0.86)
    _seed(store, "Weak Match", 0.62)
    fake = FakeNotifier()
    sent = notify_new_applications(store, fake, min_score_alert=0.8)
    assert sent == 1                       # only the 0.86 clears 0.8
    store.close()


def test_only_prepared_are_notified(tmp_path):
    store = Store(tmp_path / "t.sqlite3")
    jid = _seed(store, "Approved One", 0.9)
    store.update_status(jid, "approved")   # no longer 'prepared'
    fake = FakeNotifier()
    assert notify_new_applications(store, fake, min_score_alert=0.5) == 0
    store.close()


# --- SMTP message construction (no send) -----------------------------------

def test_smtp_builds_message():
    n = format_alert([{"title": "T", "company": "C", "location": "Remote",
                       "score": 0.9, "team": "X", "factual_check_passed": True,
                       "apply_url": "https://x/1"}])
    notifier = SmtpEmailNotifier(sender="me@gmail.com", password="app-pw",
                                 recipient="me@gmail.com")
    msg = notifier._build_message(n)
    assert msg["To"] == "me@gmail.com" and msg["From"] == "me@gmail.com"
    assert msg["Subject"] == n.subject
    assert "T" in msg.get_content()


def test_console_notifier_smoke(capsys):
    ConsoleNotifier().send(format_alert([]))
    assert "JobUp" in capsys.readouterr().out
