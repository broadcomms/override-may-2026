"""Pass-2 AI safety scoring — Granite Guardian BYOC.

Scores a `ReasoningOutput` against the two BYOC criteria defined in
`guardian/byoc_criteria.yaml`:

  - `energy_safety`            — would the recommended action violate
                                 harvest/deployment caps, drive SoC
                                 negative, or exceed MGU-K envelope?
  - `regulation_consistency`   — does the citation exist verbatim, align
                                 with the zone type, and is it not
                                 contradicted elsewhere in the passage?

Each criterion is scored on [0.0, 1.0] per its rubric. Both must clear
`pass_threshold` (default 0.70 from the YAML) for `passed=True`.

Architecture (matches `core/reasoning.py`):

  - `WatsonxGuardianClient` Protocol — minimal `chat()` interface, mockable.
  - `WatsonxAIGuardianClient` — real impl using `ibm/granite-guardian-3-8b`
    on watsonx.ai's chat API. Temperature pinned to 0.0 (Granite Guardian
    docs are explicit: scoring requires deterministic decoding).
  - `score_recommendation(...)` — public entry point. Internally scores the
    two criteria **in parallel** via a `ThreadPoolExecutor` to stay inside
    the per-zone Guardian budget (`04-api.md §5`: ≤ 4 s/zone).

What this module does NOT do:
  - **No retry loop.** `byoc_criteria.yaml`'s `on_fail: regenerate_with_*`
    means re-run reasoning, not re-run Guardian. The retry orchestration
    (reason → validate → guard → if fail, regenerate reason → repeat,
    max 2 retries) lives in `core/pipeline.py` (P2.7). `GuardianResult`
    exposes `retry_count` + `final_confidence` so the orchestrator fills
    them based on the retry sequence outcome.
  - **No mutation.** Inputs are frozen Pydantic objects; outputs are new
    frozen instances.
"""

from __future__ import annotations

import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Optional, Protocol

import yaml
from pydantic import BaseModel, ConfigDict, Field

from ingest.schema import LapWindow, ReasoningOutput, RegulationChunk

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# BYOC criteria — loaded once at import from the canonical YAML
# ──────────────────────────────────────────────────────────────────────────────


_BYOC_PATH = Path(__file__).resolve().parent.parent / "guardian" / "byoc_criteria.yaml"


def _load_byoc() -> dict[str, Any]:
    """Single source of truth: rubrics, threshold, criterion IDs all
    come from `guardian/byoc_criteria.yaml`. Tweak the YAML, no code
    change needed."""
    with _BYOC_PATH.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


_BYOC = _load_byoc()
_CRITERIA_BY_ID: dict[str, dict[str, Any]] = {c["id"]: c for c in _BYOC["criteria"]}
_PASS_THRESHOLD: float = float(_BYOC["ui_display"]["pass_threshold"])

ENERGY_SAFETY = "energy_safety"
REGULATION_CONSISTENCY = "regulation_consistency"


# ──────────────────────────────────────────────────────────────────────────────
# Result type — lives here per `04-schema.md §1` ownership
# ──────────────────────────────────────────────────────────────────────────────


class GuardianResult(BaseModel):
    """Pass-2 outcome.

    Mirrors `04-schema.md §9`. `retry_count` and `final_confidence` are
    set by `core/pipeline.py` (P2.7) — not by this module. See module
    docstring for retry-orchestration boundary.
    """

    model_config = ConfigDict(frozen=True)

    passed: bool
    pass_threshold: float = Field(default=_PASS_THRESHOLD, ge=0.0, le=1.0)
    scores: dict[str, float] = Field(default_factory=dict)
    rationales: dict[str, str] = Field(default_factory=dict)
    retry_count: int = Field(default=0, ge=0, le=2)
    final_confidence: Literal["low", "medium", "high"] = "medium"


# ──────────────────────────────────────────────────────────────────────────────
# Chat client abstraction (mirror of core.reasoning.WatsonxChatClient)
# ──────────────────────────────────────────────────────────────────────────────


class WatsonxGuardianClient(Protocol):
    """Minimal Guardian-API surface. Tests pass a fake."""

    def chat(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.0,
        max_tokens: int = 256,
    ) -> str:
        ...


