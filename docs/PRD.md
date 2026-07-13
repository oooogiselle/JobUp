# JobUp — Product Requirements Document (PRD)

**Owner:** Giselle
**Status:** Draft v1
**Last updated:** 2026-07-12

---

## 1. Problem & Motivation

Applying to new-grad roles is a high-volume, repetitive grind. Good jobs are
scattered across ATS boards, aggregators, and community lists; each requires a
slightly different resume emphasis and the same tedious form answers. Manually
finding, tailoring, and applying is slow, so candidates either apply to too few
roles or send a generic resume to many. Both hurt interview rates.

**JobUp** is a personal, human-in-the-loop job-application agent. Every day it
discovers relevant new-grad postings, lightly tailors the user's resume to each,
pre-fills the application answers, and packages everything for one-click human
approval. The human always presses "apply" — the agent never submits on its own.

## 2. Goals

- **G1** — Discover *every relevant* new-grad posting daily across trusted sources.
- **G2** — For each, produce a lightly-tailored resume that improves keyword/skill
  alignment **without fabricating anything**.
- **G3** — Flag (via notification) any posting where a heavier rewrite would
  materially improve fit, so the user can opt in.
- **G4** — Pre-fill common application questions from a reusable answer profile.
- **G5** — Present a review-and-approve queue; the user submits manually.
- **G6** — Keep the user's data local and private; be cheap to run.
- **G7** — Stay within every source's Terms of Service.
- **G8 (Timeliness)** — Surface a relevant posting **within minutes** of it appearing,
  not once a day. New-grad roles close fast; early applicants win. The system polls
  frequently and pushes a **per-job real-time alert**, with a daily email as summary.

## 3. Non-Goals (v1)

- **NG1** — No automatic submission of applications. Human presses apply. (Hard rule.)
- **NG2** — No scraping of LinkedIn or Handshake (ToS/ban risk). Manual only.
- **NG3** — No solving of CAPTCHAs, no evading bot detection, no fake accounts.
- **NG4** — No multi-user / SaaS. Single-user, personal tool.
- **NG5** — No interview scheduling, salary negotiation, or offer management.
- **NG6** — No fabrication of skills, experience, or credentials, ever.

## 4. Users & Personas

Single user: **Giselle**, a new-grad candidate.
- Wants breadth (see everything relevant) without spending hours/day.
- Trusts the agent to *prepare* but wants final control over what is sent.
- Values privacy — resume and history stay on her machine.

## 5. User Stories

- **US1** — As the user, each morning I get a digest of new relevant postings with
  a tailored resume and pre-filled answers already attached, so I can review and
  apply in minutes.
- **US2** — As the user, I can open a dashboard, see each job's match score and what
  changed in the resume, edit if needed, then mark it "applied."
- **US3** — As the user, when a role needs a heavier resume rewrite to be
  competitive, I get a notification and can approve the deeper rewrite.
- **US4** — As the user, I never worry the agent applied to something without me.
- **US5** — As the user, I can add/remove target companies and tune what counts as
  "relevant" (roles, locations, keywords, must-haves like visa sponsorship).
- **US6** — As the user, I can trust that a tailored resume never claims anything
  untrue about me.

## 6. Functional Requirements

### 6.1 Discovery
- **FR1** — Poll postings on a **frequent interval** (default every 20 min,
  configurable) from: Greenhouse, Lever, Ashby ATS public APIs; Indeed MCP; Simplify
  GitHub new-grad repos; monitored company boards (via ATS token). (Simplify/GitHub
  can additionally use webhooks/commit polling for near-instant detection.)
- **FR2** — Company monitoring is a user-maintained list of `{company → ATS token}`.
- **FR3** — Normalize all sources into one `JobPosting` schema.
- **FR4** — Deduplicate across sources (canonical URL + company+title+location).
- **FR5** — Persist every seen posting so a job is surfaced to the user at most once.

### 6.2 Relevance & Matching
- **FR6** — Filter to new-grad-eligible roles (level heuristics + LLM check).
- **FR7** — Score each posting against the user profile (skills, location, work-auth,
  must-haves). Only postings above a threshold proceed.
- **FR8** — Exclude postings that violate hard filters (e.g. requires clearance the
  user lacks, requires senior experience, wrong location, no sponsorship if needed).

### 6.3 Resume Tailoring
- **FR9** — Default to **light alignment**: reorder/emphasize existing bullets,
  align terminology to the JD's keywords, tune the summary — no new claims.
- **FR10** — Detect when light alignment is insufficient and **notify** the user with
  a recommendation to approve a heavier (still truthful) rewrite.
- **FR11** — Enforce a **factual-integrity guard**: every claim in the tailored resume
  must trace to the user's master resume / experience library. No fabrication.
- **FR12** — Render the tailored resume to ATS-friendly PDF (and keep the source).

### 6.3b Contact & Team Enrichment
- **FR12a** — For each relevant posting, **extract the hiring team / org** it targets
  (e.g. "Payments Infra", "Growth ML") from the JD and ATS metadata.
- **FR12b** — **Identify the recruiter / hiring contact** when the source exposes it
  (many Greenhouse/Lever/Ashby postings and Indeed listings include a recruiter name,
  hiring-manager, or contact email in metadata). Surface name, role, and any provided
  contact channel in the application bundle.
- **FR12c** — When no contact is exposed, record `team` only and mark `recruiter:
  unknown` — **never fabricate a name or email**, and never scrape private profiles.
  (Optional, user-approved: suggest a search query for the user to find the contact
  themselves — the agent does not auto-harvest personal data.)
