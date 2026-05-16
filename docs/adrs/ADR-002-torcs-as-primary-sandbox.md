# ADR-002 — TORCS as the primary decision-logic sandbox

- **Status**: Accepted
- **Date**: 2026-05-11

## Context

The OVERRIDE pipeline (ingest → zone detection → reasoning → validator → Guardian → fan-mode) needs telemetry input to operate. Two data sources are in scope:

1. **FastF1** — public historical race data (2014–2025 hybrid era) parsed from the FIA-licensed Formula 1 timing feed. Real lap-times, sector-times, throttle and brake traces. **No native MGU-K / battery / hybrid-energy signals** — pre-2026 cars use a different energy architecture and FastF1 doesn't expose the 2026-spec hybrid state regardless. State-of-charge / harvest / deploy are synthesized in `ingest/fastf1_parser.py` from throttle and brake integrals; `soc_source="derived"` flags the provenance.
2. **TORCS** (The Open Racing Car Simulator) — the simulator IBM's SkillsBuild Learning Lab `01_torcs_lab` ships as the primary AI environment. Open-source, deterministic, gym-style Python wrapper (`RaceYourCode/gym_torcs/`), 36-sensor SCR telemetry over UDP port 3001. Driveable via VNC in the lab container, programmable via the bundled `torcs_jm_par.py` baseline AI driver. **Also no native 2026 hybrid-energy signals** — TORCS models a generic racing car, not a 2026-spec F1 power unit; the abstract docs are explicit that "the SoC / MGU-K / recovery-cap layer must be built in the gym wrapper." Energy state is synthesized identically to the FastF1 path.

Neither source provides ground-truth 2026 hybrid telemetry — that data does not yet exist publicly. The question is which simulator anchors OVERRIDE's demo story.

## Decision

**TORCS is the primary decision-logic sandbox for v1.0.** FastF1 stays as a complementary "real-historical-data" path; both feed the same `LapFeatures` schema via `ingest/torcs_parser.py` and `ingest/fastf1_parser.py` respectively.

Concretely:
- `RaceYourCode/gym_torcs/torcs_jm_par.py` is the lab's baseline AI driver, used here unchanged structurally — only an env-gated 3-line telemetry logger added at `parse_server_str` to emit per-tick JSONL when `OVERRIDE_LOG_TELEMETRY` is set.
- Pre-captured `data/samples/torcs_*.json` replays serve as the canonical demo fixtures; the YouTube submission video plays these via fixture-mode (`?fixture=1`) for determinism.
- The compose stack keeps the TORCS lab container in the `torcs` service (`profiles: [torcs]`) alongside the OVERRIDE service; judges who want to drive live can run `podman-compose up override torcs`, and the `POST /api/sessions/torcs-live` endpoint ingests the JSONL the logger writes to the shared `torcs-telemetry` volume.

## Why TORCS over FastF1 for the primary story

1. **The challenge's foundation lab is TORCS.** IBM SkillsBuild's `hands-on-labs/01_torcs_lab/` is the IBM-published learning environment for the May 2026 AI Builders Challenge. Building OVERRIDE around TORCS keeps the data-source story coherent with the lab's mission ("autonomous AI driver in a simulation environment") and the rubric's "Challenge Fit" axis.
2. **Closed-loop interactivity.** TORCS runs live; judges can drive a TORCS lap and watch the dashboard ingest it via the live path. FastF1 only replays historical sessions — there's no interactive story.
3. **Deterministic and reproducible.** TORCS captures committed as `data/samples/torcs_*.json` are byte-for-byte reproducible. FastF1 sessions depend on the upstream cache and are subject to feed-provider changes.
4. **No licensing fragility.** TORCS is open-source (gym_torcs MIT-licensed, © 2016 Naoto Yoshida; bundled via the IBM SkillsBuild lab distribution). FastF1 wraps Formula 1's official timing feed; redistribution constraints would block shipping historical replays in the demo bundle.

## Why both, not TORCS-only

The graceful-degradation guardrail in `.bob/AGENTS.md` favors having multiple data paths so the pipeline survives single-source failure. FastF1 also brings a "real-historical-data, not synthetic" credibility beat to the explainability story — the same reasoning prompts work over 2024-Monza throttle traces, not just simulator output. Keeping both is cheap (the schemas are identical) and rubric-positive.

## Synthetic 2026 energy model — what we are claiming and not claiming

Both parsers derive `harvest_mj` / `deploy_mj` / `soc_start` / `soc_end` from brake-on-time and throttle-≥-95%-time integrals, scaled by calibrated constants (`HARVEST_KJ_PER_BRAKE_SECOND`, `DEPLOY_KJ_PER_FULL_THROTTLE_SECOND`, `BATTERY_CAPACITY_MJ`). Calibration target: per-lap harvest and deploy land in the 4–7 MJ range under the 8.5 MJ FIA cap; SoC stays in [0, 1]; `tests/test_torcs_parser.py::test_torcs_baseline_energy_calibration` locks the regression.

**We are claiming:** the system *demonstrates decision logic* (which corners produce low ROI, where Override would have been better-spent, where the harvest cap was approached) on a synthetic energy model that is internally consistent and respects the 2026 regulation's hard limits.

**We are not claiming:** the synthetic SoC trajectory matches what real 2026 F1 telemetry would produce, lap-for-lap or value-for-value. This would require either licensed team data or rFactor 2-style production-grade vehicle dynamics — both out of scope per the v1 non-goals in `docs/05-security.md` and `docs/03-prd.md` §1.

The `soc_source="derived"` field on every `LapFeatures` row carries the provenance forward; the UI surfaces it on the energy curve when explaining a reasoning step.

## Consequences

- **Lab integration is now a first-class repo concern.** `RaceYourCode/gym_torcs/*` is committed (MIT attribution in README Acknowledgements) and mounted into the `torcs` compose service. The lab's container image stays unmodified; the OVERRIDE compose only adds an entrypoint script (`scripts/torcs_container_init.sh`) that absorbs two known image bugs (Ollama directory ownership, VS Code extension install hang).
- **Calibration is a regression-tested invariant.** The synthetic energy constants are pinned by `tests/test_torcs_parser.py::test_torcs_baseline_energy_calibration`. Anyone tweaking them for the wrong reason (e.g., to satisfy a single noisy lap) will trip the test.
- **FastF1 stays available** for sessions that benefit from a real historical context. ADR-001's runtime split (watsonx for Granite, local for Docling) is unchanged.
- **Live-trackside / production race-control claims are explicitly disclaimed** in the README "What this is not" section and reinforced by ADR-002 here.

## References

- `.bob/AGENTS.md` — graceful-degradation guardrail; "strategy exploration not optimal predictor"
- `docs/00-abstract-b-torcs-study.md` — IBM TORCS Learning Lab context for the May 2026 challenge
- `docs/03-prd.md` §5.1 (FR-1.2) — ingest contract and `soc_source` provenance
- `docs/adrs/ADR-001-watsonx-runtime.md` — Granite serving runtime split
- Sutton, R. S., & Barto, A. G. (2018). *Reinforcement Learning: An Introduction* (2nd ed.), §1.7 — early-precedent argument that high-fidelity simulators are valid environments for *proving decision logic*, distinct from production-grade physical fidelity claims. TORCS plays the analogous role here: a sandbox for demonstrating the explainable-reasoning architecture, not a production race-control system.
