"""Packager (LLD §9, C9). Assembles a prepared Application from the tailored
resume, enrichment, and pre-filled answers, and — on approve — assembles the
downloadable apply package (resume PDF + cover letter + filled answers +
checklist). status starts at 'prepared' and the agent never advances it to
'applied' (SECURITY.md invariant #1/#3)."""

from __future__ import annotations

import io
import zipfile

from ..models import Application, Enrichment, JobPosting, TailoredResume, UserProfile
from .answers import STANDARD_QUESTIONS, prefill_answers, question_labels


def build_application(job: JobPosting, resume: TailoredResume,
                      enrichment: Enrichment | None,
                      profile_answers: dict | None = None,
                      profile: UserProfile | None = None) -> Application:
    answers, unanswered = prefill_answers(profile_answers or {}, profile)
    return Application(
        job_id=job.id,
        tailored_resume=resume,
        enrichment=enrichment,
        answers=answers,
        unanswered=unanswered,
        status="prepared",
        apply_url=job.apply_url,
    )


def build_checklist(bundle: dict) -> str:
    """A short, human-facing 'what to submit' summary for one job (BUILD §F).
    Pure over an application bundle dict so it's testable without the API."""
    r = bundle.get("tailored_resume", {}) or {}
    labels = question_labels()
    answers = bundle.get("answers", {}) or {}
    unanswered = bundle.get("unanswered", []) or []
    lines = [
        f"# Apply checklist — {bundle.get('title', '')} @ {bundle.get('company', '')}",
        "",
        f"- Apply here: {bundle.get('apply_url') or '(no URL)'}",
        f"- Location: {bundle.get('location') or '—'}",
        f"- Fit score: {_pct(bundle.get('score'))}",
        f"- Resume factual check: {'PASSED' if r.get('factual_check_passed') else 'FAILED — review before sending'}",
    ]
    if bundle.get("cover_letter"):
        ok = bundle.get("cover_letter_ok")
        lines.append(f"- Cover letter: included{'' if ok else ' (⚠ failed factual check — review)'}")
    lines += ["", "## To submit", "- [ ] Attach resume.pdf",
              "- [ ] Paste / attach the cover letter" if bundle.get("cover_letter") else None,
              "- [ ] Fill the application answers below", "", "## Answers"]
    lines = [ln for ln in lines if ln is not None]
    for q in STANDARD_QUESTIONS:
        k = q["key"]
        val = answers.get(k, "")
        if k == "why_this_company" and bundle.get("why_this_company"):
            val = bundle["why_this_company"]
        mark = "" if val else "  ← NEEDS YOUR ANSWER"
        lines.append(f"- {labels.get(k, k)}: {val}{mark}")
    # Any extra unanswered keys not in the standard set
    for k in unanswered:
        if k not in labels:
            lines.append(f"- {k}:   ← NEEDS YOUR ANSWER")
    return "\n".join(lines) + "\n"


def assemble_package(bundle: dict) -> bytes:
    """Zip the apply-ready artifacts for one job: resume PDF + resume markdown,
    cover letter (if generated), filled answers, and the checklist (BUILD §F)."""
    from ..render.resume_pdf import render_to_bytes
    r = bundle.get("tailored_resume", {}) or {}
    resume_md = r.get("resume_markdown", "") or ""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("checklist.md", build_checklist(bundle))
        if resume_md:
            z.writestr("resume.md", resume_md)
            z.writestr("resume.pdf", render_to_bytes(resume_md))
        if bundle.get("cover_letter"):
            z.writestr("cover_letter.md", bundle["cover_letter"])
        z.writestr("answers.md", _answers_md(bundle))
    return buf.getvalue()


def _answers_md(bundle: dict) -> str:
    labels = question_labels()
    answers = bundle.get("answers", {}) or {}
    out = ["# Application answers", ""]
    for q in STANDARD_QUESTIONS:
        k = q["key"]
        val = answers.get(k, "")
        if k == "why_this_company" and bundle.get("why_this_company"):
            val = bundle["why_this_company"]
        out.append(f"**{labels.get(k, k)}:** {val or '(unanswered)'}")
    return "\n\n".join(out) + "\n"


def _pct(score) -> str:
    return f"{round(score * 100)}%" if isinstance(score, (int, float)) else "—"
