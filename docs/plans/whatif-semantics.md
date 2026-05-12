# What-if perturbation semantics — FR-8 spec

> **Plan-file lifecycle:** this doc gets deleted in the same PR that ships FR-8
> end-to-end (per `.bob/rules.md`). It exists to pin three edge-case decisions
> before any code lands, so the schema, the perturbation functions, the cache
> key, and the UI diff renderer all agree on what each perturbation MEANS.

## Why this doc

FR-8 (per `docs/03-prd.md` §5.8) names three perturbations but doesn't fully
specify their behavior at the boundary cases. Without pinning the answers
*before* writing code, the schema, the pure perturbation functions in
`analysis/perturbations.py`, the endpoint, and the UI diff renderer will each
make implicit choices that drift. The v6 plan made 2.1 BLOCK 2.2 for exactly
this reason.

The three perturbations operate on `list[LapFeatures]` (the canonical session
shape) and return a new list. Pure functions, no pipeline coupling — the
endpoint composes them with `run_pipeline()` per gotcha #4.

## Common conventions

- **Energy conservation.** Where a perturbation "moves" deploy/harvest energy
  in time, the total session-level harvest+deploy is preserved (delta in one
  lap balanced by reverse delta in the receiving lap). Where energy is "lost"
  (a harvest opportunity skipped, a deploy zeroed out), the SoC trajectory
  reflects the loss — the validator's `harvest_cap` rule and the
  zone-detector's downstream patterns see the realistic consequence.
- **SoC trajectory recompute.** After any perturbation that modifies
  `harvest_mj` or `deploy_mj` on a lap, `soc_end` on that lap AND all
  downstream laps must recompute via `soc_end[N] = clamp(soc_end[N-1] +
  (harvest[N] - deploy[N]) / BATTERY_CAPACITY_MJ, 0, 1)`. The
  `derive_lap_energy` helper in `analysis/torcs_energy.py` does this for
  individual laps; the perturbation function chains it across the whole list.
- **Lap_number stays canonical.** A perturbation does not renumber laps.
  `delay_first_deploy(2)` does not insert a "phantom lap 0" or shift indices.
  Reading the perturbed list, you can still match perturbed-lap-3 ↔
  original-lap-3 by `lap_number`.

## Perturbation 1 — `delay_first_deploy(n: int)`

**Intent.** "What if the driver had held the battery instead of deploying on
the first deploy lap?" Models the strategic choice to save energy for later in
the race.

**Definition.** Find the first lap where `deploy_mj > DEPLOY_MIN_THRESHOLD_MJ`
(0.05 MJ — eliminates pure-cruise laps with near-zero deploys). Call it lap K.
For each lap in `[K, K+n-1]`, set `deploy_mj = 0.0`. For each downstream lap,
recompute `soc_end` via the cumulative trajectory; recompute `harvest_mj` only
if a per-lap cap was previously hit (the "deferred energy" goes into the
battery, which may saturate at SoC=1.0 and force harvest down).

**Edge cases pinned:**
| Condition | Behavior |
|---|---|
| Lap K is lap 1 AND first deploy is on lap 1 | **Shifts the deploy budget** to lap 1+n. The deploy_mj zeroed in lap 1; the same MJ added to lap 1+n if that lap exists, else energy is conserved by leaving SoC higher. Not skipped. |
| `n` > remaining-laps-after-K | Deploy zeroed through end of session; energy fully retained as SoC headroom. Validator's `over-harvest` pattern may fire next lap if SoC saturates. |
| Lap K doesn't exist (no lap above threshold) | `WhatIfRequest` validation rejects this case at the endpoint boundary; UI shows "no deploy events to delay in this session" tooltip and disables the radio. |
| `n == 0` | Identity transform. Returns input unchanged. Accepted by the schema for testing parity. |

**Why "shift" not "skip" when K=1:** the framing "delay" implies temporal
movement, not deletion. Skipping would change the SUM of session-level deploy
energy, which contradicts "delay." Test fixture asserts
`sum(deploy_mj_before) == sum(deploy_mj_after)` for the n=1, K=1 case
(modulo SoC saturation losses).

## Perturbation 2 — `skip_harvest_zone(zone_id: str)`

**Intent.** "What if the driver had missed this harvest opportunity?" Models
a strategic mistake or unavoidable racing-line conflict where regeneration
wasn't possible.

**Definition.** Locate the lap whose `zone_id` matches (zones are deterministic
per `analysis/zone_detector` so the mapping is stable). Zero out the
`harvest_mj` value for that lap. Per-sector harvest_per_sector also zeroed if
present in the future LapFeatures shape (currently aggregate only).
Recompute downstream `soc_end` trajectory.

