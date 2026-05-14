# What-if perturbation semantics (FR-8)

> **Status:** retroactive — restored 2026-05-14. The doc was originally written
> before `analysis/perturbations.py` was implemented (per v6 plan task 2.1,
> "blocking 2.2"), then deleted prematurely. `analysis/perturbations.py` and
> `ingest/schema.py` reference its sections by name; this restoration captures
> the semantics that actually shipped, verified against the code.
>
> **Lifecycle (per `.bob/rules.md`):** delete this file in the PR that ships
> FR-8 end-to-end — which is the submission PR, since FR-8 ships as part of
> the v1.0 surface. Until that PR, the doc stays because the code's
> `Per whatif-semantics.md §...` comments are load-bearing references.
>
> **Authority:** if this doc and `analysis/perturbations.py` disagree, the
> code is the source of truth and this doc has drifted. Open an issue and
> reconcile in the same commit.

---

## What FR-8 actually is

POST `/api/sessions/{session_id}/what-if` accepts a `WhatIfRequest`, applies
one of three pure perturbations to the session's lap list, re-runs the
existing pipeline (`core.pipeline.run_pipeline`) against the perturbed laps,
and returns a `WhatIfResult` with side-by-side original-vs-perturbed
recommendations.

The endpoint composes — it does not fork — `run_pipeline`. Perturbations
mutate `list[LapFeatures]` and nothing else. Zone detection, reasoning,
validator, and Guardian all re-run unchanged against the perturbed input.

This pure-function discipline matters because:

1. The decisions a perturbation surfaces have to be **trustworthy in the
   same way** the unperturbed pipeline is — same validator, same Guardian,
   same two-pass safety. A forked pipeline would mean a second code path
   to audit at submission.
2. The cache key is `sha256(WhatIfRequest.model_dump_json())[:16]` — that
   only hashes deterministically if perturbation logic is referentially
   transparent. Side-effecting code breaks the cache.

---

## Perturbation 1 — `delay_first_deploy`

**Intent.** Answer "what would the race look like if the team had saved
energy for n laps before deploying?" — a classic strategic question the
2026 hybrid era surfaces continuously.

**Semantics — the energy MOVES, it is not deleted.**

1. Find the first lap `K` where `deploy_mj >= DEPLOY_MIN_THRESHOLD_MJ`
   (0.05 MJ, ~1 second of full throttle — eliminates pure-cruise blips).
2. Zero `deploy_mj` on lap K.
3. Add the original lap-K deploy onto lap K+n's existing `deploy_mj`.
4. Re-derive SoC trajectory across the entire session via
   `_recompute_soc_trajectory`.

**Edge cases:**

| Condition | Behavior | Returned `note` |
|---|---|---|
| `n <= 0` | Identity (return input unchanged) | `None` |
| No lap has `deploy_mj >= 0.05` | Return input unchanged | `"no deploy events to delay in this session"` |
| `K + n` is past the session's last lap | Energy retained as SoC headroom (no destination lap) | `"deploy of X.XX MJ delayed past end of session (K=..., n=...); energy retained as SoC headroom"` |
| Target lap's resulting `deploy_mj` exceeds per-lap physical cap | Returned anyway; validator's `energy_bounds` rule flags it in Pass 1 | `None` (the validator note carries the signal) |

**Why energy moves rather than disappears.** The realistic strategic
alternative is "deploy later," not "skip deploy." A driver who delays
ERS-K activation still uses the same battery budget; the question is
when. Modeling this as conservation keeps the perturbation honest.

**Constraint envelope.** `n` is bounded `[1, 10]` by the Pydantic schema.
The lower bound rules out the no-op; the upper bound prevents callers
from constructing nonsensical perturbations (a 10-lap delay on a 50-lap
session is the maximum useful range).

---

## Perturbation 2 — `skip_harvest_zone`

**Intent.** Answer "what if the driver missed this regen window?" — the
single most common real-world race mistake the FIA hybrid energy regime
surfaces. Models a real mistake, not a strategic choice.

**Semantics — the energy is LOST, not deferred.**

1. Find the lap matching the target zone's `lap_number` (the endpoint
   builds a `zone_id → lap_number` lookup from the original session's
   recommendations and passes it in as `zone_lap_lookup`).
2. Zero `harvest_mj` on that lap. Clear `recharge_zones` on that lap
   (per-lap derived elsewhere; keeping it consistent matters for
   downstream rendering).
3. Re-derive SoC trajectory across the rest of the session — every
   downstream lap floors lower than it would have.

**Edge cases:**

| Condition | Behavior | Returned `note` |
|---|---|---|
| `zone_id` resolves to a lap not in `laps` | Return input unchanged | `"zone 'z_...': lap N not found"` |
| Target lap already has `harvest_mj == 0` | Return input unchanged | `"zone 'z_...': lap N already has 0 harvest — no-op"` |
| Happy path | Harvest zeroed; SoC trajectory falls | `"zone 'z_...': harvest of X.XX MJ on lap N LOST (skipped opportunity, energy not deferred)"` |

**Why LOST, not deferred.** A missed harvest window in F1 is gone — the
braking event already happened. Modeling it as "the energy reappears on
the next braking zone" would be physically incorrect and would mute the
strategic teaching signal: missed regen has lasting consequences for
the rest of the session.