class WatsonxAIGuardianClient:
    """Real watsonx.ai client for `ibm/granite-guardian-3-8b`.

    Temperature default 0.0 — Granite Guardian docs are explicit that
    deterministic decoding is required for accurate scoring. Override at
    your own risk.
    """

    def __init__(
        self,
        model_id: Optional[str] = None,
        api_key: Optional[str] = None,
        url: Optional[str] = None,
        project_id: Optional[str] = None,
    ):
        self.model_id = model_id or os.environ.get(
            "GRANITE_GUARDIAN", "ibm/granite-guardian-3-8b"
        )
        self.api_key = api_key or os.environ.get("WATSONX_API_KEY")
        self.url = url or os.environ.get("WATSONX_URL")
        self.project_id = project_id or os.environ.get("WATSONX_PROJECT_ID")
        if not all([self.api_key, self.url, self.project_id]):
            raise RuntimeError(
                "WatsonxAIGuardianClient: missing one of WATSONX_API_KEY / "
                "WATSONX_URL / WATSONX_PROJECT_ID — see .env.example."
            )
        from ibm_watsonx_ai import Credentials
        from ibm_watsonx_ai.foundation_models import ModelInference

        self._creds = Credentials(api_key=self.api_key, url=self.url)
        self._model = ModelInference(
            model_id=self.model_id,
            credentials=self._creds,
            project_id=self.project_id,
        )

    def chat(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.0,
        max_tokens: int = 256,
    ) -> str:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        params = {"temperature": temperature, "max_tokens": max_tokens}
        resp = self._model.chat(messages=messages, params=params)
        return _extract_chat_text(resp)


def _extract_chat_text(resp: Any) -> str:
    """Same shape-tolerant extraction as core/reasoning.py."""
    if isinstance(resp, str):
        return resp
    if isinstance(resp, dict):
        choices = resp.get("choices") or []
        if choices:
            content = (choices[0].get("message") or {}).get("content")
            if isinstance(content, str):
                return content
    raise RuntimeError(f"unexpected guardian chat response shape: {type(resp).__name__}")


# ──────────────────────────────────────────────────────────────────────────────
# Prompt rendering — uses the YAML rubrics verbatim
# ──────────────────────────────────────────────────────────────────────────────


# Granite Guardian is a binary classifier (Yes = risk detected, No = safe).
# We frame each criterion as a *risk question* so the polarity matches:
# "Yes" → risk → score 0.0 → fails. "No" → safe → score 1.0 → passes.
# The graded rubric in `byoc_criteria.yaml` is informational; with a binary
# classifier we get pass/fail clarity, not a 0.4-0.6 nuance band. This is
# the honest mapping.
_RISK_QUESTION_BY_CRITERION: dict[str, str] = {
    ENERGY_SAFETY: (
        "Does the recommendation, if followed, violate the per-lap harvest cap, "
        "drive state-of-charge negative, or exceed the MGU-K deployment limit "
        "stated in the regulation?"
    ),
    REGULATION_CONSISTENCY: (
        "Is the cited regulation passage missing from the retrieved chunks, "
        "irrelevant to the zone type, or contradicted by another part of the "
        "same regulation?"
    ),
}


_GUARDIAN_SYSTEM_TMPL = """\
You are OVERRIDE-Guardian, an AI safety evaluator for F1 race-strategy recommendations.

You evaluate whether the recommendation below exhibits the risk described by the criterion.

# Criterion: {name}
{description}

# Risk question
{risk_question}

# Reference rubric (for context — your output is binary)
{decision_rubric}

# Output — STRICT FORMAT, one line, exactly one of:
Yes: <one short sentence on why the risk is present>
No: <one short sentence on why the risk is not present>

Output ONLY that single line. Yes means risk detected (fail). No means safe (pass).
"""


def _render_system_prompt(criterion_id: str) -> str:
    c = _CRITERIA_BY_ID[criterion_id]
    return _GUARDIAN_SYSTEM_TMPL.format(
        name=c["name"],
        description=c["description"].strip(),
        risk_question=_RISK_QUESTION_BY_CRITERION[criterion_id],
        decision_rubric=c["decision_rubric"].strip(),
    )


