"""ATS keyword match (raises callback rate). Deterministic, offline.

Compares the keywords a job description asks for against the resume, and reports
which are present vs missing plus a coverage score. Missing keywords are
actionable: if you genuinely have the skill, surface it in the resume so ATS
keyword filters don't screen you out. (This flags gaps — it never invents skills;
adding an unsupported keyword is still caught by the factual verifier.)"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Canonical keyword -> match patterns (word-boundary, case-insensitive). Curated
# tech/skills lexicon; extend freely.
_LEXICON: dict[str, list[str]] = {
    "python": [r"python"], "java": [r"java(?!script)"], "javascript": [r"javascript", r"\bjs\b"],
    "typescript": [r"typescript", r"\bts\b"], "go": [r"golang", r"\bgo\b"], "rust": [r"rust"],
    "c++": [r"c\+\+"], "c#": [r"c#", r"\.net"], "ruby": [r"ruby"], "scala": [r"scala"],
    "kotlin": [r"kotlin"], "swift": [r"swift"], "php": [r"\bphp\b"], "sql": [r"\bsql\b"],
    "react": [r"react"], "node.js": [r"node\.?js", r"\bnode\b"], "angular": [r"angular"],
    "vue": [r"\bvue\b"], "next.js": [r"next\.?js"], "django": [r"django"], "flask": [r"flask"],
    "fastapi": [r"fastapi"], "spring": [r"spring boot", r"\bspring\b"], "rails": [r"\brails\b"],
    "graphql": [r"graphql"], "rest api": [r"rest api", r"restful", r"\brest\b"],
    "grpc": [r"grpc"], "kubernetes": [r"kubernetes", r"\bk8s\b"], "docker": [r"docker"],
    "aws": [r"\baws\b", r"amazon web services"], "gcp": [r"\bgcp\b", r"google cloud"],
    "azure": [r"azure"], "terraform": [r"terraform"], "ci/cd": [r"ci/cd", r"\bci\b/\bcd\b"],
    "linux": [r"linux"], "git": [r"\bgit\b"], "kafka": [r"kafka"], "spark": [r"spark"],
    "hadoop": [r"hadoop"], "redis": [r"redis"], "postgres": [r"postgres", r"postgresql"],
    "mysql": [r"mysql"], "mongodb": [r"mongo(db)?"], "elasticsearch": [r"elasticsearch"],
    "machine learning": [r"machine learning", r"\bml\b"], "deep learning": [r"deep learning"],
    "pytorch": [r"pytorch"], "tensorflow": [r"tensorflow"], "nlp": [r"\bnlp\b", r"natural language"],
    "computer vision": [r"computer vision"], "data science": [r"data science"],
    "distributed systems": [r"distributed systems?"], "microservices": [r"microservices?"],
    "backend": [r"back[- ]?end"], "frontend": [r"front[- ]?end"], "full stack": [r"full[- ]?stack"],
    "api design": [r"api design"], "testing": [r"unit test", r"integration test", r"\btesting\b"],
    "agile": [r"agile", r"scrum"], "data structures": [r"data structures?"],
    "algorithms": [r"algorithms?"], "system design": [r"system design"],
}


@dataclass
class ATSMatch:
    score: float                       # coverage of JD keywords 0..1
    present: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    jd_total: int = 0


def keywords_in(text: str) -> set[str]:
    t = (text or "").lower()
    found = set()
    for canonical, patterns in _LEXICON.items():
        if any(re.search(p, t) for p in patterns):
            found.add(canonical)
    return found


def keyword_match(jd_text: str, resume_text: str) -> ATSMatch:
    jd = keywords_in(jd_text)
    resume = keywords_in(resume_text)
    if not jd:
        return ATSMatch(score=1.0, present=[], missing=[], jd_total=0)
    present = sorted(jd & resume)
    missing = sorted(jd - resume)
    return ATSMatch(score=round(len(present) / len(jd), 2),
                    present=present, missing=missing, jd_total=len(jd))
