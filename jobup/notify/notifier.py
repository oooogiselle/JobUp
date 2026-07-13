"""Real-time notifier orchestration (LLD §8 C10, FR16).

`notify_new_applications` finds prepared applications that clear the alert
threshold and haven't been alerted yet, sends one batched alert, and marks them
notified — so reruns don't re-notify (idempotent, LLD §10)."""

from __future__ import annotations

import os

from ..config import Settings
from ..db import Store
from .base import ConsoleNotifier, Notifier, format_alert


def build_notifier(settings: Settings) -> Notifier:
    """Gmail SMTP if credentials + a recipient are configured, else console.
    Credentials: GMAIL_ADDRESS + GMAIL_APP_PASSWORD in the environment/.env."""
    sender = os.environ.get("GMAIL_ADDRESS")
    password = os.environ.get("GMAIL_APP_PASSWORD")
    recipient = (settings.notify or {}).get("email")
    if sender and password and recipient:
        from .email_smtp import SmtpEmailNotifier
        return SmtpEmailNotifier(sender=sender, password=password, recipient=recipient)
    return ConsoleNotifier()


def notify_new_applications(store: Store, notifier: Notifier,
                            min_score_alert: float = 0.7,
                            dashboard_url: str = "http://127.0.0.1:8765/") -> int:
    apps = store.unnotified_applications(min_score=min_score_alert)
    if not apps:
        return 0
    notifier.send(format_alert(apps, dashboard_url))
    store.mark_notified([a["id"] for a in apps])
    return len(apps)
