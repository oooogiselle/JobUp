"""Load secrets from a git-ignored .env into the process environment (SECURITY.md
T5). Called by the CLI entrypoints before any secret is read. .env is never
committed; an existing real environment variable always wins over the file."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv


def load_env() -> None:
    # Search from the working dir upward; no-op if no .env exists.
    load_dotenv(dotenv_path=_find_dotenv(), override=False)


def _find_dotenv() -> str | None:
    for parent in [Path.cwd(), *Path.cwd().parents]:
        candidate = parent / ".env"
        if candidate.exists():
            return str(candidate)
    return None
