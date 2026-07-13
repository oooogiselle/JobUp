# JobUp — Conceptual Architecture (CA / High-Level Design)

**Status:** Draft v1 · **Companion to:** `PRD.md`, `LLD.md`

---

## 1. Architecture at a Glance

JobUp is a **local-first, frequently-scheduled pipeline** with a thin approval web
app. A trigger fires on a short interval (default every ~20 min) and runs a
stateless orchestrator through a linear pipeline (ingest → normalize → dedup →
match → **enrich** → tailor → fill → package → notify). New relevant postings fire
a **per-job real-time alert**; a daily email adds a summary. All state lives in
SQLite. A FastAPI service + React dashboard let the human review and approve.
Nothing is ever submitted automatically.

**Timeliness (G8):** because new-grad roles close fast, cadence is frequent polling,
not daily. Local-first hits low latency only while the machine is awake; the runner
is **stateless and cloud-ready** so migrating to an always-on cloud VM/worker for
true real-time (laptop closed) is a deployment change, not a rewrite (§6).

```
                          ┌──────────────────────────────────────────────┐
                          │        SCHEDULER (launchd / cloud timer)      │
                          │   every ~20 min, on-wake catchup, portable    │
                          └───────────────────────┬──────────────────────┘
                                                  │ triggers
                                                  ▼
┌───────────────────────────────  ORCHESTRATOR (pipeline runner)  ───────────────────────────────┐
│                                                                                                 │
│  1. INGEST            2. NORMALIZE     3. DEDUP        4. MATCH          5. TAILOR      6. FILL   │
│  ┌───────────────┐    ┌──────────┐    ┌────────┐     ┌───────────┐    ┌──────────┐  ┌────────┐  │
│  │ Greenhouse    │    │          │    │ seen-  │     │ rules +   │    │ resume   │  │ answer │  │
│  │ Lever         │───▶│ map to   │──▶ │ store  │──▶  │ LLM       │──▶ │ tailor   │─▶│ profile│  │
│  │ Ashby         │    │ JobPost- │    │ cross- │     │ relevance │    │ +factual │  │ prefill│  │
│  │ Indeed (MCP)  │    │ ing      │    │ source │     │ + score   │    │ verifier │  │        │  │
│  │ Simplify repo │    │ schema   │    │ dedup  │     │ +hard     │    │ +PDF     │  │        │  │
│  │ Company crawl │    │          │    │        │     │ filters   │    │ render   │  │        │  │
│  └───────────────┘    └──────────┘    └────────┘     └───────────┘    └──────────┘  └────────┘  │
│         │                                  │               │                │            │       │
│         └── untrusted input boundary ──────┴───────────────┴────────────────┴────────────┘       │
│                                                                                     │           │
│                                                              7. PACKAGE + ENQUEUE    ▼           │
│                                                              ┌──────────────────────────────┐    │
│                                                              │  Approval Queue (SQLite)     │    │
│                                                              └───────────────┬──────────────┘    │
└──────────────────────────────────────────────────────────────────────────── │ ──────────────────┘
                                                                               │
                        8. NOTIFY                                              │
              ┌──────────────────────────┐                                    │
              │ Real-time per-job alert  │◀───────────────────────────────────┤
              │ (push/email) + daily     │   fires as each relevant job is     │
              │ summary digest           │   prepared, rate-limited            │
              └──────────────────────────┘                                    │
                                                                              ▼
   ┌───────────────────────────┐        HTTP        ┌────────────────────────────────────────┐
   │  React Dashboard (local)  │ ◀───────────────▶  │  FastAPI Approval API                  │
   │  review · edit · approve  │                    │  /jobs /applications /approve /config  │
   │  mark-applied             │                    └───────────────────┬────────────────────┘
   └───────────────────────────┘                                        │
                                                                        ▼
                                                        ┌────────────────────────────┐
                                                        │  SQLite (single source of  │
                                                        │  truth) + local file store │
                                                        │  for resume PDFs           │
                                                        └────────────────────────────┘
   HUMAN reviews → clicks through on the real job site → presses APPLY  (agent never submits)
```