- **FR12d** — Enrichment powers optional warm-outreach drafting (a short, honest
  note) that, like everything else, the **user** reviews and sends manually.

### 6.4 Application Preparation
- **FR13** — Maintain a reusable **answer profile** (work auth, sponsorship, start
  date, location prefs, demographic EEO answers, links, etc.).
- **FR14** — Pre-fill known application questions from the answer profile; leave
  unknown/edge questions blank and flag them for the user.

### 6.5 Approval & Submission
- **FR15** — Every prepared application enters an **approval queue** with: job info,
  match score, tailored resume + diff vs. master, pre-filled answers, and the apply URL.
- **FR16** — Send a **per-job real-time alert** (push / email) the moment a relevant,
  prepared application enters the queue — so the user can apply while the posting is
  fresh. A **daily email digest** additionally summarizes the day's queue. Alerts are
  rate-limited/batched to avoid spam during bursts.
- **FR17** — Provide a **local React dashboard** to review, edit, approve, and mark
  as applied. Submission itself is manual (user clicks through on the job site).
- **FR18** — Track application status: `discovered → prepared → approved → applied →
  (interview / rejected / no-response)`.

### 6.6 Configuration & Control
- **FR19** — User-editable config: target roles, locations, keywords, hard filters,
  company watchlist, notification preferences, schedule time.
- **FR20** — Full audit log of every action the agent took, per run.

## 7. Non-Functional Requirements

- **NFR1 (Privacy)** — All PII (resume, answers, history) stored locally in SQLite;
  no third-party storage. LLM calls send only the minimum needed per task.
- **NFR2 (Security)** — Secrets in OS keychain / `.env` (never committed). See
  `SECURITY.md` (to follow) — includes prompt-injection defense on untrusted JDs.
- **NFR3 (ToS compliance)** — Only use official/public APIs and permitted sources;
  honor robots.txt and rate limits; no auto-submit.
- **NFR4 (Cost)** — Target < a few dollars/day of LLM spend at expected volume;
  cache and batch where possible.
- **NFR5 (Reliability)** — A failing source must not fail the whole run; per-source
  isolation, retries with backoff, idempotent runs.
- **NFR6 (Portability)** — Stateless runner; all state in SQLite so it can move from
  laptop (launchd) to a cloud VM with a config change.
- **NFR7 (Performance)** — Each polling cycle completes in a couple of minutes.
- **NFR7b (Latency)** — End-to-end time from a posting going live → user alerted is
  minutes, not hours. Cloud (always-on) is required to hit this when the laptop is
  closed; local-first hits it only while the machine is awake. See D5/§6.
- **NFR8 (Auditability)** — Every tailored resume and answer set is reproducible and
  logged with the inputs that produced it.

## 8. Key Product Decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | Human presses apply; no auto-submit | Trust, ToS, avoids irreversible mistakes |
| D2 | Sources = ATS APIs + Indeed MCP + Simplify repos + company tokens | Clean, structured, ToS-friendly |
| D3 | LinkedIn/Handshake excluded from automation | Scraping violates ToS, risks bans |
| D4 | Light tailoring default, notify for heavy | Speed + honesty; user opts into effort |
| D5 | Local-first now (frequent-poll via launchd), **cloud-ready by design**; migrate to always-on cloud for true real-time | Privacy/cost now; timeliness (G8) later without a rewrite |
| D6 | Factual-integrity guard is non-negotiable | Reputational + ethical risk of fabrication |
| D7 | Extract recruiter + hiring team/org per posting when available | Enables warm outreach; higher response rate |

## 9. Success Metrics

- **M1** — % of *relevant* daily postings actually surfaced (coverage).
- **M2** — Time from posting discovered → user applied (should drop to minutes).
- **M3** — Interview-callback rate vs. pre-JobUp baseline.
- **M4** — Precision of relevance filter (user "not relevant" rate should be low).
- **M5** — Zero fabrication incidents (hard gate; any incident is a Sev-1).
- **M6** — Zero unauthorized/auto submissions (hard gate).

## 10. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Source ToS changes / API removal | Per-source connector isolation; easy to disable |
| Prompt injection via malicious JD text | Treat JD as untrusted data; guardrails (see LLD/Security) |
| Resume fabrication by the LLM | Factual-integrity verifier + master-resume grounding |
| Duplicate/spam postings | Cross-source dedup + seen-store |
| Laptop off ⇒ missed runs | launchd runs-at-next-wake; optional cloud move |
| Over-applying to irrelevant roles | Relevance threshold + hard filters + human gate |
| Cost blowup | Batch/cache LLM calls; cheap model for triage, strong model for tailoring |

## 11. Assumptions

- User has a well-structured **master resume / experience library** as the source of truth.
- User will maintain the company watchlist and answer profile.
- The Indeed MCP tool is available in the runtime; if not, that connector is disabled.
- Volume is on the order of tens of relevant postings/day, not thousands.

## 12. Resolved Decisions & Open Questions

Resolved:
- **R1** — Email via **Gmail MCP** (digest + email alerts).
- **R2** — Real-time push: **email in Phase 1**; add **OS push or Telegram in Phase 2**.
- **R3** — Models: **Opus (`claude-opus-4-8`) for resume tailoring**; **Sonnet
  (`claude-sonnet-5`) for triage/enrichment/factual-verification**.

Open:
- **OQ1** — Track outcomes (interview/reject) manually in the dashboard, or parse
  reply emails via Gmail MCP later? (Deferred to post-v1.)
