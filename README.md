# JobUp

A personal, local-first, **human-in-the-loop new-grad job-application agent.**

A scheduled pipeline discovers fresh postings, matches them to your profile,
tailors your resume to each one (grounded in your real experience — never
fabricated), and packages everything for review. You open a local dashboard,
approve the ones you like, download an apply-ready package, apply yourself, and
mark them applied.

> **Three invariants, enforced in code (not prompts):**
> 1. **It never submits an application.** `applied` is reachable only from
>    `approved`, only when *you* click it. No code path applies for you.
> 2. **It never fabricates.** Every tailored resume and cover letter is checked
>    against your experience library; unsupported claims are flagged, not sent.
> 3. **It never scrapes.** Sources are official ATS APIs, curated GitHub new-grad
>    lists, and your own CSV/JSON imports only — no LinkedIn/Indeed scraping.

---

## TL;DR — the daily rhythm

Once set up, you don't run anything by hand:

1. A background agent runs the pipeline **every 20 minutes** and tailors any new
   postings. It emails/notifies you when a strong match lands.
2. When you get a ping (or whenever), open **http://127.0.0.1:8765/**.
3. Review the fit-sorted queue → **Approve** a job (this auto-writes a grounded,
   fact-checked cover letter + "why this company") → **Download apply package** →
   click the apply link, apply yourself → **mark it applied.**

That's it. The only manual step is the review + apply — by design, because the
agent is never allowed to apply for you.

---

## 1. One-time setup

```bash
# clone, then:
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Anthropic API key — put it in a git-ignored .env file:
echo 'ANTHROPIC_API_KEY=sk-ant-...' > .env
```

Get a key at <https://console.anthropic.com>. The pipeline uses **Claude Opus 4.8**
for resume/cover-letter writing and **Claude Sonnet 5** for matching, fact-checking,
and resume extraction.

## 2. Onboarding — tell it about you

Start the dashboard once:

```bash
.venv/bin/python -m jobup.api        # → prints http://127.0.0.1:8765/
```

Open it, go to the **Profile** tab, and:

1. **Upload your resume** (PDF / TXT / MD). It's extracted into a structured
   profile — *only* facts present in your resume, nothing invented.
2. **Confirm / edit** your basics (name, work authorization, target locations,
   skills, summary) and your **experience** — these bullets are the *only* facts
   the tailor is allowed to use. Keep them accurate.
3. Fill the **standard application questions** (answered once, reused everywhere):
   work authorization, visa sponsorship, willingness to relocate, onsite/hybrid,
   earliest start date, degree, graduation date, salary expectation. Blanks are
   flagged per-application so you know what's missing. ("Why this company" is
   generated fresh per job when you approve it.)

Your profile and answers are saved to `config/profile.yaml` and
`config/answer_profile.yaml` — both **git-ignored** (they're your PII). Power
users can edit those YAML files directly instead of the dashboard.

## 3. Run the pipeline

**Automatically (recommended):** install the background agents once —

```bash
.venv/bin/python -m jobup.schedule install
```

This installs two macOS **launchd** agents:
- `com.jobup.prepare` — runs discovery + tailoring **every 20 min** (interval =
  `poll_interval_min` in `config.yaml`), catching up on wake.
- `com.jobup.dashboard` — keeps the dashboard running at
  **http://127.0.0.1:8765/**, restarting it if it dies.

```bash
.venv/bin/python -m jobup.schedule status      # are they running?
.venv/bin/python -m jobup.schedule uninstall   # stop / pause everything
```

Logs stream to `data/logs/prepare.*.log` and `data/logs/dashboard.*.log`.
Agents run while you're logged in; runs missed during sleep catch up on wake.

**Manually / on demand:** click **Run pipeline ▶** in the dashboard, or:

```bash
.venv/bin/python -m jobup.run --dry-run                 # discovery only (free, no LLM)
.venv/bin/python -m jobup.prepare --max-scan 40         # discover → tailor → package
```

`--max-scan` caps the number of Sonnet *triage* calls per run (a cost ceiling).
Already-prepared postings are skipped, so reruns only spend tokens on genuinely
new jobs. Each run prints its exact LLM cost.

## 4. Review & apply (the dashboard)

Open **http://127.0.0.1:8765/** (the token is embedded automatically; it lives in
`data/.jobup_token`).

