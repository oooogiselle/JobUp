"""launchd scheduling (LLD §6, PRD D5). Installs a macOS LaunchAgent that runs
`python -m jobup.prepare` on the configured interval, catching up on wake.

    python -m jobup.schedule install     # write + load the agent
    python -m jobup.schedule status
    python -m jobup.schedule uninstall

The runner is stateless (all state in SQLite), so this is the local-first path;
moving to an always-on cloud timer later is the same command elsewhere."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from .config import load_settings

LABEL = "com.jobup.prepare"
REPO_ROOT = Path(__file__).resolve().parent.parent
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"

_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>{label}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python}</string>
        <string>-m</string><string>jobup.prepare</string>
        <string>--limit</string><string>10</string>
        <string>--max-scan</string><string>40</string>
    </array>
    <key>WorkingDirectory</key><string>{workdir}</string>
    <key>StartInterval</key><integer>{interval}</integer>
    <key>RunAtLoad</key><true/>
    <key>StandardOutPath</key><string>{log}</string>
    <key>StandardErrorPath</key><string>{err}</string>
</dict>
</plist>
"""


def _render() -> str:
    settings = load_settings(REPO_ROOT / "config" / "config.yaml")
    interval = max(60, int(settings.poll_interval_min) * 60)
    logdir = REPO_ROOT / "data" / "logs"
    logdir.mkdir(parents=True, exist_ok=True)
    return _PLIST.format(
        label=LABEL, python=sys.executable, workdir=str(REPO_ROOT),
        interval=interval, log=str(logdir / "prepare.out.log"),
        err=str(logdir / "prepare.err.log"),
    )


def install() -> None:
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.write_text(_render())
    domain = f"gui/{os.getuid()}"
    subprocess.run(["launchctl", "bootout", domain, str(PLIST_PATH)],
                   capture_output=True)  # remove any prior instance (ignore errors)
    r = subprocess.run(["launchctl", "bootstrap", domain, str(PLIST_PATH)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        r = subprocess.run(["launchctl", "load", "-w", str(PLIST_PATH)],
                           capture_output=True, text=True)
    settings = load_settings(REPO_ROOT / "config" / "config.yaml")
    if r.returncode == 0:
        print(f"✓ Installed {LABEL} — runs every {settings.poll_interval_min} min.")
        print(f"  plist: {PLIST_PATH}")
        print(f"  logs:  {REPO_ROOT / 'data' / 'logs'}/prepare.*.log")
        print("  Note: it runs while you're logged in; asleep runs catch up on wake.")
    else:
        print("Wrote the plist but launchctl load failed. Load it manually:")
        print(f"  launchctl bootstrap {domain} {PLIST_PATH}")
        print(r.stderr.strip())


def uninstall() -> None:
    domain = f"gui/{os.getuid()}"
    subprocess.run(["launchctl", "bootout", domain, str(PLIST_PATH)], capture_output=True)
    if PLIST_PATH.exists():
        PLIST_PATH.unlink()
    print(f"✓ Removed {LABEL}.")


def status() -> None:
    domain = f"gui/{os.getuid()}"
    r = subprocess.run(["launchctl", "print", f"{domain}/{LABEL}"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(f"{LABEL} is not loaded. Run: python -m jobup.schedule install")
        return
    for line in r.stdout.splitlines():
        if any(k in line for k in ("state =", "pid =", "runs =", "last exit")):
            print(line.strip())


def main() -> None:
    ap = argparse.ArgumentParser(description="Manage the JobUp launchd schedule")
    ap.add_argument("action", choices=["install", "uninstall", "status"])
    args = ap.parse_args()
    {"install": install, "uninstall": uninstall, "status": status}[args.action]()


if __name__ == "__main__":
    main()
