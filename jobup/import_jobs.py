"""Import jobs from anywhere (CSV/JSON) and run them through the full pipeline.

You source jobs however you like — an N8N flow, a LinkedIn CSV export, a
spreadsheet — and JobUp ingests them and tailors/packages them like any other
posting. This keeps the core tool ToS-clean (JobUp never scrapes) while letting
you feed it from any external tool you choose.

Accepted columns (case-insensitive, common aliases handled):
  company, title (required), location, apply_url/url/link (required),
  description (optional — enables good tailoring), posted_at (optional).
"""

from __future__ import annotations

import argparse
import csv
import io
import json

from .config import load_settings
from .db import Store
from .env import load_env
from .llm.client import AnthropicLLM, LLMClient
from .models import Application, JobPosting, JobSourceType, RawPosting
from .pipeline.enrich import enrich
from .pipeline.normalize import normalize
from .pipeline.package import build_application
from .pipeline.tailor import tailor
from .profile import load_answers, load_profile

_ALIASES = {
    "company": ["company", "employer", "organization", "org"],
    "title": ["title", "role", "position", "job title", "job", "job_title"],
    "location": ["location", "city", "where", "locations"],
    "apply_url": ["apply_url", "url", "link", "apply", "application", "apply link", "job url", "joburl"],
    "description": ["description", "jd", "details", "job description", "job_description"],
    "posted_at": ["posted_at", "date", "posted", "date posted", "date_posted"],
}


def _get(row: dict, key: str) -> str:
    norm = {(k or "").strip().lower(): v for k, v in row.items()}
    for alias in _ALIASES[key]:
        if norm.get(alias):
            return str(norm[alias])
    return ""


def parse_import(data: bytes, filename: str = "") -> list[JobPosting]:
    """CSV or JSON bytes -> normalized JobPostings. Rows missing title or URL
    are skipped."""
    text = data.decode("utf-8", errors="replace").strip()
    if filename.lower().endswith(".json") or text[:1] in "[{":
        obj = json.loads(text)
        rows = obj if isinstance(obj, list) else obj.get("jobs", [])
    else:
        rows = list(csv.DictReader(io.StringIO(text)))
    out: list[JobPosting] = []
    for r in rows:
        title, url = _get(r, "title").strip(), _get(r, "apply_url").strip()
        if not title or not url:
            continue
        out.append(normalize(RawPosting(
            source=JobSourceType.IMPORTED, source_ref=url,
            company=_get(r, "company").strip() or "(imported)", title=title,
            location=_get(r, "location").strip() or None,
            apply_url=url, canonical_url=url,
            description_raw=_get(r, "description").strip(),
        )))
    return out


def import_and_prepare(jobs: list[JobPosting], profile, answers: dict,
                       llm: LLMClient, store: Store) -> list[Application]:
    """Tailor + verify + package each imported job (no relevance gate — you chose
    them). Already-imported jobs are skipped. Same factual verifier applies."""
    apps: list[Application] = []
    for job in jobs:
        if store.get_application(job.id) is not None:
            continue
        resume = tailor(job, profile, llm, answers=answers)
        app = build_application(job, resume, enrich(job), answers, profile=profile)
        # match=None -> score stored as None (user-selected, not AI-scored)
        store.upsert_application(job, app, None)
        apps.append(app)
    return apps


def main() -> None:
    ap = argparse.ArgumentParser(description="Import jobs (CSV/JSON) into JobUp")
    ap.add_argument("file", help="path to a .csv or .json file of jobs")
    args = ap.parse_args()

    load_env()
    import os
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY not set — needed to tailor imported jobs.")

    settings = load_settings()
    with open(args.file, "rb") as f:
        jobs = parse_import(f.read(), args.file)
    print(f"parsed {len(jobs)} jobs from {args.file}")
    if not jobs:
        return
    store = Store(settings.db_path)
    llm = AnthropicLLM()
    apps = import_and_prepare(jobs, load_profile(), load_answers(), llm, store)
    print(f"imported + tailored {len(apps)} new job(s) — review in the dashboard")
    c = llm.cost_summary()
    print(f"(LLM this run: ${c['cost_usd']} · {c['input_tokens']} in / {c['output_tokens']} out)")


if __name__ == "__main__":
    main()