**Queue tab:**
- Applications are sorted **best-fit first**; jobs scoring ≥80% get a **★ high fit**
  badge. Switch to newest-first, filter by company / fit / status / posted date, or
  search.
- **⚠ Needs attention** shows only applications whose resume *failed* the factual
  check after auto-revision — with the exact unsupported claims called out, so you
  can fix your experience library or skip them. These never masquerade as clean.
- Bulk-approve/skip with checkboxes; keyboard shortcuts `j`/`k` (move), `a`
  (approve), `s` (skip), `o` (open job).

**On a job you like → Approve:**
- It advances to `approved` and generates, on the spot, a grounded + fact-checked
  **cover letter** and a per-job **"why this company"** answer.
- Click **Download apply package ↓** to get a zip containing:
  `resume.pdf`, `resume.md`, `cover_letter.md`, `answers.md`, and `checklist.md`
  (a per-job summary: apply URL, fit, what to submit, and every answer — with
  blanks flagged `← NEEDS YOUR ANSWER`).
- Click the apply link, apply on the company's site yourself, then **I applied ✔**
  to mark it `applied`.

**Assisted apply (optional):** installs a local browser that opens the real
application form and autofills it + attaches your resume PDF, then **stops so you
review and submit.** It never submits.

```bash
pip install playwright && playwright install chromium
# then use the "Assisted apply" button, or preview values with:
.venv/bin/python -m jobup.apply <app_id> --dry-run
```

## 5. Configure sources & filters

Everything tunable lives in [`config/config.yaml`](config/config.yaml):

- `target.roles` — a job title must contain one of these words (free pre-filter).
- `target.exclude` — title words that auto-reject (senior/staff/intern/etc.).
- `target.levels` / `target.locations` — new-grad levels and where you'll work.
- `min_score` — the Sonnet triage fit threshold (0–1).
- `sources.*` — which company boards to pull: `greenhouse_tokens`, `lever_tokens`,
  `ashby_tokens`, `workday_sites`, `simplify_repos` (curated GitHub new-grad lists).
- `notify.*` — real-time alerts (console by default; Gmail SMTP when configured).
- `answers.standard` — documents the canonical application-question schema.

## 6. Import jobs from anywhere (CSV / JSON)

Sourced a list yourself (a spreadsheet, an n8n flow, a LinkedIn export)? Feed it
in and it gets tailored + packaged like any other posting — JobUp never scrapes,
it just processes what you give it. Use the **Import jobs ↥** button, or:

```bash
.venv/bin/python -m jobup.import_jobs jobs.csv
```

Accepted columns (aliases handled): `title` + `apply_url` (required), `company`,
`location`, `description`, `posted_at`.

## 7. Cost control

- Discovery (`jobup.run`) is free — no LLM.
- Tailoring spends tokens only on **new** postings; reruns are cheap.
- `--max-scan` bounds triage calls; each run prints its cost.
- To pause spending entirely: `jobup.schedule uninstall`.

## Safety & privacy

- The dashboard binds `127.0.0.1` only and requires a token on every API call.
  **Don't expose it to the internet** without adding real auth/TLS.
- PII (`.env`, `config/profile.yaml`, `config/answer_profile.yaml`, `data/`,
  `resumes/`) is git-ignored and never leaves your machine.

## Architecture & tests

Design docs: [`docs/PRD.md`](docs/PRD.md), [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md),
[`docs/LLD.md`](docs/LLD.md), [`docs/SECURITY.md`](docs/SECURITY.md). Working notes
for contributors: [`CLAUDE.md`](CLAUDE.md).

```bash
.venv/bin/python -m pytest tests/ -q     # offline, no API key (the LLM is faked)
```

**Note on Indeed:** not wired as a connector — Indeed has no free public API and
its MCP tool only exists inside a Claude agent runtime. Bring Indeed jobs in via
the CSV/JSON import instead.
