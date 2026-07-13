"""Dedup (LLD §5-step, C5). Two layers:
  1. within-run: collapse identical ids and fingerprints seen this run;
  2. against the seen-store: drop anything surfaced on a previous run.
Ensures a posting is surfaced to the user at most once (FR5) and reruns are
idempotent (LLD §10)."""

from __future__ import annotations

from dataclasses import dataclass

from ..db import Store
from ..models import JobPosting


@dataclass
class DedupResult:
    fresh: list[JobPosting]      # new this run, not seen before
    duplicates: int             # dropped as dupes (within-run or already stored)


def dedup(jobs: list[JobPosting], store: Store) -> DedupResult:
    fresh: list[JobPosting] = []
    seen_ids: set[str] = set()
    seen_fps: set[str] = set()
    dupes = 0

    for job in jobs:
        if job.id in seen_ids or job.fingerprint in seen_fps:
            dupes += 1
            continue
        if store.is_seen(job.id) or store.fingerprint_seen(job.fingerprint):
            dupes += 1
            continue
        seen_ids.add(job.id)
        seen_fps.add(job.fingerprint)
        fresh.append(job)

    return DedupResult(fresh=fresh, duplicates=dupes)
