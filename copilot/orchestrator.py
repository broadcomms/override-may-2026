"""Granite-backed session-scoped copilot orchestration."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from statistics import mean
from typing import Any, Mapping, Sequence

from pydantic import ValidationError

from analysis.post_race_report import build_race_report
from core.reasoning import WatsonxChatClient
from ingest.schema import CopilotAnswer, CopilotMessage, Session

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "copilot.system.md"
_COMPARE_RE = re.compile(r"compare\s+lap\s+(\d+)\s+(?:and|vs\.?|versus)\s+lap\s+(\d+)", re.IGNORECASE)
_SECTOR_RE = re.compile(r"sector\s+([123])", re.IGNORECASE)
_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", re.DOTALL | re.IGNORECASE)
_GREETING_RE = re.compile(r"^(?:hi|hello|hey|good\s+(?:morning|afternoon|evening)|yo)\b[!. ]*$", re.IGNORECASE)
_THANKS_RE = re.compile(r"^(?:thanks|thank you|cheers|got it|okay|ok)\b[!. ]*$", re.IGNORECASE)
_ANSWER_PREFIX_RE = re.compile(r"^\s*(?:\*{0,2}answer\*{0,2}\s*:\s*)", re.IGNORECASE)
_METADATA_MARKERS = (
    re.compile(r"\bconfidence\s*:", re.IGNORECASE),
    re.compile(r"\bsupporting laps?\s*:", re.IGNORECASE),
    re.compile(r"\bsuggestions?\s*:", re.IGNORECASE),
)


def _is_greeting(text: str) -> bool:
    return bool(_GREETING_RE.match(text.strip()))


def _is_acknowledgement(text: str) -> bool:
    return bool(_THANKS_RE.match(text.strip()))


def _wants_lap_comparison_but_unspecified(text: str) -> bool:
    lowered = text.strip().lower()
    return "compare" in lowered and "lap" in lowered and _COMPARE_RE.search(text) is None


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


def _specific_compare_pair(
    session: Session,
    request_context: Mapping[str, Any] | None = None,
) -> tuple[int, int] | None:
    live_payload = _live_context_payload(request_context)
    if live_payload is not None:
        completed = [
            int(lap["lap"])
            for lap in live_payload["completed_laps"]
            if isinstance(lap.get("lap"), int)
        ]
        if len(completed) >= 2:
            return completed[-2], completed[-1]
    if len(session.laps) >= 2:
        latest = session.laps[-1].lap_number
        top = _top_recommendation(session)
        if top is not None and top.zone.lap_number != latest:
            return top.zone.lap_number, latest
        return session.laps[-2].lap_number, latest
    return None


def _default_suggestions(
    session: Session,
    request_context: Mapping[str, Any] | None = None,
) -> list[str]:
    compare_pair = _specific_compare_pair(session, request_context)
    live_payload = _live_context_payload(request_context)
    if live_payload is not None:
        latest_snapshot = live_payload.get("latest_snapshot")
        latest_lap = latest_snapshot.get("lap") if isinstance(latest_snapshot, Mapping) else None
        suggestions = [
            "Are we under battery pressure now?",
            f"What changed on lap {latest_lap}?" if isinstance(latest_lap, int) else "What changed this lap?",
            "Why did the latest insight fire?",
        ]
        if compare_pair is not None:
            suggestions[1] = f"Compare lap {compare_pair[0]} and lap {compare_pair[1]}"
        return suggestions

    top = _top_recommendation(session)
    suggestions = [
        "What does the battery trend look like?",
        "What happened in sector 3?",
        "Why did OVERRIDE surface that recommendation?",
    ]
    if compare_pair is not None:
        suggestions[0] = f"Compare lap {compare_pair[0]} and lap {compare_pair[1]}"
    if top is not None:
        suggestions[2] = f"Why did lap {top.zone.lap_number} stand out?"
        suggestions[1] = f"What happened in sector {top.zone.sector}?"
    return suggestions


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


def _live_context_payload(request_context: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if request_context is None or request_context.get("mode") != "live_race":
        return None
    live = request_context.get("live")
    if not isinstance(live, Mapping):
        return None
    latest_snapshot = live.get("latest_snapshot")
    completed_laps = live.get("completed_laps")
    insights = live.get("insights")
    payload = {
        "intent": "live_race",
        "race_state": live.get("race_state"),
        "latest_snapshot": latest_snapshot if isinstance(latest_snapshot, Mapping) else None,
        "completed_laps": [
            lap for lap in completed_laps if isinstance(lap, Mapping)
        ][-5:] if isinstance(completed_laps, Sequence) else [],
        "insights": [
            insight for insight in insights if isinstance(insight, Mapping)
        ][:5] if isinstance(insights, Sequence) else [],
        "focus_lap": request_context.get("lap_number"),
    }
    if (
        payload["race_state"] is None
        and payload["latest_snapshot"] is None
        and not payload["completed_laps"]
        and not payload["insights"]
    ):
        return None
    return payload


def _live_lap_by_number(request_context: Mapping[str, Any] | None, lap_number: int) -> Mapping[str, Any] | None:
    payload = _live_context_payload(request_context)
    if payload is None:
        return None
    return next(
        (
            lap
            for lap in payload["completed_laps"]
            if isinstance(lap.get("lap"), int) and lap["lap"] == lap_number
        ),
        None,
    )


def _compare_live_context(
    request_context: Mapping[str, Any] | None,
    lap_a: int,
    lap_b: int,
) -> dict[str, Any] | None:
    first = _live_lap_by_number(request_context, lap_a)
    second = _live_lap_by_number(request_context, lap_b)
    if first is None or second is None:
        return None
    return {
        "intent": "live_lap_compare",
        "lap_a": first,
        "lap_b": second,
        "delta_summary": {
            "lap_time_delta_s": round(float(second["lap_time_s"]) - float(first["lap_time_s"]), 3),
            "net_energy_delta_mj": round(
                (float(second["deploy_mj"]) - float(second["harvest_mj"]))
                - (float(first["deploy_mj"]) - float(first["harvest_mj"])),
                3,
            ),
            "soc_end_delta_pct": round((float(second["soc_end"]) - float(first["soc_end"])) * 100, 1),
        },
    }


def _build_context(
    session: Session,
    question: str,
    recent_turns: Sequence[CopilotMessage],
    request_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = question.strip()
    lowered = normalized.lower()
    if _is_greeting(normalized) or _is_acknowledgement(normalized):
        return {
            "intent": "smalltalk",
            "current_focus": "live_race" if _live_context_payload(request_context) is not None else "session",
            "recent_topics": [turn.content for turn in recent_turns[-2:] if turn.role == "assistant"],
        }
    if _wants_lap_comparison_but_unspecified(normalized):
        return {
            "intent": "compare_clarify",
            "suggested_pair": _specific_compare_pair(session, request_context),
        }
    compare = _COMPARE_RE.search(normalized)
    live_payload = _live_context_payload(request_context)
    if live_payload is not None:
        context = _compare_live_context(request_context, int(compare.group(1)), int(compare.group(2))) if compare else None
        if context is None:
            context = live_payload
        sector_match = _SECTOR_RE.search(normalized)
        if sector_match is not None:
            context["focus_sector"] = int(sector_match.group(1))
        if "battery" in lowered or "energy" in lowered:
            context["focus"] = "battery"
        elif "stop" in lowered or "state" in lowered:
            context["focus"] = "race_state"
        elif "why" in lowered or "strategy" in lowered or "recommend" in lowered:
            context["focus"] = "explanation"
        return context
    if compare:
        context = _compare_context(session, int(compare.group(1)), int(compare.group(2)))
        if context is not None:
            return context
    if "why" in lowered and (
        "recommend" in lowered
        or "strategy" in lowered
        or "conservative" in lowered
    ):
        return _strategy_context(session)
    sector_match = _SECTOR_RE.search(normalized)
    if sector_match is not None:
        return _sector_context(session, int(sector_match.group(1)))
    if "battery" in lowered or "energy" in lowered:
        return _battery_context(session)
    return _general_context(session)


def render_user_message(
    session: Session,
    question: str,
    recent_turns: Sequence[CopilotMessage],
    request_context: Mapping[str, Any] | None = None,
) -> str:
    payload = {
        "question": question.strip(),
        "recent_turns": [turn.model_dump(mode="json") for turn in recent_turns[-6:]],
        "request_context": request_context,
        "session_context": _session_summary_context(session),
        "retrieved_context": _build_context(session, question, recent_turns, request_context),
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


def _sanitize_answer_text(text: str) -> str:
    cleaned = text.strip()
    cleaned = _ANSWER_PREFIX_RE.sub("", cleaned)
    marker_positions = [
        match.start()
        for pattern in _METADATA_MARKERS
        if (match := pattern.search(cleaned)) is not None
    ]
    if marker_positions:
        cleaned = cleaned[: min(marker_positions)]
    cleaned = cleaned.replace("**", "").replace("__", "").replace("`", "")
    cleaned = re.sub(
        r"\s+(?:defined|described|set out|called out)\s+in\s+FIA[^.]*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s+under\s+FIA[^.]*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bFIA\s+20\d{2}[^.]*C\d+(?:\.\d+)*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bC\d+(?:\.\d+)+\b", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" -:\n\t")


def _normalize_suggestions(
    items: Sequence[str],
    *,
    session: Session,
    request_context: Mapping[str, Any] | None = None,
    fallback: Sequence[str] | None = None,
) -> list[str]:
    normalized: list[str] = []
    defaults = list(fallback or _default_suggestions(session, request_context))
    for item in items:
        cleaned = _sanitize_answer_text(item).strip()
        if not cleaned:
            continue
        if _wants_lap_comparison_but_unspecified(cleaned):
            compare_pair = _specific_compare_pair(session, request_context)
            if compare_pair is not None:
                cleaned = f"Compare lap {compare_pair[0]} and lap {compare_pair[1]}"
        normalized.append(cleaned)
    merged = _dedupe_strings(normalized + defaults, limit=3)
    return merged


def _salvage_unstructured_answer(
    raw: str,
    session: Session,
    fallback: CopilotAnswer,
    request_context: Mapping[str, Any] | None = None,
) -> CopilotAnswer | None:
    stripped = raw.strip()
    if not _looks_like_unstructured_answer(stripped):
        return None
    valid_laps = {lap.lap_number for lap in session.laps}
    supporting_laps = [lap for lap in _extract_supporting_laps_from_text(stripped) if lap in valid_laps]
    if not supporting_laps:
        supporting_laps = fallback.supporting_laps
    answer = _sanitize_answer_text(stripped)
    if not answer:
        return None
    return CopilotAnswer(
        answer=answer,
        engine="granite",
        supporting_laps=supporting_laps,
        confidence=fallback.confidence,
        suggestions=_normalize_suggestions(
            fallback.suggestions,
            session=session,
            request_context=request_context,
            fallback=fallback.suggestions,
        ),
    )


def _normalize_model_answer(
    answer: CopilotAnswer,
    session: Session,
    fallback: CopilotAnswer,
    request_context: Mapping[str, Any] | None = None,
) -> CopilotAnswer:
    valid_laps = {lap.lap_number for lap in session.laps}
    supporting_laps = [lap for lap in answer.supporting_laps if lap in valid_laps]
    suggestions = _normalize_suggestions(
        answer.suggestions,
        session=session,
        request_context=request_context,
        fallback=fallback.suggestions,
    )
    sanitized_answer = _sanitize_answer_text(answer.answer)
    return answer.model_copy(
        update={
            "answer": sanitized_answer or fallback.answer,
            "engine": "granite",
            "supporting_laps": supporting_laps,
            "suggestions": suggestions,
        }
    )


def _looks_like_smalltalk_reply(text: str) -> bool:
    lowered = text.lower()
    return any(token in lowered for token in ("hello", "hi ", "hey", "glad", "can help", "i can"))


def _looks_like_compare_clarification(text: str) -> bool:
    lowered = text.lower()
    return "which laps" in lowered or "tell me which" in lowered or "start with lap" in lowered


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
        suggestions=[
            f"What changed on lap {lap_b}?",
            "What does the battery trend look like?",
            "Why did one of these laps stand out?",
        ],
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
        suggestions=_default_suggestions(session),
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
            suggestions=_default_suggestions(session),
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
        suggestions=_default_suggestions(session),
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
        suggestions=_default_suggestions(session),
    )


def _live_supporting_laps(payload: Mapping[str, Any]) -> list[int]:
    laps: list[int] = []
    latest_snapshot = payload.get("latest_snapshot")
    if isinstance(latest_snapshot, Mapping) and isinstance(latest_snapshot.get("lap"), int):
        laps.append(latest_snapshot["lap"])
    for lap in payload.get("completed_laps", []):
        lap_number = lap.get("lap")
        if isinstance(lap_number, int) and lap_number not in laps:
            laps.append(lap_number)
    return laps[:5]


def _top_live_insight(
    payload: Mapping[str, Any],
    *,
    sector: int | None = None,
) -> Mapping[str, Any] | None:
    for insight in payload.get("insights", []):
        if sector is not None and insight.get("sector") not in (sector, None):
            continue
        return insight
    return None


def _compare_live_laps_deterministic(
    request_context: Mapping[str, Any] | None,
    lap_a: int,
    lap_b: int,
) -> CopilotAnswer | None:
    first = _live_lap_by_number(request_context, lap_a)
    second = _live_lap_by_number(request_context, lap_b)
    if first is None or second is None:
        return None
    return CopilotAnswer(
        answer=(
            f"Live telemetry shows lap {lap_b} ran {float(second['lap_time_s']) - float(first['lap_time_s']):+.2f}s "
            f"against lap {lap_a} and changed net energy by "
            f"{((float(second['deploy_mj']) - float(second['harvest_mj'])) - (float(first['deploy_mj']) - float(first['harvest_mj']))):+.2f} MJ. "
            f"Lap {lap_a} ended at {float(first['soc_end']) * 100:.0f}% SoC while lap {lap_b} ended at {float(second['soc_end']) * 100:.0f}%."
        ),
        engine="deterministic",
        supporting_laps=[lap_a, lap_b],
        confidence="medium",
        suggestions=["What changed this lap?", "Are we under battery pressure now?", "What does the latest insight recommend?"],
    )


def _live_battery_summary_deterministic(payload: Mapping[str, Any]) -> CopilotAnswer:
    latest_snapshot = payload.get("latest_snapshot")
    latest_lap = payload.get("completed_laps", [])[-1] if payload.get("completed_laps") else None
    battery_insight = _top_live_insight(payload)
    if isinstance(latest_snapshot, Mapping):
        answer = (
            f"Live battery reserve is tracking around {float(latest_snapshot['soc_estimate']) * 100:.0f}% on lap {int(latest_snapshot['lap'])}. "
            f"The current lap is at {float(latest_snapshot['deploy_mj']):.2f} MJ deploy versus {float(latest_snapshot['harvest_mj']):.2f} MJ harvest so far."
        )
        if isinstance(latest_lap, Mapping):
            answer += (
                f" The latest closed lap finished at {float(latest_lap['soc_end']) * 100:.0f}% SoC "
                f"with {float(latest_lap['deploy_mj']):.2f} MJ deploy and {float(latest_lap['harvest_mj']):.2f} MJ harvest."
            )
        if isinstance(battery_insight, Mapping) and isinstance(battery_insight.get("recommended_action"), str):
            answer += f" {battery_insight['recommended_action']}"
        return CopilotAnswer(
            answer=answer,
            engine="deterministic",
            supporting_laps=_live_supporting_laps(payload),
            confidence="medium",
            suggestions=["What changed this lap?", "Why did the latest insight fire?", "What does sector 3 look like right now?"],
        )
    return CopilotAnswer(
        answer="Live battery context is not available yet because OVERRIDE is still waiting for the first telemetry snapshot.",
        engine="deterministic",
        supporting_laps=[],
        confidence="low",
        suggestions=["Try again after the first telemetry snapshot", "What race state are we in right now?"],
    )


def _live_sector_deterministic(payload: Mapping[str, Any], sector: int) -> CopilotAnswer:
    latest_snapshot = payload.get("latest_snapshot")
    insight = _top_live_insight(payload, sector=sector)
    if isinstance(insight, Mapping):
        return CopilotAnswer(
            answer=(
                f"Sector {sector} is drawing live attention because {str(insight.get('message', '')).strip()} "
                f"{str(insight.get('recommended_action', '')).strip()}".strip()
            ),
            engine="deterministic",
            supporting_laps=_live_supporting_laps(payload),
            confidence=str(insight.get("confidence", "medium")),
            suggestions=["Are we under battery pressure now?", "What changed this lap?", "Why did OVERRIDE surface that insight?"],
        )
    if isinstance(latest_snapshot, Mapping):
        current_sector = latest_snapshot.get("sector")
        answer = (
            f"OVERRIDE has not raised a sector-specific live insight for sector {sector} yet. "
            f"The car is currently in sector {current_sector if current_sector is not None else 'unknown'} on lap {int(latest_snapshot['lap'])}."
        )
        return CopilotAnswer(
            answer=answer,
            engine="deterministic",
            supporting_laps=_live_supporting_laps(payload),
            confidence="low",
            suggestions=["What changed this lap?", "Are we under battery pressure now?"],
        )
    return CopilotAnswer(
        answer=f"Sector {sector} cannot be analyzed yet because the live telemetry stream has not produced a usable snapshot.",
        engine="deterministic",
        supporting_laps=[],
        confidence="low",
        suggestions=["Try again once the race is live", "What race state are we in right now?"],
    )


def _live_race_status_deterministic(payload: Mapping[str, Any]) -> CopilotAnswer:
    race_state = payload.get("race_state")
    latest_snapshot = payload.get("latest_snapshot")
    if race_state in {"stopping", "cleanup", "ended"}:
        return CopilotAnswer(
            answer=(
                "The race is no longer in an active drive phase. "
                f"OVERRIDE currently reports the state as {race_state}, so the stop sequence or debrief handoff is in progress."
            ),
            engine="deterministic",
            supporting_laps=_live_supporting_laps(payload),
            confidence="high",
            suggestions=["Summarize the latest live insight", "What did the battery trend look like before the stop?"],
        )
    if isinstance(latest_snapshot, Mapping):
        return CopilotAnswer(
            answer=(
                f"The race is still live in state {race_state or 'active'}. "
                f"OVERRIDE is tracking lap {int(latest_snapshot['lap'])}, sector {latest_snapshot.get('sector') or 'unknown'}, "
                f"at {float(latest_snapshot['speed_kmh']):.0f} km/h."
            ),
            engine="deterministic",
            supporting_laps=_live_supporting_laps(payload),
            confidence="medium",
            suggestions=["Are we under battery pressure now?", "What changed this lap?", "What does the latest insight recommend?"],
        )
    return CopilotAnswer(
        answer="OVERRIDE knows the race context is live, but the first telemetry snapshot has not arrived yet.",
        engine="deterministic",
        supporting_laps=[],
        confidence="low",
        suggestions=["Try again after the first telemetry snapshot", "What race state are we in right now?"],
    )


def _live_general_deterministic(payload: Mapping[str, Any]) -> CopilotAnswer:
    latest_snapshot = payload.get("latest_snapshot")
    top_insight = _top_live_insight(payload)
    if isinstance(latest_snapshot, Mapping):
        answer = (
            f"OVERRIDE is tracking lap {int(latest_snapshot['lap'])} live, with the car in sector {latest_snapshot.get('sector') or 'unknown'} "
            f"at {float(latest_snapshot['speed_kmh']):.0f} km/h and battery reserve near {float(latest_snapshot['soc_estimate']) * 100:.0f}%."
        )
        if isinstance(top_insight, Mapping):
            answer += f" The latest live insight says: {str(top_insight.get('headline', '')).strip()}."
        return CopilotAnswer(
            answer=answer,
            engine="deterministic",
            supporting_laps=_live_supporting_laps(payload),
            confidence="medium",
            suggestions=["Are we under battery pressure now?", "What changed this lap?", "Why did OVERRIDE surface that insight?"],
        )
    return CopilotAnswer(
        answer="The live race context is attached, but OVERRIDE is still waiting for enough telemetry to summarize the current run.",
        engine="deterministic",
        supporting_laps=[],
        confidence="low",
        suggestions=["Try again once the race is live", "What race state are we in right now?"],
    )


def _smalltalk_deterministic(
    session: Session,
    request_context: Mapping[str, Any] | None = None,
) -> CopilotAnswer:
    live_payload = _live_context_payload(request_context)
    if live_payload is not None:
        latest_snapshot = live_payload.get("latest_snapshot")
        lap_context = (
            f" We are currently on lap {int(latest_snapshot['lap'])}."
            if isinstance(latest_snapshot, Mapping) and isinstance(latest_snapshot.get("lap"), int)
            else ""
        )
        return CopilotAnswer(
            answer=(
                "Hello — I’m grounded in the live race state, so I can explain the latest insight, compare recent laps, or summarize the battery trend."
                f"{lap_context}"
            ),
            engine="deterministic",
            supporting_laps=_live_supporting_laps(live_payload),
            confidence="medium",
            suggestions=_default_suggestions(session, request_context),
        )
    return CopilotAnswer(
        answer="Hello — I’m grounded in this session, so I can explain the recommendation, compare specific laps, or summarize the battery trend.",
        engine="deterministic",
        supporting_laps=[],
        confidence="medium",
        suggestions=_default_suggestions(session, request_context),
    )


def _compare_clarification_deterministic(
    session: Session,
    request_context: Mapping[str, Any] | None = None,
) -> CopilotAnswer:
    compare_pair = _specific_compare_pair(session, request_context)
    if compare_pair is not None:
        return CopilotAnswer(
            answer=f"Sure — tell me which laps you want to compare, or start with lap {compare_pair[0]} and lap {compare_pair[1]}.",
            engine="deterministic",
            supporting_laps=list(compare_pair),
            confidence="medium",
            suggestions=_default_suggestions(session, request_context),
        )
    return CopilotAnswer(
        answer="Sure — tell me which two laps you want to compare and I’ll break down the pace, energy, and SoC differences.",
        engine="deterministic",
        supporting_laps=[],
        confidence="medium",
        suggestions=_default_suggestions(session, request_context),
    )


def _deterministic_live_answer(
    question: str,
    request_context: Mapping[str, Any],
) -> CopilotAnswer | None:
    payload = _live_context_payload(request_context)
    if payload is None:
        return None
    normalized = question.strip()
    lowered = normalized.lower()
    compare = _COMPARE_RE.search(normalized)
    if compare:
        comparison = _compare_live_laps_deterministic(
            request_context,
            int(compare.group(1)),
            int(compare.group(2)),
        )
        if comparison is not None:
            return comparison
    sector_match = _SECTOR_RE.search(normalized)
    if sector_match is not None:
        return _live_sector_deterministic(payload, int(sector_match.group(1)))
    if "battery" in lowered or "energy" in lowered:
        return _live_battery_summary_deterministic(payload)
    if "stop" in lowered or "state" in lowered:
        return _live_race_status_deterministic(payload)
    return _live_general_deterministic(payload)


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
            suggestions=_default_suggestions(session),
        )
    return CopilotAnswer(
        answer=f"{preface}this session is best explored by comparing laps or asking about the battery trend, because no zone recommendation was generated.",
        engine="deterministic",
        supporting_laps=[],
        confidence="low",
        suggestions=_default_suggestions(session),
    )


def _deterministic_answer(
    session: Session,
    question: str,
    recent_turns: Sequence[CopilotMessage],
    request_context: Mapping[str, Any] | None = None,
) -> CopilotAnswer:
    normalized = question.strip()
    lowered = normalized.lower()
    if _is_greeting(normalized) or _is_acknowledgement(normalized):
        return _smalltalk_deterministic(session, request_context)
    if _wants_lap_comparison_but_unspecified(normalized):
        return _compare_clarification_deterministic(session, request_context)
    if request_context is not None:
        live_answer = _deterministic_live_answer(question, request_context)
        if live_answer is not None:
            return live_answer
    compare = _COMPARE_RE.search(normalized)
    if compare:
        return _compare_laps_deterministic(session, int(compare.group(1)), int(compare.group(2)))

    if "why" in lowered and (
        "recommend" in lowered
        or "strategy" in lowered
        or "conservative" in lowered
    ):
        return _explain_strategy_deterministic(session)

    sector_match = _SECTOR_RE.search(normalized)
    if sector_match is not None:
        return _analyze_sector_deterministic(session, int(sector_match.group(1)))

    if "battery" in lowered or "energy" in lowered:
        return _battery_summary_deterministic(session)

    return _fallback_summary_deterministic(session, recent_turns)


def answer_question(
    session: Session,
    question: str,
    *,
    recent_turns: Sequence[CopilotMessage] | None = None,
    client: WatsonxChatClient | None = None,
    request_context: Mapping[str, Any] | None = None,
) -> CopilotAnswer:
    recent_turns = recent_turns or []
    fallback = _deterministic_answer(session, question, recent_turns, request_context)
    normalized_question = question.strip()
    compare = _COMPARE_RE.search(question.strip())
    if compare and _compare_context(session, int(compare.group(1)), int(compare.group(2))) is None and _compare_live_context(request_context, int(compare.group(1)), int(compare.group(2))) is None:
        return fallback
    if client is None:
        return fallback

    system = _load_system_prompt()
    user = render_user_message(session, question, recent_turns, request_context)
    raw = client.chat(system=system, user=user, temperature=0.2, max_tokens=768)
    try:
        parsed = parse_copilot_response(raw)
    except CopilotParseError:
        salvaged = _salvage_unstructured_answer(raw, session, fallback, request_context)
        if salvaged is not None:
            if _is_greeting(normalized_question) and not _looks_like_smalltalk_reply(salvaged.answer):
                return fallback
            if _wants_lap_comparison_but_unspecified(normalized_question) and not _looks_like_compare_clarification(salvaged.answer):
                return fallback
            logger.info("Granite copilot returned prose; salvaging as Granite-backed answer")
            return salvaged
        logger.warning("Granite copilot response fell back to deterministic mode", exc_info=True)
        return fallback
    normalized = _normalize_model_answer(parsed, session, fallback, request_context)
    if _is_greeting(normalized_question) and not _looks_like_smalltalk_reply(normalized.answer):
        return fallback
    if _wants_lap_comparison_but_unspecified(normalized_question) and not _looks_like_compare_clarification(normalized.answer):
        return fallback
    return normalized


__all__ = [
    "CopilotParseError",
    "answer_question",
    "parse_copilot_response",
    "render_user_message",
]