## 2. Design Principles

- **P1 — Human-in-the-loop is structural, not optional.** There is no code path
  that submits an application. The pipeline ends at "packaged + notified."
- **P2 — Untrusted-input boundary.** Everything from a source (esp. job description
  text) is untrusted. It is treated as *data*, never as instructions to the LLM.
- **P3 — Grounded generation.** The tailor never invents facts; it only rearranges
  and rephrases content that exists in the user's experience library.
- **P4 — Per-source isolation.** One source failing (API down, ToS change) degrades
  gracefully; the run continues with the others.
- **P5 — Stateless runner, stateful store.** The orchestrator holds no state between
  runs; SQLite is the single source of truth → portable and restartable.
- **P6 — Idempotent runs.** Re-running the same day produces no duplicates and no
  double-notifications (dedup + run ledger).
- **P7 — Cheap-model triage, strong-model craft.** A cheap model does relevance
  triage at volume; a strong model does the smaller number of tailoring jobs.

## 3. Components

| # | Component | Responsibility | Key tech |
|---|-----------|----------------|----------|
| C1 | **Scheduler** | Fire the daily run; catch up missed runs | macOS `launchd` (cron fallback) |
| C2 | **Orchestrator** | Drive the pipeline, isolate failures, write run ledger | Python, `asyncio` |
| C3 | **Source Connectors** | One adapter per source → raw postings | `httpx`, Indeed MCP, GitHub API |
| C4 | **Normalizer** | Map raw → canonical `JobPosting` | Pydantic |
| C5 | **Dedup / Seen-store** | Cross-source dedup; ensure surface-once | SQLite |
| C6 | **Relevance Matcher** | Hard filters + rules + LLM relevance & scoring | rules + cheap LLM |
| C6b | **Contact/Team Enricher** | Extract hiring team/org + recruiter/contact from JD & ATS metadata (no fabrication, no private-profile scraping) | rules + LLM extraction |
| C7 | **Resume Tailor** | Light (or heavy-on-approval) tailoring + factual verifier + PDF | strong LLM, resume-tailoring skill, WeasyPrint/Typst |
| C8 | **Application Filler** | Map answer profile → application questions | Python |
| C9 | **Packager / Queue** | Assemble application bundle, enqueue for approval | SQLite |
| C10 | **Notifier** | Daily email digest + push | Gmail MCP / SMTP |
| C11 | **Approval API** | Serve queue, accept edits/approvals/status | FastAPI |
| C12 | **Dashboard** | Human review & approval UI | React + Vite |
| C13 | **Config store** | Watchlist, filters, prefs, answer profile | YAML + SQLite |
| C14 | **Audit log** | Every action, per run, reproducible | SQLite |

## 4. Data Flow (one daily run)

1. **Scheduler** triggers **Orchestrator**; a `Run` row opens in the ledger.
2. **Connectors** (C3) fetch postings concurrently; each yields raw records +
   provenance. Failures are logged per-source, not fatal.
3. **Normalizer** (C4) maps every raw record to a `JobPosting`.
4. **Dedup** (C5): drop postings already in the seen-store or duplicated this run.
5. **Matcher** (C6): apply hard filters → cheap-LLM relevance + score → keep those
   above threshold. Rejected postings are recorded (with reason) but not surfaced.
5b. **Enricher** (C6b): for each kept posting, extract the hiring **team/org** and,
   when the source exposes it, the **recruiter/contact** (name, role, channel) from
   JD text + ATS metadata. If absent → `recruiter: unknown` (never invented).
6. **Tailor** (C7): for each kept posting, produce a light-aligned resume grounded
   in the experience library; run the **factual verifier**; if light alignment is
   weak, mark `needs_heavy_rewrite` and queue a notification. Render PDF.
7. **Filler** (C8): pre-fill answers from the profile; flag unknown questions.
8. **Packager** (C9): create an `Application` (status `prepared`) with resume, diff,
   answers, apply URL; enqueue.
9. **Notifier** (C10): fire a **real-time alert per newly-prepared application**
   (rate-limited/batched during bursts); append to the daily summary. Close the `Run` row.