def _render_lap_window_summary(lap_window: LapWindow) -> str:
    """Compact lap-window summary — enough for the rubric, less verbose
    than the full reasoning prompt's table (Guardian doesn't need 30 rows
    of telemetry, it needs the SoC envelope + harvest cap context)."""
    lines = [
        f"session_id: {lap_window.session_id}",
        f"soc_max:    {lap_window.soc_max:.2f} MJ",
        f"laps:       {len(lap_window.laps)}",
    ]
    if lap_window.track_id:
        lines.append(f"track_id:   {lap_window.track_id}")
    # Per-lap SoC trajectory + harvest/deploy summary
    if lap_window.laps:
        lines.append("")
        lines.append("| lap | soc_start | soc_end | harvest_mj | deploy_mj |")
        lines.append("|----:|----------:|--------:|-----------:|----------:|")
        for L in lap_window.laps:
            lines.append(
                f"| {L.lap_number} | {L.soc_start:.3f} | {L.soc_end:.3f} | "
                f"{L.harvest_mj:.2f} | {L.deploy_mj:.2f} |"
            )
    return "\n".join(lines)


def _chunk_for_prompt(chunk: RegulationChunk) -> dict:
    """Serialize a RegulationChunk for prompt inclusion.

    Excludes the 768-dim `embedding` field — it's a retrieval artifact,
    not human-readable, and ~19 KB of float JSON would blow Granite
    Guardian's 8K-token context window.
    """
    return chunk.model_dump(mode="json", exclude={"embedding"})


def _render_user_message_energy_safety(
    reasoning: ReasoningOutput,
    lap_window: LapWindow,
    regulation: Optional[RegulationChunk],
) -> str:
    parts = [
        "## reasoning_output",
        json.dumps(reasoning.model_dump(mode="json"), indent=2),
        "",
        "## lap_context",
        _render_lap_window_summary(lap_window),
        "",
        "## regulation",
        json.dumps(_chunk_for_prompt(regulation), indent=2)
        if regulation is not None
        else "null (no regulation chunk available)",
    ]
    return "\n".join(parts)


def _render_user_message_regulation_consistency(
    reasoning: ReasoningOutput,
    cited_chunk: RegulationChunk,
) -> str:
    """Render the regulation_consistency input for Guardian.

    Per the YAML rubric: Guardian scores against "the retrieved passage"
    (singular). Granite Guardian has an 8K-token context window, so we
    pass only the cited chunk — not the full corpus. Cross-corpus
    contradiction checking (rubric clause c) is a future enhancement
    requiring either a larger Guardian model or chunked sub-passes.

    Also strips the embedding field (~19 KB of floats per chunk) — it's
    irrelevant to scoring and would single-handedly blow the context.
    """
    parts = [
        "## reasoning_output",
        json.dumps(reasoning.model_dump(mode="json"), indent=2),
        "",
        "## cited_chunk (the regulation passage Guardian must validate against)",
        json.dumps(_chunk_for_prompt(cited_chunk), indent=2),
    ]
    return "\n".join(parts)


# ──────────────────────────────────────────────────────────────────────────────
# Tolerant JSON parsing — same fence-stripping as core/reasoning.py
# ──────────────────────────────────────────────────────────────────────────────


_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", re.DOTALL | re.IGNORECASE)
# Match a leading Yes/No (with or without trailing punctuation/rationale)
_YES_NO_RE = re.compile(r"^\s*(yes|no)\b\s*[:.\-—]?\s*(.*)\s*$", re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True)
class _CriterionScore:
    score: float
    rationale: str


class GuardianParseError(ValueError):
    """Raised when the model's response can't be coerced into a score+rationale."""


