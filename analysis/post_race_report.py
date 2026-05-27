"""Deterministic post-race report and lap-analysis builders."""

from __future__ import annotations

from datetime import datetime, timezone
from statistics import mean, pstdev

from ingest.schema import LapAnalysis, LiveInsight, RaceReport, Recommendation, Session, Severity


def _clamp_score(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 1)


def _severity_weight(severity: Severity) -> int:
    return {"high": 3, "medium": 2, "low": 1}[severity]


def _recommendation_confidence(rec: Recommendation) -> str:
    guardian = rec.guardian
    if isinstance(guardian, dict):
        value = guardian.get("final_confidence")
        return value if isinstance(value, str) else rec.reasoning.confidence
    value = getattr(guardian, "final_confidence", None)
    return value if isinstance(value, str) else rec.reasoning.confidence


def _recommendation_key_moment(rec: Recommendation) -> LiveInsight:
    return LiveInsight(
        insight_id=f"li_report_{rec.zone.zone_id}",
        rule_id=f"report_{rec.zone.zone_type.value}",
        kind="explanation",
        severity=rec.zone.severity,
        headline=rec.reasoning.recommendation,
        message=(
            f"Lap {rec.zone.lap_number}, sector {rec.zone.sector}: "
            f"{rec.reasoning.cause} {rec.reasoning.consequence}"
        ),
        recommended_action=rec.reasoning.recommendation,
        confidence=_recommendation_confidence(rec),
        evidence=rec.reasoning.reasoning_chain[:3],
        lap=rec.zone.lap_number,
        sector=rec.zone.sector,
    )


def build_race_report(session: Session) -> RaceReport:
    laps = session.laps
    generated_at = datetime.now(timezone.utc)
    if not laps:
        return RaceReport(
            session_id=session.summary.session_id,
            title="Race report pending telemetry",
            executive_summary="No completed laps are available yet, so OVERRIDE is waiting for a finished session before scoring the run.",
            driver_score=0.0,
            battery_efficiency_score=0.0,
            consistency_score=0.0,
            risk_score=0.0,
            key_moments=[],
            ai_commentary=["Complete the race ingest to unlock the post-race report."],
            generated_at=generated_at,
        )

    lap_times = [lap.lap_time for lap in laps]
    avg_lap_time = mean(lap_times)
    lap_time_spread = pstdev(lap_times) if len(lap_times) > 1 else 0.0
    consistency_ratio = (lap_time_spread / avg_lap_time) if avg_lap_time > 0 else 0.0
    consistency_score = _clamp_score(100.0 - consistency_ratio * 1200.0)

    avg_abs_net_energy = mean(abs(lap.harvest_mj - lap.deploy_mj) for lap in laps)
    final_soc = laps[-1].soc_end
    battery_efficiency_score = _clamp_score(
        100.0 - avg_abs_net_energy * 65.0 - max(0.0, 0.45 - final_soc) * 140.0
    )

    risk_pressure = sum(_severity_weight(rec.zone.severity) for rec in session.recommendations)
    risk_score = _clamp_score(
        risk_pressure * 10.0 + max(0.0, 0.40 - final_soc) * 180.0
    )
    driver_score = _clamp_score(
        0.4 * consistency_score + 0.4 * battery_efficiency_score + 0.2 * (100.0 - risk_score)
    )

    best_lap = min(laps, key=lambda lap: lap.lap_time)
    worst_lap = max(laps, key=lambda lap: lap.lap_time)
    top_recommendations = sorted(
        session.recommendations,
        key=lambda rec: (
            _severity_weight(rec.zone.severity),
            rec.zone.lap_number,
        ),
        reverse=True,
    )[:3]
    key_moments = [_recommendation_key_moment(rec) for rec in top_recommendations]
    if not key_moments:
        key_moments.append(
            LiveInsight(
                insight_id=f"li_report_bestlap_l{best_lap.lap_number}_s0",
                rule_id="report_best_lap",
                kind="explanation",
                severity="low",
                headline=f"Lap {best_lap.lap_number} set the session benchmark",
                message=(
                    f"Best lap was {best_lap.lap_time:.2f}s versus {worst_lap.lap_time:.2f}s "
                    f"for the slowest lap."
                ),
                recommended_action="Use the dedicated lap route to inspect the pace delta against the slowest lap.",
                confidence="medium",
                evidence=[
                    f"Best lap average speed: {best_lap.avg_speed:.1f} km/h.",
                    f"Final SoC: {final_soc * 100:.0f}%.",
                ],
                lap=best_lap.lap_number,
                sector=None,
            )
        )

    zone_count = len(session.recommendations)
    executive_summary = (
        f"OVERRIDE reviewed {len(laps)} laps, highlighted {zone_count} zone"
        f"{'' if zone_count == 1 else 's'}, and graded consistency at {consistency_score:.1f}/100."
    )
    ai_commentary = [
        f"Best lap: {best_lap.lap_number} at {best_lap.lap_time:.2f}s; slowest lap: {worst_lap.lap_number} at {worst_lap.lap_time:.2f}s.",
        f"Battery efficiency closed at {battery_efficiency_score:.1f}/100 with final SoC at {final_soc * 100:.0f}%.",
        f"Driver score landed at {driver_score:.1f}/100 after balancing consistency, energy use, and risk pressure.",
    ]

    return RaceReport(
        session_id=session.summary.session_id,
        title=f"Race report · {session.summary.track_name or session.summary.track_id or 'session'}",
        executive_summary=executive_summary,
        driver_score=driver_score,
        battery_efficiency_score=battery_efficiency_score,
        consistency_score=consistency_score,
        risk_score=risk_score,
        key_moments=key_moments,
        ai_commentary=ai_commentary,
        generated_at=generated_at,
    )


