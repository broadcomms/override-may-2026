# P1.5 — Inefficient-Zone Patterns

> Design specification for the four inefficient-zone heuristics implemented in `analysis/zone_detector.py` (P2.1). This is the **versioned, auditable** record of *what* each heuristic detects and *why* — separate from the code that implements it. Per `.bob/rules.md`, this plan file is deleted in the same PR that ships P2.1.

---

## Why heuristics first, then AI

OVERRIDE's pipeline is heuristic baseline → AI explanation → safety pass. Granite reasons over the heuristics; it does **not** replace them. If every model fails (no watsonx, no TTM, no Guardian), the deterministic detector still produces useful zones. This is the "decision support, never replacement" guardrail in code form.

The four `ZoneType` values (`low-roi-deploy`, `late-recharge`, `over-harvest`, `unused-override`) are locked in `docs/04-schema.md` §4 and `ingest/schema.py`. This document specifies the **detection logic** that maps `LapFeatures` rows to those zone types.

## What we have to work with

Inputs to the detector (per `04-schema.md` §3):

```
LapFeatures: lap_number, soc_start, soc_end, harvest_mj, deploy_mj,
             lap_time, sector1_time, sector2_time, sector3_time,
             avg_speed, max_speed, override_uses, boost_uses,
             recharge_zones, soc_source
```

Plus the session-level `soc_max` from `LapWindow.soc_max` (battery capacity MJ).

**Caveat — FastF1-derived data.** Pre-2026 historical data has no native MGU-K telemetry. `ingest/fastf1_parser.py` derives `harvest_mj` / `deploy_mj` / `soc_*` from throttle/brake integrals (with `soc_source="derived"`), and emits **`override_uses=0`** and **`boost_uses=0`** for every row (those are 2026-only concepts). This means heuristics that depend on `override_uses` or `boost_uses` will exhibit different statistics on FastF1 vs TORCS. Heuristics below are written so they remain *meaningful* on TORCS truth, *plausible* on FastF1-derived data, and *honest* about their limits.

## Per-lap feature engineering (precomputed in `analysis/feature_engineering.py`)

Before zone detection runs, each `LapFeatures` row gets enriched with:

| Derived field | Formula | Used by |
|---|---|---|
| `time_gain_s` | `median(lap_time over session) - lap_time` (positive when faster than median) | `low-roi-deploy` |
| `roi_mj_per_s` | `deploy_mj / max(time_gain_s, 0.01)` (MJ per second of advantage; high = wasteful) | `low-roi-deploy` |
| `headroom_mj_start` | `(1.0 - soc_start) * soc_max` (how much room the battery had at lap start) | `late-recharge` (harvested-when-full) |
| `cap_mj` | per-lap harvest cap from regulation (8.5 MJ default; tunable via env or `LapWindow.soc_max`-derived) | `over-harvest` |
| `harvest_ratio` | `harvest_mj / cap_mj` (fraction of cap consumed) | `over-harvest` |
| `available_override_mj` | `soc_start * soc_max` (energy notionally available for boost) | `unused-override` |

These are computed once per session and cached on enriched lap records. Zone detection iterates over enriched rows and emits `Zone` objects.

---

## Pattern 1 — `low-roi-deploy`

**What it captures.** Battery deployed in laps where the time benefit was negligible — energy spent for very little gain. The 2026 rules' premise is that battery is the new strategic axis; spending it where it doesn't pay off costs you on the laps where it would.

**Detection (fires when ALL true):**
```
deploy_mj > 0.20 MJ                  # non-trivial deploy happened
AND time_gain_s < 0.10 s             # this lap was within ~0.1s of the session median
AND roi_mj_per_s > 1.0               # > 1 MJ spent per second of advantage
```

The `roi_mj_per_s > 1.0` floor avoids firing on laps that genuinely deployed energy productively (a fast lap with `deploy_mj=0.5` and `time_gain=1.0s` gives roi=0.5 — efficient, no fire).

**Severity thresholds** (by `roi_mj_per_s`):
- **low**: 1.0 ≤ roi < 3.0 (modest waste)
- **medium**: 3.0 ≤ roi < 10.0
- **high**: roi ≥ 10.0 (very wasteful — many MJ for ~0s gain)

**Sector assignment.** Use the slowest sector vs. the lap's median sector time as a proxy for *where* the deploy was spent inefficiently. (We can't pinpoint exactly without per-corner telemetry, which TORCS will eventually give us; the sector resolution is honest about that.)

