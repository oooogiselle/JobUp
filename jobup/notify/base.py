"""Notification model, formatting, and the console backend (LLD §8 C10, FR16).

A real-time alert fires per polling cycle for newly-prepared matches. Alerts are
batched (one message per run) so a burst of new postings doesn't spam you."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class Notification:
    subject: str
    body: str
    count: int


class Notifier(Protocol):
    def send(self, n: Notification) -> None: ...


def format_alert(apps: list[dict], dashboard_url: str = "http://127.0.0.1:8765/") -> Notification:
    """Build a per-run alert from newly-prepared applications. Time-sensitive by
    design (new-grad roles close fast), so it leads with 'apply soon'."""
    n = len(apps)
    subject = f"JobUp: {n} new match{'es' if n != 1 else ''} — review & apply"
    lines = [f"{n} new relevant posting{'s' if n != 1 else ''} prepared. "
             "New-grad roles close fast — review and apply soon.\n"]
    for a in apps:
        score = f"{a['score']*100:.0f}%" if a.get("score") is not None else "—"
        flag = "" if a.get("factual_check_passed") else "  ⚠ FACTUAL CHECK — review before sending"
        lines.append(f"• {a.get('title','?')} — {a.get('company','?')} "
                     f"({a.get('location') or '—'})")
        lines.append(f"    fit {score} · team {a.get('team') or 'unknown'}{flag}")
        if a.get("apply_url"):
            lines.append(f"    apply: {a['apply_url']}")
    lines.append(f"\nReview in the dashboard: {dashboard_url}")
    lines.append("You press apply — JobUp never submits for you.")
    return Notification(subject=subject, body="\n".join(lines), count=n)


class ConsoleNotifier:
    """Default backend: print the alert. Always available; used in tests and when
    no email credentials are configured."""

    name = "console"

    def send(self, n: Notification) -> None:
        print(f"\n[notify] {n.subject}\n{n.body}\n")
