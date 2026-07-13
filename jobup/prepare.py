"""Prepare applications (LLD §12 steps 3-6): match -> enrich -> tailor -> package.

`prepare_job` is pure (job + profile + llm -> Application | None) so it is fully
testable offline with a FakeLLM. The CLI wires discovery to prepare_job using the
real Anthropic client when ANTHROPIC_API_KEY is set. Nothing here submits an
application (SECURITY.md invariant #1)."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from .config import Settings, load_settings
from .db import Store
from .env import load_env
from .llm.client import AnthropicLLM, LLMClient
from .notify.notifier import build_notifier, notify_new_applications
from .models import Application, JobPosting, UserProfile
from .pipeline.enrich import enrich
from .pipeline.match import match
from .pipeline.package import build_application
from .pipeline.tailor import tailor
from .profile import load_answers, load_profile
from .run import fetch_jobs


def _build(job: JobPosting, profile: UserProfile, answers: dict,
           llm: LLMClient) -> Application:
    """enrich -> tailor -> package (assumes the job already passed matching)."""
    enrichment = enrich(job)
    resume = tailor(job, profile, llm)
    return build_application(job, resume, enrichment, answers)


def prepare_job(job: JobPosting, profile: UserProfile, answers: dict,
                llm: LLMClient, min_score: float = 0.6) -> Application | None:
    """Run one job through the intelligence pipeline. Returns a prepared
    Application, or None if the job is not relevant."""
    if not match(job, profile, llm, min_score=min_score).relevant:
        return None
    return _build(job, profile, answers, llm)


def _write_resume(app: Application, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{app.job_id[:12]}.md"
    path.write_text(app.tailored_resume.resume_markdown)
    return path


async def prepare(settings: Settings, profile: UserProfile, answers: dict,
                  llm: LLMClient, limit: int = 5, max_scan: int = 20,
                  store: "Store | None" = None) -> list[Application]:
    """Prepare up to `limit` applications, scanning at most `max_scan` postings
    (a cost cap: bounds triage LLM calls per run — LLD §10 / NFR4). When `store`
    is given, each prepared application is persisted for the approval dashboard."""
    jobs, _ = await fetch_jobs(settings)
    apps: list[Application] = []
    scanned = 0
    for job in jobs:
        if len(apps) >= limit or scanned >= max_scan:
            break
        # Skip postings already prepared in a previous run — don't re-spend LLM
        # calls on them (keeps scheduled runs cheap; only new jobs cost tokens).
        if store is not None and store.get_application(job.id) is not None:
            continue
        scanned += 1
        result = match(job, profile, llm, settings.min_score)
        if not result.relevant:
            continue
        app = _build(job, profile, answers, llm)
        if store is not None:
            store.upsert_application(job, app, result)
        apps.append(app)
    return apps


def main() -> None:
    ap = argparse.ArgumentParser(description="JobUp: prepare applications")
    ap.add_argument("--config", default="config/config.yaml")
    ap.add_argument("--limit", type=int, default=3,
                    help="max relevant applications to prepare this run")
    ap.add_argument("--max-scan", type=int, default=20,
                    help="max postings to triage this run (cost cap)")
    args = ap.parse_args()

    load_env()  # pull ANTHROPIC_API_KEY from a git-ignored .env if present
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit(
            "ANTHROPIC_API_KEY is not set. The prepare pipeline needs it for "
            "matching/tailoring. Set it in your environment and retry.")

    settings = load_settings(args.config)
    profile = load_profile()
    answers = load_answers()
    llm = AnthropicLLM()
    store = Store(settings.db_path)

    apps = asyncio.run(prepare(settings, profile, answers, llm,
                               limit=args.limit, max_scan=args.max_scan,
                               store=store))
    print(f"(persisted to {settings.db_path} — review at the dashboard)")

    # Real-time alert for newly-prepared matches (batched, idempotent).
    notifier = build_notifier(settings)
    threshold = float((settings.notify or {}).get("min_score_alert", 0.7))
    sent = notify_new_applications(store, notifier, min_score_alert=threshold)
    print(f"(notified {sent} new match(es) via {notifier.name})")

    cost = llm.cost_summary()
    print(f"(LLM this run: ${cost['cost_usd']} · {cost['input_tokens']} in / "
          f"{cost['output_tokens']} out tokens)")

    print(f"\n=== JobUp prepared {len(apps)} application(s) ===")
    out_dir = Path("resumes")
    for app in apps:
        r = app.tailored_resume
        path = _write_resume(app, out_dir)
        team = app.enrichment.team if app.enrichment else None
        flag = "" if r.factual_check_passed else "  ⚠️ FACTUAL CHECK FAILED"
        heavy = "  (heavier rewrite recommended)" if r.needs_heavy_rewrite else ""
        print(f"\n• {app.job_id[:12]}  team={team}{flag}{heavy}")
        print(f"    apply: {app.apply_url}")
        print(f"    resume: {path}")
        if r.unsupported_claims:
            print(f"    unsupported claims: {r.unsupported_claims}")
        if app.unanswered:
            print(f"    please answer: {app.unanswered}")


if __name__ == "__main__":
    main()