10. **Human**: reviews in the **Dashboard** (C12 → C11), edits/approves, applies on
    the job site, marks `applied`. Status transitions logged (C14).

## 5. External Interfaces

| Interface | Direction | Notes |
|-----------|-----------|-------|
| Greenhouse `boards-api.greenhouse.io/v1/boards/{token}/jobs` | in | Public JSON, no auth |
| Lever `api.lever.co/v0/postings/{token}` | in | Public JSON |
| Ashby `api.ashbyhq.com/posting-api/job-board/{token}` | in | Public JSON |
| Indeed MCP tools | in | `search_jobs`, `get_job_details` |
| Simplify GitHub repos | in | Raw README/JSON via GitHub API |
| Company career sites (custom) | in | Fetch + content-diff, robots-aware, rate-limited |
| Anthropic API (Claude) | out | Triage (cheap model) + tailoring (strong model) |
| Gmail MCP / SMTP | out | Digest email |
| Job site apply pages | out | Opened by the **human** in a browser — not by the agent |

## 6. Deployment (phased for timeliness — G8)

- **Phase 1 (local-first):** `launchd` runs `python -m jobup.run` **every ~20 min**
  (`StartInterval`), catching up on wake. FastAPI + React run on `localhost`. SQLite +
  `resumes/` under the app data dir. Low latency *while the laptop is awake*.
- **Phase 2 (cloud, always-on — real-time):** move the runner to a small always-on
  VM (or serverless cron/worker) so postings are caught and alerts fire even when the
  laptop is closed. Push alerts (email/Push/Telegram) reach the phone in minutes.
  The dashboard/API can stay local (reading a synced DB) or move to the VM behind auth.
- **Portability (why Phase 2 is cheap):** the runner is **stateless** and all state is
  in SQLite. Migration = copy the DB, set the same `.env`, install a systemd timer /
  serverless schedule. **No code change** — only config + where it runs.
- **Migration triggers:** you want alerts while away from your machine; or polling
  cadence needs to be tighter than a sometimes-asleep laptop can honor.
- **Data/secrets note:** Phase 2 moves PII + secrets off-device — handle per
  `SECURITY.md` (encrypted secrets store, least-privilege VM, no public exposure).

## 7. Technology Choices (summary)

- **Language:** Python 3.11+ (agent) + TypeScript/React (dashboard).
- **Web:** FastAPI + Uvicorn; React + Vite.
- **Data:** SQLite via SQLModel/SQLAlchemy; Pydantic for schemas.
- **HTTP:** `httpx` (async).
- **LLM:** Anthropic Claude — cheap model (e.g. Haiku) for triage, strong model
  (e.g. Opus/Sonnet) for tailoring; reuse the `resume-tailoring` skill's method.
- **PDF:** Typst or WeasyPrint (ATS-friendly, text-selectable output).
- **Scheduling:** launchd (macOS) / systemd timer or cron (Linux).
- **Secrets:** macOS Keychain or `.env` (git-ignored).

## 8. Cross-Cutting Concerns

- **Security & privacy:** local PII, secrets in keychain, prompt-injection defense at
  the untrusted-input boundary, no auto-submit. Detailed in `SECURITY.md` (later phase).
- **Observability:** structured per-run logs + audit table; a run summary in the digest.
- **Error handling:** per-source try/except, exponential backoff on transient errors,
  idempotent writes, a run ledger to make reruns safe.
- **Cost control:** batch triage prompts, cache JD→relevance, only invoke the strong
  model on postings that pass the filter.

## 9. Traceability to PRD

| PRD | Component(s) |
|-----|--------------|
| FR1–FR5 (discovery) | C3, C4, C5 |
| FR6–FR8 (match) | C6 |
| FR9–FR12 (tailor) | C7 |
| FR13–FR14 (fill) | C8 |
| FR15–FR18 (approval) | C9, C10, C11, C12 |
| FR19–FR20 (config/audit) | C13, C14 |
| NFR1/2 (privacy/security) | SQLite-local, keychain, P2 boundary |
| NFR5/6 (reliability/portability) | P4, P5, P6, C2, C14 |