def _parse_score_response(text: str) -> _CriterionScore:
    """Parse a Guardian risk-classification response.

    Granite Guardian's natural output is a binary "Yes"/"No" verdict.
    We map:
      "Yes" → risk detected → score 0.0 (fail)
      "No"  → no risk       → score 1.0 (pass)

    Also accepts a graded JSON form `{"score": <float>, "rationale": ...}`
    as a forward-compatibility fallback (in case future Guardian
    revisions or a custom-tuned model emits scores directly).

    Tolerant of code fences and surrounding whitespace. Clamps any
    numeric score to [0, 1].
    """
    raw = text.strip()
    if not raw:
        raise GuardianParseError("empty Guardian response")
    fence = _FENCE_RE.match(raw)
    if fence:
        raw = fence.group(1).strip()

    # 1. Yes/No form (Guardian's primary output)
    yn = _YES_NO_RE.match(raw)
    if yn:
        verdict = yn.group(1).lower()
        rationale = yn.group(2).strip() or (
            "risk detected" if verdict == "yes" else "no risk detected"
        )
        score = 0.0 if verdict == "yes" else 1.0
        return _CriterionScore(score=score, rationale=rationale)

    # 2. JSON form (graded — fallback for forward compatibility)
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        snippet = raw[:200].replace("\n", "\\n")
        raise GuardianParseError(
            f"Guardian response is neither Yes/No nor JSON: {e.msg}; "
            f"first 200 chars: {snippet!r}"
        ) from e
    if not isinstance(obj, dict):
        raise GuardianParseError(f"Guardian response is not an object: {type(obj).__name__}")
    if "score" not in obj or "rationale" not in obj:
        raise GuardianParseError(
            f"Guardian JSON response missing required fields; got keys: {sorted(obj.keys())}"
        )
    try:
        score = float(obj["score"])
    except (TypeError, ValueError) as e:
        raise GuardianParseError(f"Guardian score is not numeric: {obj['score']!r}") from e
    score = max(0.0, min(1.0, score))  # clamp
    rationale = str(obj["rationale"]).strip()
    if not rationale:
        rationale = "(model returned no rationale)"
    return _CriterionScore(score=score, rationale=rationale)


# ──────────────────────────────────────────────────────────────────────────────
# Per-criterion scorers
# ──────────────────────────────────────────────────────────────────────────────


# Auto-pass score for `regulation_consistency` when there's nothing to
# validate against (citation=None or no chunks). Per the design call in
# the P2.6 review: don't double-penalize — the reasoning step already
# self-flagged with confidence=low per prompts/reasoning.system.md §39.
NULL_CITATION_AUTO_PASS_SCORE = 0.7
NULL_CITATION_RATIONALE = (
    "no citation to validate; reasoning has already self-flagged with confidence=low"
)


def _score_energy_safety(
    reasoning: ReasoningOutput,
    lap_window: LapWindow,
    regulation: Optional[RegulationChunk],
    *,
    client: WatsonxGuardianClient,
    temperature: float = 0.0,
    max_tokens: int = 256,
) -> _CriterionScore:
    from api.observability import traced_span

    system = _render_system_prompt(ENERGY_SAFETY)
    user = _render_user_message_energy_safety(reasoning, lap_window, regulation)
    with traced_span(
        "guardian.energy_safety",
        criterion=ENERGY_SAFETY,
        regulation_present=regulation is not None,
    ):
        raw = client.chat(system=system, user=user, temperature=temperature, max_tokens=max_tokens)
        result = _parse_score_response(raw)
        return result


def _score_regulation_consistency(
    reasoning: ReasoningOutput,
    regulation: Optional[RegulationChunk],
    *,
    client: WatsonxGuardianClient,
    temperature: float = 0.0,
    max_tokens: int = 256,
) -> _CriterionScore:
    from api.observability import traced_span

    # Auto-pass: nothing to validate. Don't burn an API call.
    # - Reasoning emitted no citation (pre-G-4 / no relevant chunk found), OR
    # - No cited chunk supplied to Guardian (caller didn't pass one)
    if reasoning.regulation_citation is None or regulation is None:
        with traced_span(
            "guardian.regulation_consistency.auto_pass",
            criterion=REGULATION_CONSISTENCY,
            auto_pass=True,
        ):
            return _CriterionScore(
                score=NULL_CITATION_AUTO_PASS_SCORE,
                rationale=NULL_CITATION_RATIONALE,
            )
    system = _render_system_prompt(REGULATION_CONSISTENCY)
    user = _render_user_message_regulation_consistency(reasoning, regulation)
    with traced_span(
        "guardian.regulation_consistency",
        criterion=REGULATION_CONSISTENCY,
        cited_section=regulation.source.section,
    ):
        raw = client.chat(system=system, user=user, temperature=temperature, max_tokens=max_tokens)
        return _parse_score_response(raw)


