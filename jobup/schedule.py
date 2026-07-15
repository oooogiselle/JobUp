"""launchd scheduling (LLD §6, PRD D5). Installs two macOS LaunchAgents:

  - com.jobup.prepare   — runs `python -m jobup.prepare` every poll_interval_min
                          (periodic; catches up on wake).
  - com.jobup.dashboard — keeps `python -m jobup.api` (the review dashboard on
                          http://127.0.0.1:8765) running, restarting it if it dies.

    python -m jobup.schedule install     # write + load both agents
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

PREPARE_LABEL = "com.jobup.prepare"
DASHBOARD_LABEL = "com.jobup.dashboard"
REPO_ROOT = Path(__file__).resolve().parent.parent
LAUNCH_AGENTS = Path.home() / "Library" / "LaunchAgents"

# Periodic worker: discover -> match -> tailor -> package on an interval.
_PREPARE_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
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

# Long-running dashboard: keep the local review UI up (restart if it exits).
_DASHBOARD_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>{label}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python}</string>
        <string>-m</string><string>jobup.api</string>
    </array>
    <key>WorkingDirectory</key><string>{workdir}</string>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>{log}</string>
    <key>StandardErrorPath</key><string>{err}</string>
</dict>
</plist>
"""


def _plist_path(label: str) -> Path:
    return LAUNCH_AGENTS / f"{label}.plist"


def _logdir() -> Path:
    d = REPO_ROOT / "data" / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _render_prepare() -> str:
    settings = load_settings(REPO_ROOT / "config" / "config.yaml")
    interval = max(60, int(settings.poll_interval_min) * 60)
    log = _logdir()
    return _PREPARE_PLIST.format(
        label=PREPARE_LABEL, python=sys.executable, workdir=str(REPO_ROOT),
        interval=interval, log=str(log / "prepare.out.log"),
        err=str(log / "prepare.err.log"))


def _render_dashboard() -> str:
    log = _logdir()
    return _DASHBOARD_PLIST.format(
        label=DASHBOARD_LABEL, python=sys.executable, workdir=str(REPO_ROOT),
        log=str(log / "dashboard.out.log"), err=str(log / "dashboard.err.log"))


def _load(label: str, contents: str) -> bool:
    path = _plist_path(label)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents)
    domain = f"gui/{os.getuid()}"
    subprocess.run(["launchctl", "bootout", domain, str(path)], capture_output=True)
    r = subprocess.run(["launchctl", "bootstrap", domain, str(path)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        r = subprocess.run(["launchctl", "load", "-w", str(path)],
                           capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  ✗ {label}: launchctl load failed — {r.stderr.strip()}")
        print(f"    Load manually: launchctl bootstrap {domain} {path}")
    return r.returncode == 0


def _unload(label: str) -> None:
    domain = f"gui/{os.getuid()}"
    path = _plist_path(label)
    subprocess.run(["launchctl", "bootout", domain, str(path)], capture_output=True)
    if path.exists():
        path.unlink()
    print(f"✓ Removed {label}.")


def install() -> None:
    settings = load_settings(REPO_ROOT / "config" / "config.yaml")
    ok_prepare = _load(PREPARE_LABEL, _render_prepare())
    ok_dash = _load(DASHBOARD_LABEL, _render_dashboard())
    if ok_prepare:
        print(f"✓ {PREPARE_LABEL} — pipeline runs every {settings.poll_interval_min} min.")
    if ok_dash:
        print(f"✓ {DASHBOARD_LABEL} — dashboard stays up at http://127.0.0.1:8765/")
    print(f"  logs: {REPO_ROOT / 'data' / 'logs'}/")
    print("  Note: agents run while you're logged in; asleep runs catch up on wake.")


def uninstall() -> None:
    _unload(PREPARE_LABEL)
    _unload(DASHBOARD_LABEL)


def status() -> None:
    domain = f"gui/{os.getuid()}"
    for label in (PREPARE_LABEL, DASHBOARD_LABEL):
        r = subprocess.run(["launchctl", "print", f"{domain}/{label}"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            print(f"{label}: not loaded")
            continue
        fields = [ln.strip() for ln in r.stdout.splitlines()
                  if any(k in ln for k in ("state =", "pid =", "runs =", "last exit"))]
        print(f"{label}: " + " · ".join(fields))


def main() -> None:
    ap = argparse.ArgumentParser(description="Manage the JobUp launchd schedule")
    ap.add_argument("action", choices=["install", "uninstall", "status"])
    args = ap.parse_args()
    {"install": install, "uninstall": uninstall, "status": status}[args.action]()


if __name__ == "__main__":
    main()
