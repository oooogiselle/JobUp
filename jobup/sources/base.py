"""Source connector contract (LLD §3). Each connector fetches raw postings and is
run in isolation by the orchestrator so one failing source never fails the run
(ARCHITECTURE P4)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ..models import RawPosting


@runtime_checkable
class SourceConnector(Protocol):
    name: str

    async def fetch(self) -> list[RawPosting]:
        ...


@dataclass
class ConnectorResult:
    name: str
    postings: list[RawPosting]
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None
