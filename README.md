# JobUp

A personal, **human-in-the-loop** new-grad job-application agent. It discovers
relevant postings frequently, lightly tailors your resume to each (never
fabricating anything), extracts the hiring team/recruiter when exposed, pre-fills
application answers, and alerts you in real time. **You press apply — it never
submits on your own.**

## Docs
- [`docs/PRD.md`](docs/PRD.md) — product requirements
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — conceptual/component architecture
- [`docs/LLD.md`](docs/LLD.md) — low-level design
- [`docs/SECURITY.md`](docs/SECURITY.md) — threat model & invariants

## Status
Implemented:
1. **Discovery** — **Greenhouse + Lever + Ashby + Simplify GitHub** ingest →
   normalize → cross-source dedup → seen-store (`jobup.run`). Configure tokens/repos
   in `config/config.yaml` (thousands of postings/run).
2. **Prepare** — match (hard filters → Sonnet triage) → enrich (team) → tailor
   (Opus, grounded) → factual verify → package (`jobup.prepare`). The factual
   verifier is a hard gate; the agent never submits.
3. **Approval dashboard** — FastAPI + React approval queue (`jobup.api`): filter
   (search / company / fit / status / posted date), review each application
   (structured JD, autofilled answers, factual-check flags, team, posted date),
   download the **ATS-friendly resume PDF**, **assisted apply** (opens the form
   and autofills it + attaches the PDF — you submit), then approve / mark-applied.
   The state machine makes `applied` reachable only from `approved`.
4. **Real-time notifier** — `jobup.prepare` sends a batched alert for new matches
   (console by default; Gmail SMTP when credentials are set). Idempotent.
5. **Industry-grade dashboard** — Queue/Profile tabs, stats bar, bulk approve/skip,
   keyboard shortcuts (`j`/`k`/`a`/`s`/`o`), **ATS keyword-match** meter, toasts.
6. **Profile + resume upload** — upload a PDF/text resume; it's extracted into your
   profile + autofill answers (grounded, nothing invented), editable in the UI.

Scheduling (launchd) and the security review are next (see LLD §12).

## Setup
```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Run
```bash
# fetch + dedup, no writes:
.venv/bin/python -m jobup.run --dry-run

# real run (persists to the local seen-store):
.venv/bin/python -m jobup.run

# prepare tailored applications for the top relevant jobs (needs ANTHROPIC_API_KEY):
export ANTHROPIC_API_KEY=sk-ant-...          # or put it in a git-ignored .env
.venv/bin/python -m jobup.prepare --limit 3 --max-scan 40

# open the approval dashboard (review, approve, mark-applied):
.venv/bin/python -m jobup.api                # http://127.0.0.1:8765/

# optional: assisted apply — opens the real form and autofills it (you submit):
pip install playwright && playwright install chromium
#   then use the "Assisted apply" button in the dashboard, or:
.venv/bin/python -m jobup.apply <app_id> --dry-run   # preview the autofill values

# run automatically every N minutes (macOS launchd; interval from config):
.venv/bin/python -m jobup.schedule install     # start
.venv/bin/python -m jobup.schedule status
.venv/bin/python -m jobup.schedule uninstall   # stop

# tests (offline, fixture-based, no API key needed):
.venv/bin/python -m pytest tests/ -q
```

Each `prepare` run prints its LLM cost, skips already-prepared postings (cheap
reruns), and only spends on new jobs — so the scheduled job stays inexpensive.

**Indeed:** not wired as a connector — Indeed has no free public API, and its MCP
tool is only available inside a Claude agent runtime (not this standalone process).
When JobUp runs under an agent/cloud runtime, an Indeed-MCP connector can be added.

A demo queue is pre-seeded, so `jobup.api` shows two example applications
(one verified, one with a factual-check failure) on first run. Delete
`data/jobup.sqlite3` to start empty.

Configure sources/filters in [`config/config.yaml`](config/config.yaml). Copy
[`config/profile.example.yaml`](config/profile.example.yaml) →
`config/profile.yaml` (git-ignored) with your real experience library. Secrets
(e.g. `ANTHROPIC_API_KEY`) come from the environment, never the repo.
