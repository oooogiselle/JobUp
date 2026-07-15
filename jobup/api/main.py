"""Approval API (LLD §8, C11). Local-only FastAPI service backing the dashboard.

Security (SECURITY.md T3/T9):
  - binds 127.0.0.1 only (see __main__.py);
  - every /api/* call requires the X-JobUp-Token header, even locally;
  - NO endpoint performs an external submission — the human applies on the job
    site and then marks the application 'applied'. 'applied' is reachable only
    from 'approved' via a human-initiated call (state machine in db.py)."""

from __future__ import annotations

import secrets
from pathlib import Path

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from pydantic import BaseModel

from ..db import Store
from ..models import UserProfile
from ..profile import load_answers, load_profile
from ..render.resume_pdf import render_to_bytes
from ..resume_extract import ingest_resume, save_answers, save_profile
from .dashboard import DASHBOARD_HTML

_TOKEN_FILE = "data/.jobup_token"


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _load_or_create_token() -> str:
    p = Path(_TOKEN_FILE)
    if p.exists():
        return p.read_text().strip()
    p.parent.mkdir(parents=True, exist_ok=True)
    tok = secrets.token_urlsafe(24)
    p.write_text(tok)
    p.chmod(0o600)
    return tok


class AnswersPatch(BaseModel):
    answers: dict


class BulkAction(BaseModel):
    action: str          # "approve" | "skip"
    ids: list[str]