**Edge cases pinned:**
| Condition | Behavior |
|---|---|
| Energy fate | **LOST, not deferred.** The harvest opportunity is gone; the battery is lower for the remainder of the session. Models a real racing mistake, not a deferred regeneration. |
| `zone_id` doesn't exist in the session | Endpoint returns 404 "zone not found in this session". |
| Multiple zones share the same lap_number | Each `zone_id` is unique within a session (per `analysis/zone_detector` invariant). Test fixture asserts uniqueness. |
| SoC underflow | `clamp(soc_end, 0, 1)` covers it — SoC floors at 0; downstream laps with `deploy_mj > 0` but `soc_start = 0` may show inconsistent behavior. The validator's `energy_bounds` rule catches this and the recommendation card shows the engineer "battery exhausted" tooltip. Expected. |

**Why "lost" not "deferred":** the perturbation answers "what if you'd missed
this opportunity?" The honest answer is the battery is permanently lower. A
"deferred to next lap" variant would model "what if you'd recharged later
instead?" which is a different question — not in FR-8 scope, v1.1 candidate.

## Perturbation 3 — `extend_override(zone_id: str, extra_laps: int = 1)`

**Intent.** "What if the driver had extended the Override Mode boost through
one more lap?" Models the strategic choice to spend extra battery for a
sustained attack.

**Definition.** Locate the zone (must be of type `unused-override` or
`low-roi-deploy` — validation enforces). For each of `extra_laps` consecutive
laps after the zone's lap_number, add `OVERRIDE_DEPLOY_MJ_PER_LAP = 0.5 MJ` to
`deploy_mj`. Increment `override_uses` by 1 on the seed lap. Recompute
downstream SoC.

**Edge cases pinned:**
| Condition | Behavior |
|---|---|
| Default `extra_laps` | **1 lap.** Single-lap extension models the typical strategic decision; multi-lap is a power-user dial. |
| Extension extends past end of session | Extra laps beyond the last lap are silently truncated. UI shows "extends N laps, M applied (session ended)" footnote in the diff. |
| SoC underflow before all extensions applied | Each lap's extension is capped at `min(0.5, soc_start * BATTERY_CAPACITY_MJ)`. If battery is empty, deploy is zero, and the diff shows "battery exhausted on lap X — extension truncated." Honest. |
| Override already at high use-count | No cap. The FIA regulation in C5.18 doesn't limit count per session in the public text; let the validator's `harvest_cap` rule catch out-of-budget consequences downstream. |

**Why 0.5 MJ default:** matches the documented Override Mode boost magnitude
in the 2026 regs (~50% boost over the deployment-already-in-flight, applied
for ~10 seconds = ~0.5 MJ over a single lap at typical deploy rates).

## `WhatIfRequest` schema (Pydantic, frozen)

```python
from typing import Literal
from pydantic import BaseModel, Field

class WhatIfRequest(BaseModel):
    model_config = {"frozen": True}

    perturbation: Literal["delay_first_deploy", "skip_harvest_zone", "extend_override"]
    # Validator: required when perturbation in {"skip_harvest_zone", "extend_override"};
    # ignored when "delay_first_deploy" (uses `n` instead).
    zone_id: str | None = Field(default=None, pattern=r"^z_[A-Za-z0-9_]+$")
    # Validator: required when perturbation == "delay_first_deploy"; ignored otherwise.
    n: int | None = Field(default=None, ge=1, le=10)
    # Validator: optional for "extend_override"; defaults to 1.
    extra_laps: int | None = Field(default=1, ge=1, le=5)
```

Schema-level validators enforce the per-perturbation required-field set.

## Cache key spec (per v6 gotcha #4)

```python
import hashlib

def whatif_cache_key(req: WhatIfRequest) -> str:
    return hashlib.sha256(req.model_dump_json().encode()).hexdigest()[:16]
```

Deterministic across runs. Filename-safe (16 hex chars). The pydantic
`model_dump_json` produces a stable string for frozen models with sorted keys
(Pydantic v2 default behavior). Disk cache location:
`data/sessions/{session_id}/whatif/{cache_key}.json`.

## What the UI diff renders

Two `Recommendation` cards side-by-side per zone, "Before" (original) on the
left, "After" (perturbed) on the right. Highlighted deltas:
- `harvest_mj`, `deploy_mj`, `soc_end` with arrow → and color coding
  (green=lower deploy / lower harvest; red=higher; gray=unchanged)
- Validator and Guardian badges for both states (the perturbation may flip
  pass→fail or vice versa — that's the explainability beat)
- The reasoning chain in the "After" card highlights any step that newly
  references the perturbation ("After the delayed deploy, the battery
  retained 0.42 MJ of headroom into lap 4...")

NO animation between states. Per UI doc §4.3 — clear "Before / After"
labeling beats motion. The fan toggle is the only animated control in this
UI; consistency matters.

## Non-goals (deferred to v1.1)

- Compound perturbations (combining two at once). v1 accepts one `WhatIfRequest`
  per call; chaining via multiple sequential calls is the v1 escape hatch.
- "Restore lost harvest to a different lap" variant of skip_harvest_zone (the
  "deferred" energy fate). Different perturbation conceptually; v1.1 if asked.
- Per-sector targeting (current Perturbation 2 zeros the whole lap's harvest;
  sector-precision would need richer LapFeatures shape).
- UI undo/redo for what-if history. Each request creates a cached entry;
  user can fire repeated requests but no in-UI history stack.