**Required `metrics` keys** (per `04-schema.md` §4):
- `deploy_mj`
- `time_gain_s`
- `roi_mj_per_s`

**Description string template** (deterministic, no LLM):
> *"Lap {N}: deployed {deploy_mj:.2f} MJ for {time_gain_s:+.2f} s of advantage (ROI {roi_mj_per_s:.1f} MJ/s)."*

---

## Pattern 2 — `late-recharge`

**What it captures.** Harvest activity on a lap where the battery had little room left to absorb it — energy discarded as heat instead of recovered usefully. Or: a lap with very low harvest when the battery is near-empty (a missed window). The first variant is what fires on most data; the second requires lap-to-lap context that's harder to localize.

**Detection (variant 1 — harvested-when-full, fires when ALL true):**
```
soc_start > 0.85                     # battery was near-full at lap start
AND harvest_mj > 0.30 MJ             # but we still pulled meaningful harvest
AND headroom_mj_start < 0.6 MJ       # very little capacity to absorb it
```

**Detection (variant 2 — missed-harvest-window, fires when ALL true):**
```
soc_start < 0.30                     # battery was depleted at lap start
AND harvest_mj < 0.10 MJ             # but we harvested almost nothing
AND len(recharge_zones) == 0         # no sector saw meaningful regen
```

Both variants emit `zone_type=late-recharge`. The `description` distinguishes which variant fired.

**Severity thresholds** (by `headroom_mj_start` for variant 1, by `soc_start` for variant 2):
- Variant 1:
  - **low**: 0.4 ≤ headroom < 0.6 MJ
  - **medium**: 0.2 ≤ headroom < 0.4 MJ
  - **high**: headroom < 0.2 MJ
- Variant 2:
  - **low**: 0.20 ≤ soc_start < 0.30
  - **medium**: 0.10 ≤ soc_start < 0.20
  - **high**: soc_start < 0.10

