"""LLM client wrapper (LLD §6). Two surfaces:
  - parse():    structured JSON output validated against a pydantic schema
                (matching, factual verification, fit assessment).
  - generate(): free text out (resume tailoring), with adaptive thinking.

Both are pure text-in/text-out: NO tools are ever passed, so untrusted job text
cannot trigger an action (SECURITY.md T1). A Protocol + FakeLLM make the whole
pipeline testable offline without network or an API key.

Models (per PRD R3): Sonnet 5 for triage/verify/enrich, Opus 4.8 for tailoring."""

from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel

TRIAGE_MODEL = "claude-sonnet-5"
TAILOR_MODEL = "claude-opus-4-8"

T = TypeVar("T", bound=BaseModel)


class LLMClient(Protocol):
    def parse(self, *, model: str, system: str, user: str,
              schema: type[T], max_tokens: int = 2048) -> T: ...

    def generate(self, *, model: str, system: str, user: str,
                 max_tokens: int = 8000, thinking: bool = True) -> str: ...


# USD per 1M tokens (input, output) — for run cost estimates (PRD NFR4).
_PRICES = {
    "claude-opus-4-8": (5.0, 25.0),
    "claude-sonnet-5": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}


class AnthropicLLM:
    """Real client. Structured calls use messages.parse(); tailoring uses
    messages.create() with adaptive thinking. Neither passes `tools`.
    Tracks cumulative token usage + estimated cost per run."""

    def __init__(self, api_key: str | None = None):
        import anthropic
        from collections import defaultdict
        self._client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        self.usage: dict = defaultdict(lambda: {"calls": 0, "in": 0, "out": 0})

    def _track(self, model: str, usage) -> None:
        u = self.usage[model]
        u["calls"] += 1
        u["in"] += (getattr(usage, "input_tokens", 0) or 0) + \
                   (getattr(usage, "cache_read_input_tokens", 0) or 0) + \
                   (getattr(usage, "cache_creation_input_tokens", 0) or 0)
        u["out"] += getattr(usage, "output_tokens", 0) or 0

    def cost_summary(self) -> dict:
        total_in = total_out = cost = 0.0
        by_model = {}
        for model, u in self.usage.items():
            pin, pout = _PRICES.get(model, (0.0, 0.0))
            c = u["in"] / 1e6 * pin + u["out"] / 1e6 * pout
            by_model[model] = {**u, "cost_usd": round(c, 4)}
            cost += c; total_in += u["in"]; total_out += u["out"]
        return {"input_tokens": int(total_in), "output_tokens": int(total_out),
                "cost_usd": round(cost, 4), "by_model": by_model}

    def parse(self, *, model, system, user, schema, max_tokens=2048):
        resp = self._client.messages.parse(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_format=schema,
        )
        self._track(model, getattr(resp, "usage", None))
        return resp.parsed_output

    def generate(self, *, model, system, user, max_tokens=8000, thinking=True):
        kwargs = dict(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        if thinking:
            kwargs["thinking"] = {"type": "adaptive"}
            kwargs["output_config"] = {"effort": "high"}
        resp = self._client.messages.create(**kwargs)
        self._track(model, getattr(resp, "usage", None))
        return "".join(b.text for b in resp.content if b.type == "text")


class FakeLLM:
    """Deterministic test double. `parse_fn`/`generate_fn` receive the user text
    and return a dict (coerced to the schema) / a string respectively."""

    def __init__(self, parse_fn=None, generate_fn=None):
        self._parse_fn = parse_fn
        self._generate_fn = generate_fn
        self.parse_calls: list[dict] = []
        self.generate_calls: list[dict] = []

    def parse(self, *, model, system, user, schema, max_tokens=2048):
        self.parse_calls.append({"model": model, "system": system, "user": user})
        if self._parse_fn is None:
            raise RuntimeError("FakeLLM.parse called but no parse_fn provided")
        out = self._parse_fn(user, schema)
        return out if isinstance(out, BaseModel) else schema(**out)

    def generate(self, *, model, system, user, max_tokens=8000, thinking=True):
        self.generate_calls.append({"model": model, "system": system, "user": user})
        if self._generate_fn is None:
            raise RuntimeError("FakeLLM.generate called but no generate_fn provided")
        return self._generate_fn(user)


# --- structured decision schemas (what the LLM returns) --------------------

class TriageDecision(BaseModel):
    relevant: bool
    score: float
    reasons: list[str]


class FactualCheck(BaseModel):
    passed: bool
    unsupported_claims: list[str]
    notes: str = ""


class FitAssessment(BaseModel):
    needs_heavy_rewrite: bool
    rationale: str = ""
