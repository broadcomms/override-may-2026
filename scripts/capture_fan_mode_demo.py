"""Capture a clean Session JSON with populated `fan` for UI dev (P3.4).

Runs the full orchestrator on a synthetic 5-lap session, then translates
each recommendation into Fan Mode and stitches the result back onto the
Recommendation. Persists the complete Session shape — exactly what the
API would return for `GET /api/sessions/{id}` after a `?mode=both` call
on every zone.

Used by `ui/src/api/client.ts` as the default fixture for fixture-mode
dev. Burns ~one full pipeline + N fan-translation calls = ~$0.05 on
Essentials per R18 estimate.

Run:
    .venv/bin/python scripts/capture_fan_mode_demo.py
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

import sys

sys.path.insert(0, str(ROOT))

from core.fan_mode import translate_to_fan_mode  # noqa: E402
from core.guardian import WatsonxAIGuardianClient  # noqa: E402
from core.pipeline import run_pipeline  # noqa: E402
from core.reasoning import WatsonxAIChatClient  # noqa: E402
from core.regs import WatsonxAIEmbeddingClient  # noqa: E402
from ingest.schema import LapFeatures, Recommendation  # noqa: E402


# A clean 5-lap session that fires one or more zones reliably.
# Lap 3 has heavy deploy with no time gain → low-roi-deploy.
LAPS = [
    LapFeatures(lap_number=1, soc_start=0.85, soc_end=0.78, harvest_mj=0.4, deploy_mj=0.3,
                lap_time=85.4, sector1_time=27.0, sector2_time=29.5, sector3_time=28.9,
                avg_speed=210.0, max_speed=320.0, override_uses=1, boost_uses=0,
                recharge_zones=[2], soc_source="derived"),
    LapFeatures(lap_number=2, soc_start=0.78, soc_end=0.72, harvest_mj=0.3, deploy_mj=0.4,
                lap_time=85.4, sector1_time=27.0, sector2_time=29.5, sector3_time=28.9,
                avg_speed=210.0, max_speed=320.0, override_uses=1, boost_uses=0,
                recharge_zones=[2], soc_source="derived"),
    LapFeatures(lap_number=3, soc_start=0.72, soc_end=0.55, harvest_mj=0.2, deploy_mj=0.7,
                lap_time=85.4, sector1_time=27.0, sector2_time=30.5, sector3_time=27.9,
                avg_speed=205.0, max_speed=315.0, override_uses=1, boost_uses=0,
                recharge_zones=[1], soc_source="derived"),
    LapFeatures(lap_number=4, soc_start=0.55, soc_end=0.48, harvest_mj=0.4, deploy_mj=0.5,
                lap_time=85.4, sector1_time=27.0, sector2_time=29.5, sector3_time=28.9,
                avg_speed=210.0, max_speed=320.0, override_uses=1, boost_uses=0,
                recharge_zones=[2], soc_source="derived"),
    LapFeatures(lap_number=5, soc_start=0.48, soc_end=0.40, harvest_mj=0.3, deploy_mj=0.4,
                lap_time=85.4, sector1_time=27.0, sector2_time=29.5, sector3_time=28.9,
                avg_speed=210.0, max_speed=320.0, override_uses=1, boost_uses=0,
                recharge_zones=[2], soc_source="derived"),
]


async def main() -> int:
    chat = WatsonxAIChatClient()
    embed = WatsonxAIEmbeddingClient()
    guard = WatsonxAIGuardianClient()

    print("=== capturing clean Session via run_pipeline …")
    t0 = time.time()
    session = await run_pipeline(
        laps=LAPS,
        soc_max=4.0,
        chat_client=chat,
        embedding_client=embed,
        guardian_client=guard,
        source="fastf1",
        track_id="monza",
        session_id="s_fan_mode_demo",
    )
    pipeline_s = time.time() - t0
    print(f"    pipeline ran in {pipeline_s:.1f}s · {len(session.recommendations)} zones")

    print("=== translating each recommendation to Fan Mode …")
    augmented: list[Recommendation] = []
    for r in session.recommendations:
        try:
            t0 = time.time()
            fan = await asyncio.to_thread(translate_to_fan_mode, r.reasoning, client=chat)
            print(f"    fan(zone={r.zone.zone_id}) {time.time()-t0:.1f}s — {fan.headline}")
            augmented.append(r.model_copy(update={"fan": fan}))
        except Exception as e:
            print(f"    fan(zone={r.zone.zone_id}) FAILED: {type(e).__name__}: {e}")
            augmented.append(r)  # keep without fan

    final = session.model_copy(update={"recommendations": augmented})

    out = ROOT / "tests" / "fixtures" / "fan_mode_demo.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "fixture_id": "fan_mode_demo",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "captured_via": "scripts/capture_fan_mode_demo.py — full pipeline + Fan Mode per zone",
        "purpose": (
            "Clean Session with populated `fan: FanOutput` for every Recommendation. "
            "Used by ui/src/api/client.ts as the default fixture so the UI can render "
            "Engineer ↔ Fan toggle without any watsonx round-trip during dev."
        ),
        "session": final.model_dump(mode="json"),
    }
    out.write_text(json.dumps(payload, indent=2))
    print(f"\n✓ wrote {out}")
    print(f"  {len(augmented)} recommendations, "
          f"{sum(1 for r in augmented if r.fan)} with fan populated")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