def build_lap_analysis(session: Session, lap_number: int) -> LapAnalysis:
    lap = next((item for item in session.laps if item.lap_number == lap_number), None)
    if lap is None:
        raise ValueError(f"Lap {lap_number} not found in session {session.summary.session_id}.")

    related_recs = [rec for rec in session.recommendations if rec.zone.lap_number == lap_number]
    net_energy = lap.harvest_mj - lap.deploy_mj
    if related_recs:
        headline = related_recs[0].reasoning.recommendation
    elif net_energy <= -0.25:
        headline = f"Lap {lap_number} spent more energy than it recovered"
    elif net_energy >= 0.25:
        headline = f"Lap {lap_number} rebuilt battery reserve"
    else:
        headline = f"Lap {lap_number} held a balanced energy window"

    slowest_sector_idx = max(
        [(1, lap.sector1_time), (2, lap.sector2_time), (3, lap.sector3_time)],
        key=lambda item: item[1],
    )[0]
    sector_callouts = [
        f"Sector {slowest_sector_idx} was the slowest split on the lap.",
    ]
    if lap.recharge_zones:
        sector_callouts.append(
            "Recharge activity appeared in sector "
            + ", ".join(str(sector) for sector in lap.recharge_zones)
            + "."
        )

    evidence = [
        f"SoC moved from {lap.soc_start * 100:.0f}% to {lap.soc_end * 100:.0f}%.",
        f"Harvest was {lap.harvest_mj:.2f} MJ versus {lap.deploy_mj:.2f} MJ deploy.",
        f"Lap time was {lap.lap_time:.2f}s with {lap.avg_speed:.1f} km/h average speed.",
    ]
    if lap.override_uses or lap.boost_uses:
        evidence.append(
            f"Overtake Mode uses: {lap.override_uses}; boost windows: {lap.boost_uses}."
        )
    for rec in related_recs[:2]:
        evidence.extend(rec.reasoning.reasoning_chain[:2])

    summary = (
        f"Lap {lap_number} finished in {lap.lap_time:.2f}s, closed at {lap.soc_end * 100:.0f}% SoC, "
        f"and ran a net energy delta of {net_energy:+.2f} MJ."
    )

    return LapAnalysis(
        session_id=session.summary.session_id,
        lap_number=lap_number,
        headline=headline,
        summary=summary,
        sector_callouts=sector_callouts,
        evidence=evidence,
        generated_at=datetime.now(timezone.utc),
    )


__all__ = ["build_lap_analysis", "build_race_report"]
