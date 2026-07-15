# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

JobUp is a personal, local-first **new-grad job-application agent**. A scheduled Python pipeline discovers postings, matches + tailors a resume to each (grounded, never fabricated), and packages them for a human to review and apply. A FastAPI + single-file React dashboard is the approval surface. Design docs: `docs/{PRD,ARCHITECTURE,LLD,SECURITY}.md`.

### Two hard invariants (do not break; they're enforced in code, not prompts)
1. **The agent never submits an application.** The `application` status machine (`db.py` `ALLOWED_TRANSITIONS`) makes `applied` reachable only from `approved`, and only via a human-initiated API call. No code path submits externally.
2. **Never fabricates.** Every tailored resume and cover letter passes a factual verifier (`pipeline/tailor.py::verify_factual`) against the user's experience library; unsupported claims block/flag it. Sources are official ATS APIs / curated GitHub lists / user CSV imports only — **no scraping** (LinkedIn/Indeed excluded by design).

## Commands

```bash
# setup
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# run the pipeline (needs ANTHROPIC_API_KEY in .env)
.venv/bin/python -m jobup.run --dry-run          # discovery only (free, no LLM)
.venv/bin/python -m jobup.prepare --limit 10 --max-scan 50   # discover→match→tailor→notify
.venv/bin/python -m jobup.import_jobs jobs.csv   # import external jobs (CSV/JSON) → tailor
.venv/bin/python -m jobup.api                    # dashboard at http://127.0.0.1:8765/
.venv/bin/python -m jobup.schedule install|status|uninstall   # macOS launchd every N min

# tests (offline, no API key — LLM is faked)
.venv/bin/python -m pytest tests/ -q
.venv/bin/python -m pytest tests/test_match_tailor_slice.py::test_tailor_catches_planted_fabrication -q   # single test
```

Secrets live in git-ignored `.env`; the dashboard API token auto-generates into `data/.jobup_token`. Sources/filters are configured in `config/config.yaml`; the user's profile + answers are git-ignored PII (`config/profile.yaml`, `config/answer_profile.yaml`; `*.example.yaml` are the committed templates).

## Architecture

**Pipeline (the spine):** `jobup/run.py` (discovery) and `jobup/prepare.py` (the intelligence run) drive stages in `jobup/pipeline/`: `match` (free rule-based `hard_filters` then Sonnet `triage`) → `enrich` (team/recruiter, extraction-only) → `tailor` (Opus draft → `verify_factual` → fit assessment) → `package` (build an `Application`). `prepare.py` sorts jobs **newest-posted-first across all sources** and skips already-prepared jobs so scheduled reruns only spend LLM tokens on new postings; `--max-scan` caps *triage calls*, not jobs scanned (hard-filter rejects are free).

**Sources (`jobup/sources/`):** one connector per ATS — `greenhouse`, `lever`, `ashby` (public JSON), `workday` (careers-URL → cxs POST endpoint; how FAANG+ like Nvidia/Salesforce come in), `simplify` (parses SimplifyJobs-style GitHub new-grad tables, both HTML `<tr>` and markdown). Each has a **pure `parse_*(payload)` function** (unit-tested with fixtures) separate from async `fetch()`. `build_connectors()` in `run.py` wires them from config; the orchestrator runs each in isolation so one failing source never fails the run (`ConnectorResult`). User imports (`jobup/import_jobs.py`) are a sixth "source" that feeds the same tailor pipeline.

**LLM layer (`jobup/llm/`):** all model access goes through the `LLMClient` protocol (`client.py`) with two methods — `parse()` (structured JSON via `messages.parse`, for triage/verify/fit) and `generate()` (adaptive-thinking text, for tailoring/cover letters). `AnthropicLLM` is the real impl (tracks token cost); **`FakeLLM` makes the whole pipeline testable offline** — every test injects it. Models: Opus 4.8 tailoring, Sonnet 5 everything else. **Injection defense** (`guards.py`): JD text is untrusted — `sanitize_jd` + `<job_description>` fencing + a data-only system rule, and generation calls pass **no tools**. Prompts are centralized in `prompts.py` (`_fenced_jd` is the single choke point for untrusted JD).

**Storage (`jobup/db.py`):** a single SQLite `Store` is the source of truth (the runner is stateless → portable to cloud). Tables: `job_posting` (seen-store for dedup), `application` (the review queue + state machine), `resume` (library, one default). Schema changes use the idempotent `_MIGRATIONS` list (ALTER-in on existing DBs), not just `CREATE IF NOT EXISTS`.

**API + dashboard (`jobup/api/`):** `main.py::create_app` is a FastAPI app bound to 127.0.0.1; every `/api/*` route requires the `X-JobUp-Token` header (timing-safe) and responses are `no-store`. `dashboard.py` is a **single-file React app served as one HTML string** (CDN React/Babel, zero build step) with the token substituted in at serve time. Rendering: `jobup/render/resume_pdf.py` (Markdown→ATS-friendly PDF via fpdf2), `master_resume.py` (profile→bulleted markdown). ATS keyword match: `jobup/ats.py`. Resume upload→extraction: `jobup/resume_extract.py`.

## Gotchas that will bite you

- **Resume extraction must NOT use strict structured output** (`messages.parse` with the nested schema) — the API rejects it with `400 "Schema is too complex"`. `resume_extract.py` uses a JSON prompt + tolerant parse on purpose. The smaller triage/verify schemas are fine with `parse()`.
- **SQLite is opened with `check_same_thread=False`** because FastAPI runs sync endpoints across threadpool threads; the single-threaded `TestClient` won't catch a regression here (see `tests/test_db_threading.py`).
- **`config-driven filtering`** lives in `config.yaml → target.roles` (title must contain one) and `target.exclude` (auto-reject); both run in `hard_filters` before any LLM call. `min_score` is the triage threshold.
- Sources that carry **no JD** (Simplify, Workday, most imports) tailor generically — `description_clean` is empty, so ATS/tailoring have less to work with.
- Connectors returning the same `name` are **aggregated** in the discovery summary; don't read per-board counts off `ConnectorResult.name` directly.
