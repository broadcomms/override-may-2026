"""Granite-backed session-scoped copilot orchestration."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from statistics import mean
from typing import Any, Sequence

from pydantic import ValidationError

from analysis.post_race_report import build_race_report
from core.reasoning import WatsonxChatClient
from ingest.schema import CopilotAnswer, CopilotMessage, Session

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "copilot.system.md"
_COMPARE_RE = re.compile(r"compare\s+lap\s+(\d+)\s+(?:and|vs\.?|versus)\s+lap\s+(\d+)", re.IGNORECASE)
_SECTOR_RE = re.compile(r"sector\s+([123])", re.IGNORECASE)
_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", re.DOTALL | re.IGNORECASE)


class CopilotParseError(ValueError):
    """Raised when the Granite copilot response cannot be validated."""


def _load_system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _lap_by_number(session: Session, lap_number: int):
    return next((lap for lap in session.laps if lap.lap_number == lap_number), None)


def _top_recommendation(session: Session):
    if not session.recommendations:
        return None
    return sorted(
        session.recommendations,
        key=lambda rec: (
            {"high": 3, "medium": 2, "low": 1}[rec.zone.severity],
            rec.zone.lap_number,
        ),
        reverse=True,
    )[0]


def _dedupe_strings(items: Sequence[str], *, limit: int = 3) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        cleaned = item.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        out.append(cleaned)
        if len(out) >= limit:
            break
    return out


def _recommendation_snapshot(rec: Any) -> dict[str, Any]:
    validator = rec.validator.model_dump(mode="json") if hasattr(rec.validator, "model_dump") else rec.validator
    guardian = rec.guardian.model_dump(mode="json") if hasattr(rec.guardian, "model_dump") else rec.guardian
    return {
        "zone": rec.zone.model_dump(mode="json"),
        "reasoning": rec.reasoning.model_dump(mode="json"),
        "validator": validator,
        "guardian": guardian,
    }


def _session_summary_context(session: Session) -> dict[str, Any]:
    laps = session.laps
    best_lap = min(laps, key=lambda lap: lap.lap_time) if laps else None
    worst_lap = max(laps, key=lambda lap: lap.lap_time) if laps else None
    return {
        "summary": session.summary.model_dump(mode="json"),
        "regulation_source": (
            session.regulation_source.model_dump(mode="json")
            if session.regulation_source is not None
            else None
        ),
        "forecast": session.forecast.model_dump(mode="json") if session.forecast is not None else None,
        "best_lap": (
            {
                "lap_number": best_lap.lap_number,
                "lap_time_s": best_lap.lap_time,
                "soc_end_pct": round(best_lap.soc_end * 100, 1),
            }
            if best_lap is not None
            else None
        ),
        "worst_lap": (
            {
                "lap_number": worst_lap.lap_number,
                "lap_time_s": worst_lap.lap_time,
                "soc_end_pct": round(worst_lap.soc_end * 100, 1),
            }
            if worst_lap is not None
            else None
        ),
    }


def _compare_context(session: Session, lap_a: int, lap_b: int) -> dict[str, Any] | None:
    first = _lap_by_number(session, lap_a)
    second = _lap_by_number(session, lap_b)
    if first is None or second is None:
        return None
    return {
        "intent": "lap_compare",
        "lap_a": first.model_dump(mode="json"),
        "lap_b": second.model_dump(mode="json"),
        "delta_summary": {
            "lap_time_delta_s": round(second.lap_time - first.lap_time, 3),
            "net_energy_delta_mj": round(
                (second.deploy_mj - second.harvest_mj) - (first.deploy_mj - first.harvest_mj),
                3,
            ),
            "soc_end_delta_pct": round((second.soc_end - first.soc_end) * 100, 1),
        },
        "related_recommendations": [
            _recommendation_snapshot(rec)
            for rec in session.recommendations
            if rec.zone.lap_number in {lap_a, lap_b}
        ][:3],
    }


def _strategy_context(session: Session) -> dict[str, Any]:
    top = _top_recommendation(session)
    report = build_race_report(session)
    return {
        "intent": "strategy_explain",
        "top_recommendation": _recommendation_snapshot(top) if top is not None else None,
        "additional_recommendations": [
            _recommendation_snapshot(rec)
            for rec in sorted(
                session.recommendations,
                key=lambda rec: (
                    {"high": 3, "medium": 2, "low": 1}[rec.zone.severity],
                    rec.zone.lap_number,
                ),
                reverse=True,
            )[:3]
        ],
        "report_summary": {
            "executive_summary": report.executive_summary,
            "driver_score": report.driver_score,
            "battery_efficiency_score": report.battery_efficiency_score,
            "risk_score": report.risk_score,
            "key_moments": [moment.model_dump(mode="json") for moment in report.key_moments[:3]],
        },
    }


def _sector_context(session: Session, sector: int) -> dict[str, Any]:
    sector_key = {1: "sector1_time", 2: "sector2_time", 3: "sector3_time"}[sector]
    sector_splits = [
        {"lap_number": lap.lap_number, "sector_time_s": getattr(lap, sector_key)}
        for lap in session.laps
    ]
    return {
        "intent": "sector_analysis",
        "sector": sector,
        "average_sector_time_s": round(mean(item["sector_time_s"] for item in sector_splits), 3)
        if sector_splits
        else None,
        "sector_splits": sector_splits[:10],
        "related_recommendations": [
            _recommendation_snapshot(rec)
            for rec in session.recommendations
            if rec.zone.sector == sector
        ][:4],
    }


def _battery_context(session: Session) -> dict[str, Any]:
    if not session.laps:
        return {"intent": "battery_analysis", "battery_trend": None}
    first = session.laps[0]
    last = session.laps[-1]
    lowest = min(session.laps, key=lambda lap: lap.soc_end)
    return {
        "intent": "battery_analysis",
        "battery_trend": {
            "soc_start_pct": round(first.soc_start * 100, 1),
            "soc_end_pct": round(last.soc_end * 100, 1),
            "average_net_energy_mj_per_lap": round(
                mean(lap.harvest_mj - lap.deploy_mj for lap in session.laps),
                3,
            ),
            "lowest_soc_lap": lowest.lap_number,
            "lowest_soc_pct": round(lowest.soc_end * 100, 1),
            "forecast": session.forecast.model_dump(mode="json") if session.forecast is not None else None,
        },
        "energy_extremes": [
            {
                "lap_number": lap.lap_number,
                "net_energy_mj": round(lap.harvest_mj - lap.deploy_mj, 3),
                "soc_end_pct": round(lap.soc_end * 100, 1),
            }
            for lap in sorted(
                session.laps,
                key=lambda lap: abs(lap.harvest_mj - lap.deploy_mj),
                reverse=True,
            )[:5]
        ],
        "related_recommendations": [
            _recommendation_snapshot(rec)
            for rec in session.recommendations[:3]
        ],
    }


def _general_context(session: Session) -> dict[str, Any]:
    report = build_race_report(session)
    return {
        "intent": "general",
        "report_summary": report.model_dump(mode="json"),
        "top_recommendations": [
            _recommendation_snapshot(rec)
            for rec in sorted(
                session.recommendations,
                key=lambda rec: (
                    {"high": 3, "medium": 2, "low": 1}[rec.zone.severity],
                    rec.zone.lap_number,
                ),
                reverse=True,
            )[:3]
        ],
    }


def _build_context(
    session: Session,
    question: str,
    recent_turns: Sequence[CopilotMessage],
) -> dict[str, Any]:
    normalized = question.strip()
    compare = _COMPARE_RE.search(normalized)
    if compare:
        context = _compare_context(session, int(compare.group(1)), int(compare.group(2)))
        if context is not None:
            return context
    if "why" in normalized.lower() and (
        "recommend" in normalized.lower()
        or "strategy" in normalized.lower()
        or "conservative" in normalized.lower()
    ):
        return _strategy_context(session)
    sector_match = _SECTOR_RE.search(normalized)
    if sector_match is not None:
        return _sector_context(session, int(sector_match.group(1)))
    if "battery" in normalized.lower() or "energy" in normalized.lower():
        return _battery_context(session)
    return _general_context(session)


def render_user_message(
    session: Session,
    question: str,
    recent_turns: Sequence[CopilotMessage],
) -> str:
    payload = {
        "question": question.strip(),
        "recent_turns": [turn.model_dump(mode="json") for turn in recent_turns[-4:]],
        "session_context": _session_summary_context(session),
        "retrieved_context": _build_context(session, question, recent_turns),
    }
    return "## copilot_request\n" + json.dumps(payload, indent=2)


def parse_copilot_response(text: str) -> CopilotAnswer:
    raw = text.strip()
    if not raw:
        raise CopilotParseError("empty copilot response")
    fence = _FENCE_RE.match(raw)
    if fence:
        raw = fence.group(1).strip()
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        snippet = raw[:200].replace("\n", "\\n")
        raise CopilotParseError(
            f"copilot response is not valid JSON: {e.msg}; first 200 chars: {snippet!r}"
        ) from e
    try:
        return CopilotAnswer.model_validate(obj)
    except ValidationError as e:
        raise CopilotParseError(f"copilot output failed schema validation:\n{e}") from e


def _looks_like_unstructured_answer(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) < 40:
        return False
    return any(token in stripped for token in (". ", "\n", "lap", "sector", "battery", "energy"))


def _extract_supporting_laps_from_text(text: str) -> list[int]:
    seen: set[int] = set()
    laps: list[int] = []
    for match in re.finditer(r"\blap\s+(\d+)\b", text, flags=re.IGNORECASE):
        lap_number = int(match.group(1))
        if lap_number in seen:
            continue
        seen.add(lap_number)
        laps.append(lap_number)
    return laps


def _salvage_unstructured_answer(
    raw: str,
    session: Session,
    fallback: CopilotAnswer,
) -> CopilotAnswer | None:
    stripped = raw.strip()
    if not _looks_like_unstructured_answer(stripped):
        return None
    valid_laps = {lap.lap_number for lap in session.laps}
    supporting_laps = [lap for lap in _extract_supporting_laps_from_text(stripped) if lap in valid_laps]
    if not supporting_laps:
        supporting_laps = fallback.supporting_laps
    answer = re.sub(r"\s+", " ", stripped).strip()
    return CopilotAnswer(
        answer=answer,
        engine="granite",
        supporting_laps=supporting_laps,
        confidence=fallback.confidence,
        suggestions=fallback.suggestions,
    )


def _normalize_model_answer(answer: CopilotAnswer, session: Session, fallback: CopilotAnswer) -> CopilotAnswer:
    valid_laps = {lap.lap_number for lap in session.laps}
    supporting_laps = [lap for lap in answer.supporting_laps if lap in valid_laps]
    suggestions = _dedupe_strings(answer.suggestions, limit=3) or fallback.suggestions
    return answer.model_copy(
        update={
            "engine": "granite",
            "supporting_laps": supporting_laps,
            "suggestions": suggestions,
        }
    )


def _compare_laps_deterministic(session: Session, lap_a: int, lap_b: int) -> CopilotAnswer:
    first = _lap_by_number(session, lap_a)
    second = _lap_by_number(session, lap_b)
    if first is None or second is None:
        return CopilotAnswer(
            answer=f"OVERRIDE could not compare laps {lap_a} and {lap_b} because one of them is missing from this session.",
            engine="deterministic",
            supporting_laps=[lap for lap in (lap_a, lap_b) if _lap_by_number(session, lap) is not None],
            confidence="low",
            suggestions=["Ask about battery trend", "Ask why the main recommendation was surfaced"],
        )

    lap_time_delta = second.lap_time - first.lap_time
    energy_delta = (second.deploy_mj - second.harvest_mj) - (first.deploy_mj - first.harvest_mj)
    answer = (
        f"Lap {lap_b} ran {lap_time_delta:+.2f}s against lap {lap_a} and changed net energy by {energy_delta:+.2f} MJ. "
        f"Lap {lap_a} closed at {first.soc_end * 100:.0f}% SoC while lap {lap_b} closed at {second.soc_end * 100:.0f}%."
    )
    return CopilotAnswer(
        answer=answer,
        engine="deterministic",
        supporting_laps=[lap_a, lap_b],
        confidence="high",
        suggestions=["Ask which lap was more efficient", "Ask about sector instability", "Ask about the top recommendation"],
    )


def _explain_strategy_deterministic(session: Session) -> CopilotAnswer:
    top = _top_recommendation(session)
    if top is None:
        return CopilotAnswer(
            answer="This session finished without a highlighted recommendation, so OVERRIDE does not have a strategy intervention to explain.",
            engine="deterministic",
            supporting_laps=[],
            confidence="medium",
            suggestions=["Ask about battery trend", "Compare two laps"],
        )
    return CopilotAnswer(
        answer=(
            f"OVERRIDE highlighted lap {top.zone.lap_number}, sector {top.zone.sector} because {top.reasoning.cause} "
            f"{top.reasoning.consequence} The recommended next move was: {top.reasoning.recommendation}"
        ),
        engine="deterministic",
        supporting_laps=[top.zone.lap_number],
        confidence=top.reasoning.confidence,
        suggestions=["Compare that lap to another lap", "Ask about battery trend", "Ask about sector analysis"],
    )


def _analyze_sector_deterministic(session: Session, sector: int) -> CopilotAnswer:
    related = [rec for rec in session.recommendations if rec.zone.sector == sector]
    if related:
        laps = sorted({rec.zone.lap_number for rec in related})
        answer = (
            f"Sector {sector} drew attention on laps {', '.join(str(lap) for lap in laps)}. "
            f"The strongest flag was: {related[0].reasoning.cause}"
        )
        return CopilotAnswer(
            answer=answer,
            engine="deterministic",
            supporting_laps=laps,
            confidence="medium",
            suggestions=["Ask why that recommendation was surfaced", "Compare one of those laps", "Ask about battery trend"],
        )

    sector_times = []
    for lap in session.laps:
        sector_time = [lap.sector1_time, lap.sector2_time, lap.sector3_time][sector - 1]
        sector_times.append(sector_time)
    avg_sector = mean(sector_times) if sector_times else 0.0
    return CopilotAnswer(
        answer=(
            f"Sector {sector} did not trigger a dedicated recommendation in this session. "
            f"Its average split still landed at {avg_sector:.2f}s across the recorded laps."
        ),
        engine="deterministic",
        supporting_laps=[],
        confidence="low",
        suggestions=["Ask about the top recommendation", "Ask about battery trend"],
    )


def _battery_summary_deterministic(session: Session) -> CopilotAnswer:
    if not session.laps:
        return CopilotAnswer(
            answer="No completed laps are available yet, so OVERRIDE cannot summarize the battery trend.",
            engine="deterministic",
            supporting_laps=[],
            confidence="low",
            suggestions=["Ask after race ingest completes"],
        )
    first = session.laps[0]
    last = session.laps[-1]
    avg_net = mean(lap.harvest_mj - lap.deploy_mj for lap in session.laps)
    return CopilotAnswer(
        answer=(
            f"Battery reserve moved from {first.soc_start * 100:.0f}% at the start to {last.soc_end * 100:.0f}% at the finish. "
            f"Average net energy per lap was {avg_net:+.2f} MJ, which explains why the session ended with the reserve at {last.soc_end * 100:.0f}%."
        ),
        engine="deterministic",
        supporting_laps=[first.lap_number, last.lap_number],
        confidence="medium",
        suggestions=["Compare two laps", "Ask why the top recommendation was surfaced", "Ask about a sector"],
    )


def _fallback_summary_deterministic(session: Session, recent_turns: Sequence[CopilotMessage]) -> CopilotAnswer:
    top = _top_recommendation(session)
    preface = ""
    if recent_turns:
        preface = "Using the current session context and your recent turns, "
    if top is not None:
        return CopilotAnswer(
            answer=(
                f"{preface}the clearest explainability anchor is lap {top.zone.lap_number}, sector {top.zone.sector}: "
                f"{top.reasoning.recommendation}"
            ),
            engine="deterministic",
            supporting_laps=[top.zone.lap_number],
            confidence=top.reasoning.confidence,
            suggestions=["Compare two laps", "Ask about battery trend", "Ask about sector 3"],
        )
    return CopilotAnswer(
        answer=f"{preface}this session is best explored by comparing laps or asking about the battery trend, because no zone recommendation was generated.",
        engine="deterministic",
        supporting_laps=[],
        confidence="low",
        suggestions=["Compare lap 1 and lap 3", "Ask about battery trend"],
    )


def _deterministic_answer(
    session: Session,
    question: str,
    recent_turns: Sequence[CopilotMessage],
) -> CopilotAnswer:
    normalized = question.strip()
    compare = _COMPARE_RE.search(normalized)
    if compare:
        return _compare_laps_deterministic(session, int(compare.group(1)), int(compare.group(2)))

    if "why" in normalized.lower() and (
        "recommend" in normalized.lower()
        or "strategy" in normalized.lower()
        or "conservative" in normalized.lower()
    ):
        return _explain_strategy_deterministic(session)

    sector_match = _SECTOR_RE.search(normalized)
    if sector_match is not None:
        return _analyze_sector_deterministic(session, int(sector_match.group(1)))

    if "battery" in normalized.lower() or "energy" in normalized.lower():
        return _battery_summary_deterministic(session)

    return _fallback_summary_deterministic(session, recent_turns)


def answer_question(
    session: Session,
    question: str,
    *,
    recent_turns: Sequence[CopilotMessage] | None = None,
    client: WatsonxChatClient | None = None,
) -> CopilotAnswer:
    recent_turns = recent_turns or []
    fallback = _deterministic_answer(session, question, recent_turns)
    compare = _COMPARE_RE.search(question.strip())
    if compare and _compare_context(session, int(compare.group(1)), int(compare.group(2))) is None:
        return fallback
    if client is None:
        return fallback

    system = _load_system_prompt()
    user = render_user_message(session, question, recent_turns)
    raw = client.chat(system=system, user=user, temperature=0.2, max_tokens=768)
    try:
        parsed = parse_copilot_response(raw)
    except CopilotParseError:
        salvaged = _salvage_unstructured_answer(raw, session, fallback)
        if salvaged is not None:
            logger.info("Granite copilot returned prose; salvaging as Granite-backed answer")
            return salvaged
        logger.warning("Granite copilot response fell back to deterministic mode", exc_info=True)
        return fallback
    return _normalize_model_answer(parsed, session, fallback)


__all__ = [
    "CopilotParseError",
    "answer_question",
    "parse_copilot_response",
    "render_user_message",
]
