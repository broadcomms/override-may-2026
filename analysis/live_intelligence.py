"""Deterministic live-intelligence rules for the cockpit SSE stream.

The live path stays heuristic and low-latency by design: no Granite calls, no
Guardian pass, and no transport-model imports. The API stream passes in
LiveLapSnapshot / LiveLapStats instances, but this module only depends on the
attributes it needs via Protocols so it remains reusable by later report/lap
artifacts without an api.main import cycle.
"""

from __future__ import annotations

from typing import Literal, Optional, Protocol, Sequence

from ingest.schema import Confidence, LiveInsight, Severity


class SupportsLiveLapStats(Protocol):
    lap: int
    lap_time_s: float
    avg_speed_kmh: float
    max_speed_kmh: float
    harvest_mj: float
    deploy_mj: float
    soc_end: float
    fuel_used_kg: float | None


class SupportsLiveLapSnapshot(Protocol):
    lap: int
    speed_kmh: float
    avg_speed_kmh: float
    harvest_mj: float
    deploy_mj: float
    soc_estimate: float
    sector: int | None
    balance_label: Literal["spending", "recovering", "balanced"]


def _insight_id(rule_id: str, lap: Optional[int], sector: Optional[int]) -> str:
    return f"li_{rule_id}_l{lap or 0}_s{sector or 0}"


def _confidence_for_severity(severity: Severity) -> Confidence:
    return "high" if severity == "high" else "medium" if severity == "medium" else "low"


def _severity_rank(severity: Severity) -> int:
    return {"high": 3, "medium": 2, "low": 1}[severity]


def _kind_rank(kind: str) -> int:
    return {
        "anomaly": 4,
        "prediction": 3,
        "strategy_recommendation": 2,
        "explanation": 1,
    }.get(kind, 0)


def _strategy_mode(snapshot: SupportsLiveLapSnapshot | None, laps: Sequence[SupportsLiveLapStats]) -> tuple[str, str]:
    latest = laps[-1] if laps else None
    soc = snapshot.soc_estimate if snapshot is not None else latest.soc_end if latest is not None else 0.6
    if soc <= 0.35:
        return "conserve", "Battery reserve is narrow enough to support a conservative deployment mode."
    if latest is not None and latest.deploy_mj - latest.harvest_mj >= 0.45:
        return "recover", "Recent laps spent more energy than they recovered, so a recovery phase is supported."
    if snapshot is not None and snapshot.balance_label == "recovering" and soc >= 0.72:
        return "push", "Energy balance is recovering with reserve in hand, which supports a higher-value push window."
    return "balanced", "Energy use is close enough to balanced that the current deployment mode can stay steady."


def _strategy_insight(
    snapshot: SupportsLiveLapSnapshot | None,
    laps: Sequence[SupportsLiveLapStats],
) -> Optional[LiveInsight]:
    latest = laps[-1] if laps else None
    lap = snapshot.lap if snapshot is not None else latest.lap if latest is not None else None
    sector = snapshot.sector if snapshot is not None else None
    if lap is None:
        return None

    mode, rationale = _strategy_mode(snapshot, laps)
    soc = snapshot.soc_estimate if snapshot is not None else latest.soc_end if latest is not None else 0.0
    net = None
    if latest is not None:
        net = latest.harvest_mj - latest.deploy_mj
    elif snapshot is not None:
        net = snapshot.harvest_mj - snapshot.deploy_mj

    evidence = [f"SoC estimate is {soc * 100:.0f}%."]
    if net is not None:
        sign = "+" if net >= 0 else ""
        evidence.append(f"Net energy trend is {sign}{net:.2f} MJ.")
    if latest is not None:
        evidence.append(f"Latest completed lap closed at {latest.avg_speed_kmh:.1f} km/h average speed.")

    return LiveInsight(
        insight_id=_insight_id("strategy_mode_v1", lap, sector),
        rule_id="strategy_mode_v1",
        kind="strategy_recommendation",
        severity="medium" if mode in {"recover", "conserve"} else "low",
        headline=f"{mode.capitalize()} mode supported",
        message=rationale,
        recommended_action=(
            "Recommend trimming deploy until the battery trend stabilizes."
            if mode in {"recover", "conserve"}
            else "Recommend holding the current deployment pattern while telemetry stays balanced."
            if mode == "balanced"
            else "Recommend saving the stronger deploy window for the next high-value straight."
        ),
        confidence="medium",
        evidence=evidence,
        lap=lap,
        sector=sector if sector in {1, 2, 3} else None,
    )