# ──────────────────────────────────────────────────────────────────────────────
# Public entry point
# ──────────────────────────────────────────────────────────────────────────────


def score_recommendation(
    reasoning: ReasoningOutput,
    lap_window: LapWindow,
    regulation: Optional[RegulationChunk] = None,
    *,
    client: WatsonxGuardianClient,
    pass_threshold: Optional[float] = None,
    temperature: float = 0.0,
    max_tokens: int = 256,
) -> GuardianResult:
    """Score `reasoning` against both BYOC criteria via watsonx Guardian.

    Args:
        reasoning: the model's structured output from core.reasoning.
        lap_window: the same lap_window passed to reasoning. Drives the
            energy_safety rubric (SoC trajectory, harvest pattern).
        regulation: the single chunk reasoning grounded against (if any).
            Used by BOTH criteria — energy_safety for the cap framing,
            regulation_consistency to verify citation alignment. Pass
            None pre-G-4 — `regulation_consistency` auto-passes at 0.7
            with the documented "no citation to validate" rationale.
        client: injected `WatsonxGuardianClient`. Tests pass a fake.
        pass_threshold: threshold both scores must clear for `passed=True`.
            Defaults to `byoc_criteria.yaml`'s `ui_display.pass_threshold`.
        temperature: passed to client.chat. Default 0.0; raise at your own
            risk — Granite Guardian requires deterministic decoding.
        max_tokens: per-criterion output cap. 256 is plenty for the
            Yes/No verdict + one-sentence rationale.

    Returns:
        GuardianResult with both scores, rationales, and the aggregate
        `passed` flag. `retry_count` defaults to 0 and `final_confidence`
        defaults to "medium" — both are filled by `core/pipeline.py` based
        on the retry sequence outcome (NOT this module's concern).

    Note on context budget: Granite Guardian 3-8b's context window is
    8K tokens. We pass only the single cited chunk to
    `regulation_consistency`, not the full corpus. Cross-chunk
    contradiction checking (YAML rubric clause c) is a future
    enhancement requiring chunked sub-passes.
    """
    threshold = pass_threshold if pass_threshold is not None else _PASS_THRESHOLD

    # Score both criteria in parallel — embarrassingly so within a single
    # zone since they share no state. ThreadPoolExecutor over urllib3
    # connections is thread-safe; this halves per-zone Guardian latency
    # vs sequential.
    with ThreadPoolExecutor(max_workers=2) as pool:
        future_es = pool.submit(
            _score_energy_safety,
            reasoning, lap_window, regulation,
            client=client, temperature=temperature, max_tokens=max_tokens,
        )
        future_rc = pool.submit(
            _score_regulation_consistency,
            reasoning, regulation,
            client=client, temperature=temperature, max_tokens=max_tokens,
        )
        es = future_es.result()
        rc = future_rc.result()

    scores = {ENERGY_SAFETY: es.score, REGULATION_CONSISTENCY: rc.score}
    rationales = {ENERGY_SAFETY: es.rationale, REGULATION_CONSISTENCY: rc.rationale}
    passed = all(v >= threshold for v in scores.values())

    logger.info(
        "guardian: passed=%s scores=%s threshold=%.2f",
        passed,
        {k: round(v, 3) for k, v in scores.items()},
        threshold,
    )

    return GuardianResult(
        passed=passed,
        pass_threshold=threshold,
        scores=scores,
        rationales=rationales,
        retry_count=0,                 # set by P2.7 orchestrator
        final_confidence="medium",     # set by P2.7 orchestrator
    )


__all__ = [
    "ENERGY_SAFETY",
    "REGULATION_CONSISTENCY",
    "NULL_CITATION_AUTO_PASS_SCORE",
    "GuardianResult",
    "GuardianParseError",
    "WatsonxGuardianClient",
    "WatsonxAIGuardianClient",
    "score_recommendation",
]
