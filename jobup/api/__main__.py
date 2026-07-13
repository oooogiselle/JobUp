"""Run the approval API + dashboard locally: `python -m jobup.api`.

Binds 127.0.0.1 only (SECURITY.md T9) — never expose this without adding real
auth/TLS. Prints the localhost URL with the token so you can open it directly."""

from __future__ import annotations

import argparse

import uvicorn

from ..config import load_settings
from ..env import load_env
from .main import create_app


def main() -> None:
    ap = argparse.ArgumentParser(description="JobUp approval dashboard")
    ap.add_argument("--config", default="config/config.yaml")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()

    load_env()
    settings = load_settings(args.config)
    app = create_app(store_path=settings.db_path)
    token = app.state.token
    print("\n  JobUp dashboard →  "
          f"http://127.0.0.1:{args.port}/\n  (token in data/.jobup_token)\n")
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
