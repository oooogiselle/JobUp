"""Gmail SMTP notifier (LLD §8 C10). Sends the real-time alert as an email.

Credentials come from the environment (a Gmail address + an app password), never
the repo (SECURITY.md T5). Message construction is split out so it is testable
without sending. Note: PRD R1 preferred Gmail MCP, but the scheduled runner is a
plain Python process with no MCP access, so SMTP is the deliverable backend; a
Gmail-MCP sender can be plugged in when running under an agent."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from .base import Notification


class SmtpEmailNotifier:
    name = "email"

    def __init__(self, sender: str, password: str, recipient: str,
                 host: str = "smtp.gmail.com", port: int = 587):
        self.sender = sender
        self.password = password
        self.recipient = recipient
        self.host = host
        self.port = port

    def _build_message(self, n: Notification) -> EmailMessage:
        msg = EmailMessage()
        msg["From"] = self.sender
        msg["To"] = self.recipient
        msg["Subject"] = n.subject
        msg.set_content(n.body)
        return msg

    def send(self, n: Notification) -> None:  # pragma: no cover - network/creds
        msg = self._build_message(n)
        with smtplib.SMTP(self.host, self.port) as s:
            s.starttls()
            s.login(self.sender, self.password)
            s.send_message(msg)
