"""SQLite seen-store (LLD §2.2, §5-dedup). Single source of truth; the runner is
stateless so the DB fully defines state (portability, ARCHITECTURE §6)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import Application, JobPosting, MatchResult

_SCHEMA = """
CREATE TABLE IF NOT EXISTS job_posting (
    id            TEXT PRIMARY KEY,
    source        TEXT NOT NULL,
    source_ref    TEXT NOT NULL,
    company       TEXT NOT NULL,
    title         TEXT NOT NULL,
    location      TEXT,
    remote        INTEGER,
    description_raw   TEXT,
    description_clean TEXT,
    apply_url     TEXT NOT NULL,
    canonical_url TEXT NOT NULL,
    posted_at     TEXT,
    first_seen_at TEXT NOT NULL,
    fingerprint   TEXT NOT NULL,
    raw_json      TEXT
);
CREATE INDEX IF NOT EXISTS idx_job_fingerprint ON job_posting(fingerprint);

CREATE TABLE IF NOT EXISTS application (
    id            TEXT PRIMARY KEY,   -- = job_id (one application per posting)
    company       TEXT,
    title         TEXT,
    location      TEXT,
    status        TEXT NOT NULL,
    score         REAL,
    factual_check_passed INTEGER,
    needs_heavy_rewrite  INTEGER,
    team          TEXT,
    apply_url     TEXT,
    posted_at     TEXT,               -- when the posting went live (for date filter)
    description   TEXT,               -- sanitized JD, shown in the dashboard
    data          TEXT NOT NULL,      -- full Application JSON incl. resume markdown
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_app_status ON application(status);

CREATE TABLE IF NOT EXISTS resume (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    markdown    TEXT NOT NULL,
    source      TEXT,             -- uploaded | profile | tailored
    is_default  INTEGER DEFAULT 0,
    created_at  TEXT NOT NULL
);
"""

# Columns added after v1; ALTER-in on existing DBs (idempotent migration).
_MIGRATIONS = [
    ("application", "posted_at", "TEXT"),
    ("application", "description", "TEXT"),
    ("application", "notified_at", "TEXT"),   # real-time alert sent (idempotency)
    ("resume", "is_default", "INTEGER DEFAULT 0"),
]

# Application state machine (LLD §7). The agent only ever writes 'prepared';
# every advance from here is human-initiated via the API. 'applied' is reachable
# only from 'approved' — nothing in the pipeline can set it (SECURITY invariant #1).
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "prepared": {"approved", "skipped"},
    "approved": {"applied", "skipped"},
    "applied": {"interview", "rejected", "no_response"},
    "skipped": set(),
    "interview": set(),
    "rejected": set(),
    "no_response": set(),
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path: str | Path = "data/jobup.sqlite3"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: FastAPI runs sync endpoints across threadpool
        # threads, so one request's connection may be opened, used, and closed on
        # different threads. Each Store is used by a single request at a time (never
        # concurrently), so disabling the thread check is safe here.
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        for table, col, coltype in _MIGRATIONS:
            cols = {r["name"] for r in self.conn.execute(f"PRAGMA table_info({table})")}
            if col not in cols:
                self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {coltype}")

    # -- dedup / seen ------------------------------------------------------
    def is_seen(self, job_id: str) -> bool:
        cur = self.conn.execute("SELECT 1 FROM job_posting WHERE id = ?", (job_id,))
        return cur.fetchone() is not None

    def fingerprint_seen(self, fingerprint: str) -> bool:
        cur = self.conn.execute(
            "SELECT 1 FROM job_posting WHERE fingerprint = ?", (fingerprint,)
        )
        return cur.fetchone() is not None

    # -- writes ------------------------------------------------------------
    def insert(self, job: JobPosting) -> None:
        self.conn.execute(
            """INSERT OR IGNORE INTO job_posting
               (id, source, source_ref, company, title, location, remote,
                description_raw, description_clean, apply_url, canonical_url,
                posted_at, first_seen_at, fingerprint, raw_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                job.id, job.source.value, job.source_ref, job.company, job.title,
                job.location, None if job.remote is None else int(job.remote),
                job.description_raw, job.description_clean, job.apply_url,
                job.canonical_url,
                job.posted_at.isoformat() if job.posted_at else None,
                job.first_seen_at.isoformat(),
                job.fingerprint, json.dumps(job.raw_json),
            ),
        )
        self.conn.commit()

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM job_posting").fetchone()[0]

    # -- applications ------------------------------------------------------
    def upsert_application(self, job: JobPosting, app: Application,
                           match: MatchResult | None = None) -> None:
        r = app.tailored_resume
        team = app.enrichment.team if app.enrichment else None
        now = _now_iso()
        existing = self.get_application(app.job_id)
        created = existing["created_at"] if existing else now
        posted = job.posted_at.isoformat() if job.posted_at else None
        self.conn.execute(
            """INSERT INTO application
               (id, company, title, location, status, score,
                factual_check_passed, needs_heavy_rewrite, team, apply_url,
                posted_at, description, data, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                 company=excluded.company, title=excluded.title,
                 location=excluded.location, status=excluded.status,
                 score=excluded.score,
                 factual_check_passed=excluded.factual_check_passed,
                 needs_heavy_rewrite=excluded.needs_heavy_rewrite,
                 team=excluded.team, apply_url=excluded.apply_url,
                 posted_at=excluded.posted_at, description=excluded.description,
                 data=excluded.data, updated_at=excluded.updated_at""",
            (
                app.job_id, job.company, job.title, job.location, app.status,
                match.score if match else None,
                int(r.factual_check_passed), int(r.needs_heavy_rewrite), team,
                app.apply_url, posted, job.description_clean,
                app.model_dump_json(), created, now,
            ),
        )
        self.conn.commit()

    def list_applications(self, status: str | None = None, company: str | None = None,
                          min_score: float | None = None, posted_since: str | None = None,
                          q: str | None = None, needs_attention: bool | None = None,
                          order: str = "recent") -> list[dict]:
        """Filter by status, company (substring), min fit score, posted-on-or-after
        date (ISO), a free-text query over title/company/team, and the
        needs-attention flag (resumes that failed the factual check). `order` is
        'fit' (highest fit score first) or 'recent' (newest posting first)."""
        clauses, params = [], []
        if status:
            clauses.append("status = ?"); params.append(status)
        if company:
            clauses.append("company LIKE ?"); params.append(f"%{company}%")
        if min_score is not None:
            clauses.append("score >= ?"); params.append(min_score)
        if posted_since:
            clauses.append("posted_at >= ?"); params.append(posted_since)
        if needs_attention is not None:
            clauses.append("COALESCE(factual_check_passed,0) = ?")
            params.append(0 if needs_attention else 1)
        if q:
            clauses.append("(title LIKE ? OR company LIKE ? OR team LIKE ?)")
            params += [f"%{q}%"] * 3
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        order_sql = ("score IS NULL, score DESC, COALESCE(posted_at, updated_at) DESC"
                     if order == "fit" else "COALESCE(posted_at, updated_at) DESC")
        rows = self.conn.execute(
            f"SELECT * FROM application{where} ORDER BY {order_sql}", params).fetchall()
        return [self._app_summary(r) for r in rows]

    def companies(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT company FROM application WHERE company IS NOT NULL "
            "ORDER BY company").fetchall()
        return [r["company"] for r in rows]

    # -- notifications -----------------------------------------------------
    def unnotified_applications(self, min_score: float = 0.0) -> list[dict]:
        """Prepared applications that haven't been alerted yet and clear the
        alert threshold — the input to the real-time notifier (idempotent)."""
        rows = self.conn.execute(
            "SELECT id, company, title, location, score, apply_url, team, "
            "factual_check_passed, posted_at FROM application "
            "WHERE notified_at IS NULL AND status='prepared' AND "
            "COALESCE(score,0) >= ? ORDER BY score DESC", (min_score,)).fetchall()
        out = []
        for r in rows:
            d = dict(r); d["factual_check_passed"] = bool(r["factual_check_passed"])
            out.append(d)
        return out

    def mark_notified(self, app_ids: list[str]) -> None:
        now = _now_iso()
        self.conn.executemany(
            "UPDATE application SET notified_at=? WHERE id=?",
            [(now, i) for i in app_ids])
        self.conn.commit()

    def get_application(self, app_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM application WHERE id=?", (app_id,)).fetchone()
        return dict(row) if row else None

    def get_application_bundle(self, app_id: str) -> dict | None:
        row = self.get_application(app_id)
        if not row:
            return None
        from .ats import keyword_match
        from .jd import structure_jd
        bundle = {k: row[k] for k in
                  ("id", "company", "title", "location", "status", "score",
                   "posted_at", "description", "created_at", "updated_at")}
        bundle["description_sections"] = structure_jd(row["description"] or "")
        bundle.update(json.loads(row["data"]))   # full Application incl. resume
        resume_md = bundle.get("tailored_resume", {}).get("resume_markdown", "")
        bundle["ats"] = keyword_match(row["description"] or "", resume_md).__dict__
        return bundle

    def update_status(self, app_id: str, new_status: str) -> dict:
        """Advance status if the transition is legal (LLD §7). Raises KeyError if
        the app is missing, ValueError on an illegal transition."""
        row = self.get_application(app_id)
        if not row:
            raise KeyError(app_id)
        cur = row["status"]
        if new_status not in ALLOWED_TRANSITIONS.get(cur, set()):
            raise ValueError(f"illegal transition {cur} -> {new_status}")
        data = json.loads(row["data"])
        data["status"] = new_status
        self.conn.execute(
            "UPDATE application SET status=?, data=?, updated_at=? WHERE id=?",
            (new_status, json.dumps(data), _now_iso(), app_id))
        self.conn.commit()
        return self.get_application(app_id)

    def finalize_generation(self, app_id: str, cover_letter: str, cover_ok: bool,
                            why: str, why_ok: bool) -> dict:
        """Store the on-approve generated artifacts (cover letter + per-job
        'why this company'), and move why_this_company from unanswered -> answers."""
        row = self.get_application(app_id)
        if not row:
            raise KeyError(app_id)
        data = json.loads(row["data"])
        data["cover_letter"] = cover_letter
        data["cover_letter_ok"] = cover_ok
        data["why_this_company"] = why
        data["why_this_company_ok"] = why_ok
        if why:
            data.setdefault("answers", {})["why_this_company"] = why
            data["unanswered"] = [k for k in data.get("unanswered", [])
                                  if k != "why_this_company"]
        self.conn.execute("UPDATE application SET data=?, updated_at=? WHERE id=?",
                          (json.dumps(data), _now_iso(), app_id))
        self.conn.commit()
        return self.get_application_bundle(app_id)

    def update_answers(self, app_id: str, answers: dict) -> dict:
        row = self.get_application(app_id)
        if not row:
            raise KeyError(app_id)
        data = json.loads(row["data"])
        data["answers"] = {**data.get("answers", {}), **answers}
        data["unanswered"] = [k for k in data.get("unanswered", [])
                              if k not in answers or answers[k] in (None, "")]
        self.conn.execute(
            "UPDATE application SET data=?, updated_at=? WHERE id=?",
            (json.dumps(data), _now_iso(), app_id))
        self.conn.commit()
        return self.get_application_bundle(app_id)

    @staticmethod
    def _app_summary(r: sqlite3.Row) -> dict:
        return {
            "id": r["id"], "company": r["company"], "title": r["title"],
            "location": r["location"], "status": r["status"], "score": r["score"],
            "factual_check_passed": bool(r["factual_check_passed"]),
            "needs_heavy_rewrite": bool(r["needs_heavy_rewrite"]),
            "team": r["team"], "posted_at": r["posted_at"],
            "updated_at": r["updated_at"],
        }

    # -- resume library ----------------------------------------------------
    def save_resume(self, name: str, markdown: str, source: str = "uploaded") -> str:
        import uuid
        rid = uuid.uuid4().hex[:12]
        first = self.conn.execute("SELECT COUNT(*) FROM resume").fetchone()[0] == 0
        self.conn.execute(
            "INSERT INTO resume (id, name, markdown, source, is_default, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (rid, name, markdown, source, 1 if first else 0, _now_iso()))
        self.conn.commit()
        return rid

    def list_resumes(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, name, source, is_default, created_at, LENGTH(markdown) AS size "
            "FROM resume ORDER BY is_default DESC, created_at DESC").fetchall()
        return [{**dict(r), "is_default": bool(r["is_default"])} for r in rows]

    def get_resume(self, rid: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM resume WHERE id=?", (rid,)).fetchone()
        return dict(row) if row else None

    def set_default_resume(self, rid: str) -> None:
        self.conn.execute("UPDATE resume SET is_default = (id = ?)", (rid,))
        self.conn.commit()

    def default_resume(self) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM resume WHERE is_default = 1 LIMIT 1").fetchone()
        return dict(row) if row else None

    def delete_resume(self, rid: str) -> None:
        was_default = (self.get_resume(rid) or {}).get("is_default")
        self.conn.execute("DELETE FROM resume WHERE id=?", (rid,))
        # if we removed the default, promote the most recent remaining resume
        if was_default:
            nxt = self.conn.execute(
                "SELECT id FROM resume ORDER BY created_at DESC LIMIT 1").fetchone()
            if nxt:
                self.conn.execute("UPDATE resume SET is_default=1 WHERE id=?", (nxt["id"],))
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