def create_app(store_path: str = "data/jobup.sqlite3", token: str | None = None,
               llm=None) -> FastAPI:
    app = FastAPI(title="JobUp Approval")
    app.state.token = token or _load_or_create_token()
    app.state.store_path = store_path
    app.state.llm = llm   # injectable for tests; else built lazily from the API key

    def get_llm():
        if app.state.llm is not None:
            return app.state.llm
        import os
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise HTTPException(400, "ANTHROPIC_API_KEY not set — needed to extract a resume")
        from ..llm.client import AnthropicLLM
        app.state.llm = AnthropicLLM()
        return app.state.llm

    @app.middleware("http")
    async def no_store(request: Request, call_next):
        resp = await call_next(request)
        if request.url.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    def get_store():
        s = Store(app.state.store_path)
        try:
            yield s
        finally:
            s.close()

    def auth(request: Request, x_jobup_token: str = Header(default="")):
        if not secrets.compare_digest(x_jobup_token, request.app.state.token):
            raise HTTPException(status_code=401, detail="missing/invalid X-JobUp-Token")

    protected = [Depends(auth)]

    @app.get("/", response_class=HTMLResponse)
    def dashboard() -> str:
        # The token is embedded so the same-origin localhost page can call /api.
        return DASHBOARD_HTML.replace("__TOKEN__", app.state.token)

    @app.get("/api/applications", dependencies=protected)
    def list_apps(status: str | None = None, company: str | None = None,
                  min_score: float | None = None, posted_since: str | None = None,
                  q: str | None = None, needs_attention: bool | None = None,
                  order: str = "recent", store: Store = Depends(get_store)):
        return store.list_applications(status=status, company=company,
                                       min_score=min_score, posted_since=posted_since,
                                       q=q, needs_attention=needs_attention, order=order)

    @app.get("/api/companies", dependencies=protected)
    def companies(store: Store = Depends(get_store)):
        return store.companies()

    @app.get("/api/stats", dependencies=protected)
    def stats(store: Store = Depends(get_store)):
        from collections import Counter
        from datetime import date
        rows = store.list_applications()
        scores = [r["score"] for r in rows if r["score"] is not None]
        today = date.today().isoformat()
        return {
            "total": len(rows),
            "by_status": dict(Counter(r["status"] for r in rows)),
            "avg_score": round(sum(scores) / len(scores), 2) if scores else None,
            "new_today": sum(1 for r in rows if (r["updated_at"] or "").startswith(today)),
        }

    @app.get("/api/run", dependencies=protected)
    def run_status():
        return getattr(app.state, "run_status", {"running": False, "phase": "idle"})

    @app.post("/api/run", dependencies=protected)
    def trigger_run(body: dict | None = None):
        """Trigger a full discovery -> match -> tailor -> package run in the
        background (BUILD golden path #2). Bounded by max_scan (triage cost cap);
        already-prepared postings are skipped so reruns only spend tokens on new
        jobs. Never submits anything."""
        import threading

        cur = getattr(app.state, "run_status", None)
        if cur and cur.get("running"):
            raise HTTPException(409, "a run is already in progress")
        get_llm()  # fail fast if ANTHROPIC_API_KEY is missing
        from ..profile import load_profile
        profile = load_profile()
        if not profile.name or not profile.experience:
            raise HTTPException(400, "profile is incomplete — add your name and at "
                                     "least one experience entry before running")
        max_scan = int((body or {}).get("max_scan", 40))
        app.state.run_status = {"running": True, "phase": "discovering",
                                "started_at": _now_iso(), "summary": None, "error": None}

        def _work():
            import asyncio
            from ..config import load_settings
            from ..profile import load_answers, load_profile
            from ..run import discover
            from .. import prepare as prepare_mod
            try:
                settings = load_settings()
                asyncio.run(discover(settings, dry_run=False))
                app.state.run_status["phase"] = "tailoring"
                store = Store(app.state.store_path)
                try:
                    apps = asyncio.run(prepare_mod.prepare(
                        settings, load_profile(), load_answers(), get_llm(),
                        limit=max_scan, max_scan=max_scan, store=store))
                finally:
                    store.close()
                app.state.run_status = {"running": False, "phase": "done",
                                        "finished_at": _now_iso(), "error": None,
                                        "summary": {"prepared": len(apps)}}
            except Exception as e:  # noqa: BLE001 - surface to the dashboard
                app.state.run_status = {"running": False, "phase": "error",
                                        "finished_at": _now_iso(),
                                        "error": f"{type(e).__name__}: {e}", "summary": None}

        threading.Thread(target=_work, daemon=True).start()
        return {"started": True}

    @app.post("/api/import", dependencies=protected)
    async def import_jobs(file: UploadFile = File(...), store: Store = Depends(get_store)):
        """Import jobs from a CSV/JSON file and tailor them through the pipeline.
        You source them however you like (N8N, a LinkedIn export, a spreadsheet) —
        JobUp never scrapes; it just processes what you feed it."""
        from ..import_jobs import import_and_prepare, parse_import
        data = await file.read()
        if not data:
            raise HTTPException(400, "empty file")
        if len(data) > 10 * 1024 * 1024:
            raise HTTPException(413, "file too large (max 10 MB)")
        try:
            jobs = parse_import(data, file.filename or "jobs.csv")
        except Exception as e:
            raise HTTPException(400, f"could not parse file: {e}")
        apps = import_and_prepare(jobs, load_profile(), load_answers(), get_llm(), store)
        return {"parsed": len(jobs), "imported": len(apps)}

    @app.post("/api/applications/bulk-action", dependencies=protected)
    def bulk_action(b: BulkAction, store: Store = Depends(get_store)):
        target = {"approve": "approved", "skip": "skipped"}.get(b.action)
        if not target:
            raise HTTPException(400, "action must be 'approve' or 'skip'")
        results: dict[str, str] = {}
        for app_id in b.ids:
            try:
                store.update_status(app_id, target)
                results[app_id] = "ok"
            except (KeyError, ValueError) as e:
                results[app_id] = str(e)
        return results

    @app.get("/api/applications/{app_id}", dependencies=protected)
    def get_app(app_id: str, store: Store = Depends(get_store)):
        bundle = store.get_application_bundle(app_id)
        if bundle is None:
            raise HTTPException(404, "application not found")
        return bundle

    @app.get("/api/applications/{app_id}/resume.md", dependencies=protected,
             response_class=PlainTextResponse)
    def get_resume(app_id: str, store: Store = Depends(get_store)) -> str:
        bundle = store.get_application_bundle(app_id)
        if bundle is None:
            raise HTTPException(404, "application not found")
        return bundle.get("tailored_resume", {}).get("resume_markdown", "")

    @app.get("/api/applications/{app_id}/resume.pdf", dependencies=protected)
    def get_resume_pdf(app_id: str, store: Store = Depends(get_store)):
        bundle = store.get_application_bundle(app_id)
        if bundle is None:
            raise HTTPException(404, "application not found")
        md = bundle.get("tailored_resume", {}).get("resume_markdown", "")
        pdf = render_to_bytes(md)
        return Response(content=pdf, media_type="application/pdf",
                        headers={"Content-Disposition": "inline; filename=resume.pdf"})

    def _transition(app_id: str, new_status: str, store: Store):
        try:
            return store.update_status(app_id, new_status)
        except KeyError:
            raise HTTPException(404, "application not found")
        except ValueError as e:
            raise HTTPException(409, str(e))

    @app.post("/api/applications/{app_id}/approve", dependencies=protected)
    def approve(app_id: str, store: Store = Depends(get_store)):
        return _transition(app_id, "approved", store)

    @app.post("/api/applications/{app_id}/mark-applied", dependencies=protected)
    def mark_applied(app_id: str, store: Store = Depends(get_store)):
        # Human-only: confirms THEY applied on the job site. The agent cannot
        # reach this state from the pipeline (only 'approved' -> 'applied').
        return _transition(app_id, "applied", store)

    @app.post("/api/applications/{app_id}/skip", dependencies=protected)
    def skip(app_id: str, store: Store = Depends(get_store)):
        return _transition(app_id, "skipped", store)

    @app.patch("/api/applications/{app_id}", dependencies=protected)
    def patch_answers(app_id: str, patch: AnswersPatch, store: Store = Depends(get_store)):
        try:
            return store.update_answers(app_id, patch.answers)
        except KeyError:
            raise HTTPException(404, "application not found")

    # --- profile ----------------------------------------------------------
    @app.get("/api/profile", dependencies=protected)
    def get_profile():
        return {"profile": load_profile().model_dump(), "answers": load_answers()}

    @app.put("/api/profile", dependencies=protected)
    def put_profile(profile: dict):
        save_profile(UserProfile(**profile))
        return {"profile": load_profile().model_dump()}

    @app.put("/api/answers-profile", dependencies=protected)
    def put_answers(answers: dict):
        save_answers(answers)
        return {"answers": load_answers()}

    @app.post("/api/profile/upload", dependencies=protected)
    async def upload_resume(file: UploadFile = File(...), store: Store = Depends(get_store)):
        from ..render.master_resume import profile_to_markdown
        data = await file.read()
        if not data:
            raise HTTPException(400, "empty file")
        if len(data) > 10 * 1024 * 1024:                 # 10 MB cap (DoS guard)
            raise HTTPException(413, "file too large (max 10 MB)")
        profile, answers = ingest_resume(data, file.filename or "resume.pdf", get_llm())
        # Seed the resume library with a clean master resume from the extraction.
        store.save_resume(f"Master resume ({file.filename or 'upload'})",
                          profile_to_markdown(profile), source="uploaded")
        return {"profile": profile.model_dump(), "answers": answers}

    # --- resume library ---------------------------------------------------
    @app.get("/api/resumes", dependencies=protected)
    def list_resumes(store: Store = Depends(get_store)):
        return store.list_resumes()

    @app.post("/api/resumes", dependencies=protected)
    def save_resume(body: dict, store: Store = Depends(get_store)):
        """Save a resume. {from_profile: true} renders the current profile into a
        clean bulleted master resume; otherwise {name, markdown}."""
        from ..render.master_resume import profile_to_markdown
        if body.get("from_profile"):
            p = load_profile()
            name = body.get("name") or f"Master resume — {p.name or 'profile'}"
            rid = store.save_resume(name, profile_to_markdown(p), source="profile")
        else:
            if not body.get("markdown"):
                raise HTTPException(400, "markdown required")
            rid = store.save_resume(body.get("name") or "Resume",
                                    body["markdown"], source="manual")
        return {"id": rid, "resumes": store.list_resumes()}

    @app.get("/api/resumes/{rid}", dependencies=protected)
    def get_resume(rid: str, store: Store = Depends(get_store)):
        r = store.get_resume(rid)
        if r is None:
            raise HTTPException(404, "resume not found")
        return r

    @app.get("/api/resumes/{rid}/pdf", dependencies=protected)
    def resume_lib_pdf(rid: str, store: Store = Depends(get_store)):
        r = store.get_resume(rid)
        if r is None:
            raise HTTPException(404, "resume not found")
        return Response(content=render_to_bytes(r["markdown"]), media_type="application/pdf",
                        headers={"Content-Disposition": "inline; filename=resume.pdf"})

    @app.post("/api/resumes/{rid}/default", dependencies=protected)
    def set_default_resume(rid: str, store: Store = Depends(get_store)):
        if store.get_resume(rid) is None:
            raise HTTPException(404, "resume not found")
        store.set_default_resume(rid)
        return {"resumes": store.list_resumes()}

    @app.delete("/api/resumes/{rid}", dependencies=protected)
    def del_resume(rid: str, store: Store = Depends(get_store)):
        store.delete_resume(rid)
        return {"resumes": store.list_resumes()}

    def _generate_artifacts(bundle: dict, store: Store) -> dict:
        """Generate the grounded cover letter + per-job 'why this company' answer
        and persist them. Shared by the on-demand button and on-approve finalize."""
        from ..pipeline.cover_letter import (
            generate_cover_letter,
            generate_why_this_company,
        )
        profile = load_profile()
        company, title = bundle.get("company", ""), bundle.get("title", "")
        jd = bundle.get("description", "")
        llm = get_llm()
        letter, lcheck = generate_cover_letter(company, title, jd, profile, llm)
        why, wcheck = generate_why_this_company(company, title, jd, profile, llm)
        return store.finalize_generation(bundle["id"], letter, lcheck.passed,
                                         why, wcheck.passed)

    @app.post("/api/applications/{app_id}/cover-letter", dependencies=protected)
    def cover_letter(app_id: str, store: Store = Depends(get_store)):
        bundle = store.get_application_bundle(app_id)
        if bundle is None:
            raise HTTPException(404, "application not found")
        return _generate_artifacts(bundle, store)

    @app.post("/api/applications/{app_id}/finalize", dependencies=protected)
    def finalize(app_id: str, store: Store = Depends(get_store)):
        """On approve: advance to 'approved' (if still prepared) and generate the
        cover letter + per-job 'why this company'. Idempotent on re-approve."""
        bundle = store.get_application_bundle(app_id)
        if bundle is None:
            raise HTTPException(404, "application not found")
        if bundle.get("status") == "prepared":
            _transition(app_id, "approved", store)
        elif bundle.get("status") != "approved":
            raise HTTPException(409, f"cannot finalize from status {bundle.get('status')}")
        bundle = store.get_application_bundle(app_id)
        return _generate_artifacts(bundle, store)

    @app.get("/api/applications/{app_id}/package.zip", dependencies=protected)
    def package_zip(app_id: str, store: Store = Depends(get_store)):
        """The apply-ready package: resume PDF + resume/cover markdown + filled
        answers + apply checklist, as a single downloadable zip (BUILD §F)."""
        from ..pipeline.package import assemble_package
        bundle = store.get_application_bundle(app_id)
        if bundle is None:
            raise HTTPException(404, "application not found")
        data = assemble_package(bundle)
        slug = (bundle.get("company") or "job").lower().replace(" ", "-")[:24]
        return Response(content=data, media_type="application/zip",
                        headers={"Content-Disposition":
                                 f"attachment; filename=jobup-{slug}.zip"})

    @app.get("/api/applications/{app_id}/cover-letter.pdf", dependencies=protected)
    def cover_letter_pdf(app_id: str, store: Store = Depends(get_store)):
        bundle = store.get_application_bundle(app_id)
        if bundle is None or not bundle.get("cover_letter"):
            raise HTTPException(404, "no cover letter — generate it first")
        return Response(content=render_to_bytes(bundle["cover_letter"]),
                        media_type="application/pdf",
                        headers={"Content-Disposition": "inline; filename=cover-letter.pdf"})

    @app.post("/api/applications/{app_id}/assisted-apply", dependencies=protected)
    def assisted_apply(app_id: str, store: Store = Depends(get_store)):
        """Launch the local browser-assist: opens the apply page and autofills.
        It NEVER submits — you review and submit. Runs as a detached local process
        because it opens a GUI browser on this machine."""
        import importlib.util
        import subprocess
        import sys

        bundle = store.get_application_bundle(app_id)
        if bundle is None:
            raise HTTPException(404, "application not found")
        if importlib.util.find_spec("playwright") is None:
            raise HTTPException(400, "Playwright not installed. Run: "
                                "pip install playwright && playwright install chromium")
        subprocess.Popen([sys.executable, "-m", "jobup.apply", app_id],
                         start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"launched": True, "apply_url": bundle["apply_url"]}

    return app