def _energy_pressure_insight(
    snapshot: SupportsLiveLapSnapshot | None,
    laps: Sequence[SupportsLiveLapStats],
) -> Optional[LiveInsight]:
    latest = laps[-1] if laps else None
    if latest is None:
        return None

    deploy_gap = latest.deploy_mj - latest.harvest_mj
    if deploy_gap < 0.4 and not (
        snapshot is not None
        and snapshot.deploy_mj - snapshot.harvest_mj >= 0.35
        and snapshot.soc_estimate <= 0.72
    ):
        return None

    soc = snapshot.soc_estimate if snapshot is not None else latest.soc_end
    severity: Severity = "high" if soc <= 0.45 or deploy_gap >= 0.7 else "medium"
    sector = snapshot.sector if snapshot is not None else None
    return LiveInsight(
        insight_id=_insight_id("energy_pressure_v1", latest.lap, sector),
        rule_id="energy_pressure_v1",
        kind="strategy_recommendation",
        severity=severity,
        headline="Energy pressure building",
        message=(
            f"Deploy exceeded harvest by {deploy_gap:.2f} MJ on lap {latest.lap}, "
            f"and battery reserve is trending tighter."
        ),
        recommended_action="Recommend a recover lap before repeating the same deployment pattern.",
        confidence=_confidence_for_severity(severity),
        evidence=[
            f"Lap {latest.lap} closed with {latest.deploy_mj:.2f} MJ deploy vs {latest.harvest_mj:.2f} MJ harvest.",
            f"SoC is tracking around {soc * 100:.0f}%.",
        ],
        lap=latest.lap,
        sector=sector if sector in {1, 2, 3} else None,
    )


def _battery_prediction_insight(laps: Sequence[SupportsLiveLapStats]) -> Optional[LiveInsight]:
    if len(laps) < 2:
        return None

    recent = list(laps[-3:])
    deltas = [recent[i - 1].soc_end - recent[i].soc_end for i in range(1, len(recent))]
    avg_drop = sum(deltas) / len(deltas)
    latest = recent[-1]
    if avg_drop < 0.04:
        return None

    laps_to_threshold = max(1, int(round((latest.soc_end - 0.35) / avg_drop))) if latest.soc_end > 0.35 else 1
    projected_lap = latest.lap + max(1, laps_to_threshold)
    severity: Severity = "high" if latest.soc_end <= 0.45 or avg_drop >= 0.08 else "medium"
    return LiveInsight(
        insight_id=_insight_id("battery_prediction_v1", latest.lap, None),
        rule_id="battery_prediction_v1",
        kind="prediction",
        severity=severity,
        headline="Battery reserve trending down",
        message=(
            f"Recent SoC slope would bring the reserve near 35% around lap {projected_lap} "
            "if the same energy pattern continues."
        ),
        recommended_action="Recommend conservative deployment until the reserve trend flattens.",
        confidence=_confidence_for_severity(severity),
        evidence=[
            f"Recent SoC drops average {avg_drop * 100:.1f}% per lap.",
            f"Latest completed lap ended at {latest.soc_end * 100:.0f}% SoC.",
        ],
        lap=latest.lap,
        sector=None,
    )


def _pace_anomaly_insight(
    snapshot: SupportsLiveLapSnapshot | None,
    laps: Sequence[SupportsLiveLapStats],
) -> Optional[LiveInsight]:
    if len(laps) < 2:
        return None

    latest = laps[-1]
    previous = laps[-2]
    lap_delta = latest.lap_time_s - previous.lap_time_s
    speed_delta = previous.avg_speed_kmh - latest.avg_speed_kmh
    if lap_delta < 1.2 and speed_delta < 6.0:
        return None

    severity: Severity = "high" if lap_delta >= 2.5 or speed_delta >= 10.0 else "medium"
    sector = snapshot.sector if snapshot is not None else None
    sector_note = f" Sector {sector} is the current focus." if sector in {1, 2, 3} else ""
    return LiveInsight(
        insight_id=_insight_id("pace_drop_v1", latest.lap, sector),
        rule_id="pace_drop_v1",
        kind="anomaly",
        severity=severity,
        headline="Pace drop detected",
        message=(
            f"Lap {latest.lap} lost {lap_delta:.2f}s versus lap {previous.lap} while average speed fell "
            f"by {speed_delta:.1f} km/h.{sector_note}"
        ),
        recommended_action="Recommend checking the current sector for stability before increasing deploy again.",
        confidence=_confidence_for_severity(severity),
        evidence=[
            f"Lap {previous.lap}: {previous.lap_time_s:.2f}s at {previous.avg_speed_kmh:.1f} km/h average.",
            f"Lap {latest.lap}: {latest.lap_time_s:.2f}s at {latest.avg_speed_kmh:.1f} km/h average.",
        ],
        lap=latest.lap,
        sector=sector if sector in {1, 2, 3} else None,
    )


def derive_live_insights(
    snapshot: SupportsLiveLapSnapshot | None,
    completed_laps: Sequence[SupportsLiveLapStats],
) -> list[LiveInsight]:
    """Return the current deterministic live insights sorted by urgency."""

    insights: list[LiveInsight] = []

    for candidate in (
        _energy_pressure_insight(snapshot, completed_laps),
        _battery_prediction_insight(completed_laps),
        _pace_anomaly_insight(snapshot, completed_laps),
        _strategy_insight(snapshot, completed_laps),
    ):
        if candidate is not None:
            insights.append(candidate)

    insights.sort(
        key=lambda insight: (
            _severity_rank(insight.severity),
            _kind_rank(insight.kind),
            insight.lap or 0,
            insight.sector or 0,
        ),
        reverse=True,
    )
    return insights


__all__ = ["derive_live_insights"]