**Sector assignment.** Variant 1 → first sector with non-zero harvest in `recharge_zones` (the harvest started when full; that's where it happened). Variant 2 → sector with longest brake-time but no harvest (would need the brake-time-per-sector signal, which we have in `LapInputs` for FastF1 but not in `LapFeatures` directly). For v1 we **default to sector 1** for variant 2 with a code comment; refined when we add per-sector brake telemetry to LapFeatures (post-G-2 with TORCS).

**Required `metrics` keys**:
- `harvest_mj`
- `lap_time_cost_s` — proxy: `time_gain_s` flipped sign (slower laps tend to over-harvest)
- `available_window_s` — proxy: count of `recharge_zones` × 8.0 s (8s/sector heuristic)

**Description string templates:**
> Variant 1: *"Lap {N}: harvested {harvest_mj:.2f} MJ when battery was {soc_start*100:.0f}% full ({headroom_mj_start:.2f} MJ headroom)."*
> Variant 2: *"Lap {N}: only {harvest_mj:.2f} MJ harvested with battery at {soc_start*100:.0f}% — recharge window underused."*

---

## Pattern 3 — `over-harvest`

**What it captures.** Lap harvest approaches or hits the regulation cap when the battery is already near full — energy that *had* to be dumped because you were already at capacity AND at the regulatory ceiling. Different from `late-recharge` in that this one is about hitting the *cap* (regulation-bounded), not just the battery's *capacity* (physics-bounded).

**Detection (fires when ALL true):**
```
harvest_ratio > 0.85                 # within 15% of the per-lap cap
AND soc_end > 0.90                   # battery was near-full when lap ended
```

The conjunction matters: harvesting at the cap *while battery is depleted* is correct behavior (you needed it). Harvesting at the cap *while battery is full* is the inefficiency this pattern catches.

**Severity thresholds** (by `harvest_ratio`):
- **low**: 0.85 ≤ ratio < 0.95
- **medium**: 0.95 ≤ ratio < 1.00
- **high**: ratio ≥ 1.00 (at or above cap)

**Sector assignment.** Use the sector index in `recharge_zones` with the largest harvest contribution; default to last entry in `recharge_zones` if tie.

**Required `metrics` keys**:
- `harvest_mj`
- `cap_mj`
- `headroom_mj` — `cap_mj - harvest_mj` (how much more harvest was *legally* possible)

**Description string template:**
> *"Lap {N}: harvested {harvest_mj:.2f} MJ ({harvest_ratio*100:.0f}% of {cap_mj:.1f} MJ cap) with battery {soc_end*100:.0f}% full at lap end."*

---

## Pattern 4 — `unused-override`

**What it captures.** A lap where Override Mode (the 2026 DRS replacement, available within ~1 s of a leading car) could plausibly have been triggered for an attack but wasn't, AND the battery had energy to spend. Most useful on real 2026 race data; on FastF1 historical data this pattern reads as *"never used boost despite available energy"*.

**Detection (fires when ALL true):**
```
override_uses == 0
AND boost_uses == 0
AND soc_start > 0.70                 # had meaningful energy to spend
AND deploy_mj < 0.10 MJ              # almost nothing was deployed this lap
```

The `deploy_mj < 0.10` floor distinguishes "had energy and used it inefficiently elsewhere" (caught by `low-roi-deploy`) from "had energy and didn't use it at all" (this pattern). Over-conservative laps are the target.

**FastF1-data caveat.** This heuristic is **expected to fire frequently on FastF1 sessions** because every row has `override_uses=0` and `boost_uses=0`. That over-firing is *intentional* in v1 — it surfaces "didn't deploy meaningfully" laps for downstream reasoning, even when the original 2014–2025 data didn't have a boost concept. Calibrate to TORCS truth post-G-2.

**Severity thresholds** (by `available_override_mj`):
- **low**: 2.8 ≤ available < 3.2 MJ (= soc_start ≥ 0.70 with soc_max ≈ 4.0)
- **medium**: 3.2 ≤ available < 3.6 MJ (= soc_start ≥ 0.80)
- **high**: available ≥ 3.6 MJ (= soc_start ≥ 0.90 — fully charged, never deployed)

**Sector assignment.** Default to the sector with the highest `avg_speed` proxy (we don't have per-sector speed in `LapFeatures`, so we default to **sector 2** — the typical longest-straight sector at most circuits). Comment in code; refined when LapFeatures gains per-sector speed.

**Required `metrics` keys**:
- `gap_to_leader_s` — **0.0 placeholder** for v1 (FastF1 doesn't expose; TORCS may)
- `available_override_mj`
- `straight_length_m` — **0.0 placeholder** for v1 (would require track metadata)

**Description string template:**
> *"Lap {N}: {available_override_mj:.2f} MJ available, {deploy_mj:.2f} MJ deployed — boost window unused."*

---

## Calibration notes

**Default thresholds above are educated guesses**, not measured. They will be re-tuned in two passes:

1. **Post-FastF1 sweep (after P2.1 lands).** Run the detector against 3 FastF1 sessions (Monza/Silverstone/Monaco — varying degrees of energy-strategic tracks). If a pattern fires on 0% of laps or > 60% of laps, the threshold is wrong; adjust until firing rate is in the 5–25% sensible range.
2. **Post-TORCS sweep (after G-2).** Re-tune against TORCS truth where `soc_source="measured"`. The TORCS run is where we calibrate `cap_mj` to the regulation value pinned at G-4.

Threshold values in this doc are the **starting point**, not the final answer. Code references this doc; tuning happens by editing both together.

---

## What this doc does NOT specify

- **Which corner** within a sector triggered an inefficient deploy. We don't have per-corner data in `LapFeatures` v1; the `Zone.sector` field is the resolution we ship. ADR-002-candidate (per-`zone_type` discriminated unions) might add per-corner detail later.
- **Cross-lap reasoning.** "Forecast indicates SoC headroom narrows by L25" is a Granite-reasoning concern, not a heuristic concern. The detector is per-lap; reasoning ties laps together.
- **Severity for the `unused-override` pattern on TORCS-truth data.** When real `override_uses` exist, the threshold logic flips (we'd compare *missed* opportunities against *taken* ones). v1 ships the FastF1-friendly logic above; v2 lands at G-2.

## Status

- [x] Four patterns specified with heuristics and severity thresholds
- [x] Required `metrics` keys mapped to each pattern (matches `04-schema.md` §4)
- [x] FastF1-data caveats surfaced honestly (especially `unused-override`)
- [x] Calibration plan documented (post-FastF1 sweep + post-TORCS sweep)
- [ ] Implemented in `analysis/zone_detector.py` (P2.1 — next step)
- [ ] Validated against FastF1 fixtures (P2.1 tests)
- [ ] Re-calibrated against TORCS truth (post-G-2)

This file is **deleted in the same PR that ships P2.1's `analysis/zone_detector.py`**. The heuristic spec then lives in code comments + the test fixtures.