The downstream SoC floor (`SOC_MIN = 0.0`) means very late-session skip
events can push subsequent deploys into clamp territory. That clamp is
visible to the reasoning model and the validator's energy-bounds rule;
the UI shows the resulting recommendation diff honestly.

---

## Perturbation 3 — `extend_override`

**Intent.** Answer "what if the driver activated Override Mode on this
zone — or extended an existing activation?" — Override Mode (the 2026
"push-to-pass" equivalent) is a discrete strategic choice with a fixed
energy cost, modeled here as +0.5 MJ/lap of additional deploy.

**Semantics.**

1. Find the seed lap matching the target zone's `lap_number`.
2. Increment `override_uses` on the seed lap by 1 (tracked separately
   from `deploy_mj` because the validator's
   `override_uses_in_budget` rule depends on it).
3. For each of `extra_laps` (default 1, range `[1, 5]`) AFTER the seed:
   a. Check available SoC budget on that lap:
      `soc_budget_mj = soc_start * BATTERY_CAPACITY_MJ`
   b. Subtract the lap's existing `deploy_mj`. If the remainder is
      `<= 0`, truncate honestly — no further extensions land.
   c. Otherwise, add `min(OVERRIDE_DEPLOY_MJ_PER_LAP, remaining)`
      onto that lap's `deploy_mj`. Partial extensions are allowed
      (e.g. a lap with 0.3 MJ available gets +0.3 MJ, not the full
      0.5 MJ).
4. Re-derive SoC trajectory.

**Why 0.5 MJ/lap.** Approximates Override Mode's documented magnitude
under the 2026 regulations (~50% over the in-flight deploy rate × 10
seconds). The exact number is a calibration target; if regs analysis
or telemetry capture refines it, change `OVERRIDE_DEPLOY_MJ_PER_LAP`
in `analysis/perturbations.py` and update this paragraph in the same
commit.

**Edge cases:**

| Condition | Behavior | Returned `note` |
|---|---|---|
| `zone_id` resolves to a lap not in `laps` | Return input unchanged | `"zone 'z_...': lap N not found"` |
| Extension would run past the session's last lap | Truncate at the last lap | `"zone 'z_...': extension applied to K of M requested laps (session ended)"` |
| Battery exhausts mid-extension | Truncate at the depleted lap | `"zone 'z_...': battery exhausted on lap N — extension truncated after K of M laps"` |
| All `extra_laps` apply but `applied < extra_laps` (defensive branch) | Apply what landed | `"zone 'z_...': applied K of M extensions"` |

**Why honest truncation rather than silent over-deploy.** The 2026 regs
hard-cap per-lap deploy. Letting `extend_override` push past the cap
would produce recommendations that look real but couldn't legally happen.
Truncation + a clear `note` makes the constraint visible to the reasoning
model and to the UI.

---

## Schema-hashable `WhatIfRequest` payload for caching

`WhatIfRequest` is `frozen=True` so `model_dump_json()` is deterministic
(field order, default handling, no datetime drift). The cache key is:

```python
cache_key = hashlib.sha256(request.model_dump_json().encode()).hexdigest()[:16]
```

Stable across runs, deterministic, filename-safe. Cache lives at
`data/sessions/{session_id}/whatif/{cache_key}.json`. Cache hit: the
endpoint skips perturbation + pipeline re-run entirely and returns the
cached `WhatIfResult`. Cache miss: compute, persist, return.

**Why 16 hex chars.** 64-bit collision space — vastly larger than the
~100-perturbation cap a single session would realistically generate.
Truncating from 64 hex chars keeps the filename short.

**The `WhatIfResult.cache_key` field is asserted equal to the request
hash** at endpoint exit (Pydantic validator on `WhatIfResult.cache_key`
checks the 16-hex-char regex). If the two ever diverge, the cache is
corrupt; the endpoint logs and recomputes.

---

## What the UI diff renders

`WhatIfResult.original: list[Recommendation]` and
`WhatIfResult.perturbed: list[Recommendation]` are paired side-by-side
by `Recommendation.zone.zone_id`:

- **Same zone in both lists** → `WhatIfDiff` renders "Before / After"
  cards with metric deltas (red ↓ green ↑ on harvest_mj, deploy_mj,
  soc_end). This is the dominant case.
- **Zone in `original` only** → the perturbation made the zone go away.
  The UI shows the "Before" card with a "resolved by this perturbation"
  banner.
- **Zone in `perturbed` only** → the perturbation surfaced a NEW zone
  (e.g. an extend_override that triggered a late-session SoC underflow
  zone the unperturbed run didn't have). Labeled "newly detected" rather
  than "before/after" — there's no Before to diff against.

`WhatIfResult.note` carries the truncation / no-op / honest-truncation
message from the perturbation function. The UI renders it inline above
the diff cards as a warning banner. Never silent.

---

## Why the doc deletes in the submission PR, not now

`analysis/perturbations.py` has nine `Per whatif-semantics.md §...`
references; `ingest/schema.py` `WhatIfRequest` and `WhatIfResult` have
two more. Until those code references go away — which would require an
inline-rationale refactor — the doc is load-bearing for code-reading
clarity. The FR-8 submission PR is the natural moment to either inline
the rationales or delete the doc; until then it stays.
