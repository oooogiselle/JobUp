# JobUp — Build Prompt: "Make the full loop flow end-to-end"

## Mission
Refactor and complete the existing JobUp codebase so the **entire loop works start to
finish**: dashboard onboarding → discovery → match → tailor (with grounding) → package →
human review → export an apply-ready package → mark applied. You may restructure modules
and interfaces where they block a clean flow, but reuse the existing logic (`run.py`,
`prepare.py`, `pipeline/`, `db.py`, `api/`, `sources/`). This is **refactor + complete**,
not a greenfield rewrite.

## Non-negotiable invariants (enforced in code, not prompts — do not weaken)
1. **The agent never submits an application.** `applied` is reachable only from `approved`,
   only via a human-initiated API call. No code path submits externally.
2. **Never fabricates.** Every tailored resume AND cover letter passes `verify_factual`
   against the user's experience library before it can be presented as clean.
3. **No scraping.** Sources stay: official ATS APIs, curated GitHub lists, user CSV/JSON
   imports. No LinkedIn/Indeed scraping.

## The golden path that must work (acceptance)
A first-time user can, from the dashboard:
1. Paste/upload their resume → it's auto-extracted into a profile they confirm/edit, and
   answer a short one-time set of standard questions.
2. Trigger a run → discovery pulls fresh postings, the pipeline matches + tailors them.
3. See a review queue sorted by fit, with **high-signal jobs highlighted**, and a separate
   **"Needs attention"** bucket for resumes that failed the factual check (showing the
   unsupported claims).
4. Approve a job → its cover letter + per-job answers are generated on the spot → download
   an apply-ready package (resume PDF + cover letter + filled answers + checklist).
5. Click the apply link, apply themselves, and mark the application `applied`.

## Work items

### A. Onboarding — dashboard-driven (currently YAML-only; this is a top gap)
- Dashboard flow: upload/paste resume → `resume_extract.py` extracts → user confirms/edits
  profile fields → answers the one-time standard question set → saved.
- YAML (`profile.yaml`, `answer_profile.yaml`) becomes an **export/backup**, not the entry
  point. Keep loaders working for power users, but the dashboard is the primary path.
- Persist profile + answers via the `Store` (or existing config files written by the API);
  validate required fields before a run can proceed.
- Keep `resume_extract.py`'s tolerant JSON parse — do NOT switch it to strict
  `messages.parse` (the API rejects the nested schema with "Schema is too complex").

### B. Discovery — keep single-pass + parallel (do NOT add multi-agent)
- Leave the `asyncio.gather` per-connector isolation model as-is.
- Focus on coverage + freshness: make Simplify/Workday parsing robust, keep newest-first
  ordering, keep skipping already-prepared jobs so reruns only spend tokens on new postings.
- No agent swarm here — discovery is I/O + deterministic rules.

### C. Tailoring — add a bounded self-correction loop (the one place agentic behavior pays off)
- Current flow: draft (Opus) → verify (Sonnet) → fit (Sonnet), where a failed verify is a
  dead end. Change to:
  ```
  draft → verify → [if unsupported claims] → revise (feed claims back as feedback) → re-verify
  ```
- Cap at **1–2 revision iterations**. If still unsupported after the cap, mark
  `factual_check_passed = False` and route to the "Needs attention" bucket (do NOT present
  as clean). This is a bounded critic+retry, **not** a planner/researcher/writer swarm —
  keep it deterministic.

### D. Cover letter + per-job "why this company" — NEW module, on-approve/on-demand
- Does not exist today. Add a `cover_letter` generator (Opus `generate`) that runs the same
  `draft → verify → revise` grounding loop as tailoring.
- Generate **only when the user approves a job** (or clicks "generate") — do not spend
  tokens on cover letters for jobs that get skipped.
- The per-job `why_this_company` answer is generated at the same time.

### E. Pre-filled answers — canonical config-defined schema (currently thin)
- Define a fixed standard question set (NOT a plugin) in config, e.g.: work authorization,
  needs sponsorship, relocation/onsite willingness, earliest start date, degree + grad date,
  salary expectation, plus the generated per-job `why_this_company`.
- `prefill_answers` maps `answer_profile` → this schema; blanks flagged as `unanswered`.
- Defer per-ATS answer mapping to v2.

### F. Apply package — assemble + expose for download (currently only raw markdown on disk)
- On approve, assemble a per-job package: **resume PDF** (via `render/resume_pdf.py`),
  **cover letter**, **filled answers**, **apply checklist** (short per-job summary of what to
  submit + the apply URL).
- Expose it **downloadable from the dashboard** — each application card has the artifacts
  right there. Wire `resume_pdf.py` into this path (it's currently unused by the flow).

### G. Dashboard + state machine
- Review queue sorted by fit score, high-tier jobs badged/highlighted; "Needs attention"
  bucket for failed-check apps.
- Approve → generate cover letter + answers + package → download → mark `applied`
  (human-initiated). State machine unchanged; the agent never advances to `applied`.
- Keep the single-file React app, 127.0.0.1 bind, `X-JobUp-Token` on every `/api/*`,
  `no-store` responses.

## Volume / cadence
- No tight `--limit`. Process all fresh, eligible, not-yet-prepared postings each run,
  bounded only by `--max-scan` (token safety cap on triage calls). Surface high-fit jobs.

## Verification — LIVE end-to-end (definition of done)
- All offline `FakeLLM` tests pass (add coverage for the new revise loop, cover letter,
  answer schema, package assembly).
- Then run the **real loop** against real sources + Anthropic API with the user's real
  profile/resume/key, and show real prepared applications in the dashboard, at least one
  approved → downloaded package. A wired-but-unrun flow is NOT done.

## Explicit non-goals
- Multi-agent discovery; full multi-agent/swarm tailoring.
- Auto-submitting applications; any scraping source.
- Plugin architecture for the answer schema.
