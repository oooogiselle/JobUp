"""Discovery entrypoint (LLD §12 steps 1-2): `python -m jobup.run`.

This first slice runs: ingest (Greenhouse) -> normalize -> dedup -> seen-store.
Matching, enrichment, tailoring, filling, packaging, and notify land in later
slices. Nothing here submits anything (docs/SECURITY.md invariant #1)."""

from __future__ import annotations

import argparse
import asyncio

import httpx

from .config import Settings, load_settings
from .db import Store
from .pipeline.dedup import dedup
from .pipeline.normalize import normalize
from .sources.ashby import AshbyConnector
from .sources.base import ConnectorResult
from .sources.greenhouse import GreenhouseConnector
from .sources.lever import LeverConnector
from .sources.simplify import SimplifyConnector
from .sources.workday import WorkdayConnector


def build_connectors(settings: Settings, client: httpx.AsyncClient):
    connectors = []
    names = settings.sources.company_names
    for token in settings.sources.greenhouse_tokens:
        connectors.append(GreenhouseConnector(token, company=names.get(token), client=client))
    for token in settings.sources.lever_tokens:
        connectors.append(LeverConnector(token, company=names.get(token), client=client))
    for token in settings.sources.ashby_tokens:
        connectors.append(AshbyConnector(token, company=names.get(token), client=client))
    for repo in settings.sources.simplify_repos:
        connectors.append(SimplifyConnector(repo, client=client))
    for site in settings.sources.workday_sites:
        connectors.append(WorkdayConnector(site, company=names.get(site), client=client))
    # Indeed MCP / custom company crawl added later.
    return connectors


async def run_connector(c) -> ConnectorResult:
    """Per-source isolation (ARCHITECTURE P4): a failing source never fails the run."""
    try:
        postings = await asyncio.wait_for(c.fetch(), timeout=60)
        return ConnectorResult(name=c.name, postings=postings)
    except Exception as e:  # noqa: BLE001 - deliberately broad; isolate the source
        return ConnectorResult(name=c.name, postings=[], error=f"{type(e).__name__}: {e}")


async def fetch_jobs(settings: Settings):
    """Fetch + normalize from all connectors (no persistence). Returns
    (normalized jobs, per-source ConnectorResults). Shared by discover + prepare."""
    async with httpx.AsyncClient(timeout=30) as client:
        connectors = build_connectors(settings, client)
        results = await asyncio.gather(*(run_connector(c) for c in connectors))
    raw = [p for r in results for p in r.postings]
    return [normalize(p) for p in raw], results


async def discover(settings: Settings, dry_run: bool = False) -> dict:
    store = Store(settings.db_path)
    jobs, results = await fetch_jobs(settings)
    raw = [p for r in results for p in r.postings]
    dd = dedup(jobs, store)

    if not dry_run:
        for job in dd.fresh:
            store.insert(job)

    # Aggregate per source type (there may be many boards of the same kind).
    from collections import defaultdict
    agg: dict = defaultdict(lambda: {"jobs": 0, "boards": 0, "failed": 0})
    for r in results:
        a = agg[r.name]
        a["boards"] += 1
        if r.ok:
            a["jobs"] += len(r.postings)
        else:
            a["failed"] += 1
    summary = {
        "sources": {k: f"{v['jobs']} jobs from {v['boards'] - v['failed']}/{v['boards']} boards"
                    for k, v in agg.items()},
        "errors": {r.name: r.error for r in results if not r.ok},
        "ingested": len(raw),
        "normalized": len(jobs),
        "fresh": len(dd.fresh),
        "duplicates": dd.duplicates,
        "persisted": 0 if dry_run else len(dd.fresh),
        "store_total": store.count(),
        "dry_run": dry_run,
    }
    store.close()
    return summary


def _print_summary(s: dict) -> None:
    print("\n=== JobUp discovery run ===")
    for name, val in s["sources"].items():
        print(f"  source {name:12} -> {val}")
    print(f"  ingested   : {s['ingested']}")
    print(f"  fresh      : {s['fresh']}")
    print(f"  duplicates : {s['duplicates']}")
    print(f"  persisted  : {s['persisted']}{'  (dry-run)' if s['dry_run'] else ''}")
    print(f"  store total: {s['store_total']}")
    if s["errors"]:
        print("  source errors:")
        for name, err in s["errors"].items():
            print(f"    {name}: {err}")


def main() -> None:
    ap = argparse.ArgumentParser(description="JobUp daily discovery run")
    ap.add_argument("--config", default="config/config.yaml")
    ap.add_argument("--dry-run", action="store_true",
                    help="fetch + dedup but do not persist to the seen-store")
    args = ap.parse_args()

    settings = load_settings(args.config)
    summary = asyncio.run(discover(settings, dry_run=args.dry_run))
    _print_summary(summary)


if __name__ == "__main__":
    main()
