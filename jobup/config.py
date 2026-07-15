"""Config loading (LLD §9). YAML for filters/watchlist; secrets come from env,
never from this file (docs/SECURITY.md T5)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class SourcesConfig:
    greenhouse_tokens: list[str] = field(default_factory=list)
    lever_tokens: list[str] = field(default_factory=list)
    ashby_tokens: list[str] = field(default_factory=list)
    simplify_repos: list[str] = field(default_factory=list)
    workday_sites: list[str] = field(default_factory=list)
    company_sites: list[dict] = field(default_factory=list)
    indeed: dict = field(default_factory=dict)
    # Optional display-name overrides: {"token": "Company Name"}
    company_names: dict = field(default_factory=dict)


@dataclass
class Settings:
    poll_interval_min: int = 20
    daily_summary_at: str = "08:00"
    min_score: float = 0.6
    target: dict = field(default_factory=dict)
    sources: SourcesConfig = field(default_factory=SourcesConfig)
    llm: dict = field(default_factory=dict)
    notify: dict = field(default_factory=dict)
    db_path: str = "data/jobup.sqlite3"

    @property
    def anthropic_api_key(self) -> str | None:
        return os.environ.get("ANTHROPIC_API_KEY")


def load_settings(path: str | Path = "config/config.yaml") -> Settings:
    data: dict = {}
    p = Path(path)
    if p.exists():
        data = yaml.safe_load(p.read_text()) or {}
    src = data.get("sources", {}) or {}
    return Settings(
        poll_interval_min=int(data.get("poll_interval_min", 20)),
        daily_summary_at=data.get("daily_summary_at", "08:00"),
        min_score=float(data.get("min_score", 0.6)),
        target=data.get("target", {}) or {},
        sources=SourcesConfig(
            greenhouse_tokens=src.get("greenhouse_tokens", []) or [],
            lever_tokens=src.get("lever_tokens", []) or [],
            ashby_tokens=src.get("ashby_tokens", []) or [],
            simplify_repos=src.get("simplify_repos", []) or [],
            workday_sites=src.get("workday_sites", []) or [],
            company_sites=src.get("company_sites", []) or [],
            indeed=src.get("indeed", {}) or {},
            company_names=src.get("company_names", {}) or {},
        ),
        llm=data.get("llm", {}) or {},
        notify=data.get("notify", {}) or {},
        db_path=data.get("db_path", "data/jobup.sqlite3"),
    )
