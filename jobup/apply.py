"""Assisted apply (LLD approval-flow, browser-assist).

Opens the real application page in a browser and fills the fields it can match
from your saved answers, then STOPS — you review and click submit yourself. This
preserves the hard invariant: the agent never submits (SECURITY.md invariant #1).

Design notes / limits:
  - A plain URL cannot pre-fill an ATS form, so we drive the page with Playwright.
  - Field coverage is best-effort per ATS (label/name/placeholder matching).
  - We never solve CAPTCHAs or evade bot detection; if a site blocks automation
    or shows a CAPTCHA, you finish by hand (SECURITY.md T7).
  - Browser automation may violate some job sites' ToS — this is human-in-the-loop
    assistance for your own applications, and you perform the final submit.

The matching core (`match_field`, `fill_plan`) is pure and unit-tested; the
Playwright runner is thin and driven locally by the user."""

from __future__ import annotations

import argparse
from dataclasses import dataclass

# Answer-profile key -> keyword patterns to look for in a field's label/name/etc.
# Ordered most-specific first so e.g. "linkedin" wins before a generic "url".
FIELD_MATCHERS: list[tuple[str, list[str]]] = [
    ("linkedin", ["linkedin"]),
    ("github", ["github"]),
    ("portfolio", ["portfolio", "personal website", "personal site", "website", "url"]),
    ("work_authorization", ["legally authorized", "work authorization", "authorized to work",
                            "eligible to work", "authoriz"]),
    ("requires_sponsorship", ["require sponsorship", "need sponsorship", "visa sponsorship",
                              "sponsorship"]),
    ("earliest_start_date", ["start date", "available to start", "availability",
                             "when can you start"]),
    ("preferred_locations", ["preferred location", "location preference", "where are you based",
                             "current location", "location"]),
    ("gender", ["gender"]),
    ("veteran_status", ["veteran"]),
]

# Keywords that identify a resume/CV file-upload field.
_RESUME_FIELD = ("resume", "cv", "curriculum", "attach")


def is_resume_field(descriptor: str) -> bool:
    return any(k in (descriptor or "").lower() for k in _RESUME_FIELD)


@dataclass
class FillItem:
    key: str
    value: str
    descriptor: str


def match_field(descriptor: str, answers: dict) -> tuple[str, str] | None:
    """Given a field's combined descriptor (label + name + placeholder + aria,
    lowercased) return the (answer_key, value) to fill, or None. Only considers
    answer keys that have a non-empty value."""
    d = (descriptor or "").lower()
    for key, patterns in FIELD_MATCHERS:
        val = answers.get(key)
        if val in (None, ""):
            continue
        if any(p in d for p in patterns):
            return key, str(val)
    return None


def fill_plan(descriptors: list[str], answers: dict) -> list[FillItem]:
    """What we would fill for a page's fields (each descriptor = one control).
    Each answer key is used at most once (first matching field wins)."""
    plan: list[FillItem] = []
    used: set[str] = set()
    for desc in descriptors:
        m = match_field(desc, answers)
        if m and m[0] not in used:
            used.add(m[0])
            plan.append(FillItem(key=m[0], value=m[1], descriptor=desc))
    return plan


# --- Playwright runner (driven locally by the user) ------------------------

_DESCRIBE_JS = """
(el) => {
  let label = '';
  if (el.id) { const l = document.querySelector(`label[for="${el.id}"]`); if (l) label = l.innerText; }
  if (!label) { const l = el.closest('label'); if (l) label = l.innerText; }
  return [label, el.getAttribute('name')||'', el.getAttribute('placeholder')||'',
          el.getAttribute('aria-label')||''].join(' ');
}
"""


def assisted_apply(url: str, answers: dict, resume_pdf: str | None = None,
                   headless: bool = False) -> list[FillItem]:
    """Open the application page, fill matched fields, attach the resume PDF to
    the resume upload if present, and wait for the user to review + submit.
    Requires: pip install playwright && playwright install chromium.
    Never submits. Returns the fields it filled (a resume attach shows as key
    'resume')."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "Playwright is not installed. Run:\n"
            "  pip install playwright && playwright install chromium") from e

    filled: list[FillItem] = []
    with sync_playwright() as p:  # pragma: no cover - needs a real browser
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page()
        page.goto(url, wait_until="domcontentloaded")
        for el in page.query_selector_all("input, textarea, select"):
            try:
                desc = el.evaluate(_DESCRIBE_JS)
                tag = el.evaluate("e => e.tagName.toLowerCase()")
                etype = (el.evaluate("e => e.type || ''") or "").lower()
            except Exception:
                continue
            # Resume file upload: attach the rendered PDF.
            if etype == "file":
                if resume_pdf and is_resume_field(desc):
                    try:
                        el.set_input_files(resume_pdf)
                        filled.append(FillItem(key="resume", value=resume_pdf, descriptor=desc.strip()))
                    except Exception:
                        pass
                continue
            m = match_field(desc, answers)
            if not m:
                continue
            key, value = m
            try:
                if tag == "select":
                    el.select_option(label=value)
                else:
                    el.fill(value)
                filled.append(FillItem(key=key, value=value, descriptor=desc.strip()))
            except Exception:
                pass  # unfillable control (radio group, custom widget) — skip
        print(f"\nFilled {len(filled)} field(s). Review the page, then submit it "
              "yourself. Close the browser window when done.\n")
        # Hand control to the user; exit when they close the page. Never submit.
        while not page.is_closed():
            page.wait_for_timeout(500)
        browser.close()
    return filled


def main() -> None:
    from .db import Store
    from .config import load_settings
    from .env import load_env

    ap = argparse.ArgumentParser(description="JobUp assisted apply (opens & fills; you submit)")
    ap.add_argument("app_id")
    ap.add_argument("--config", default="config/config.yaml")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the answers + matchers without opening a browser")
    args = ap.parse_args()

    load_env()
    settings = load_settings(args.config)
    store = Store(settings.db_path)
    bundle = store.get_application_bundle(args.app_id)
    store.close()
    if not bundle:
        raise SystemExit(f"no application {args.app_id}")

    answers = bundle.get("answers", {})
    resume_md = bundle.get("tailored_resume", {}).get("resume_markdown", "")

    if args.dry_run:
        print(f"apply url: {bundle['apply_url']}")
        print("answers available for autofill:")
        for k, v in answers.items():
            print(f"  {k:22} = {v}")
        print("resume PDF: will be rendered and attached to the resume upload field")
        return

    # Render the tailored resume to an ATS-friendly PDF to attach.
    from .render.resume_pdf import render_markdown_pdf
    pdf_path = render_markdown_pdf(resume_md, f"resumes/{args.app_id[:12]}.pdf")

    print(f"Opening {bundle['apply_url']} and autofilling (attaching {pdf_path})…")
    filled = assisted_apply(bundle["apply_url"], answers, resume_pdf=str(pdf_path))
    print("filled:", [i.key for i in filled])


if __name__ == "__main__":
    main()
