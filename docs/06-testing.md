# Testing

OVERRIDE's quality gate is `pytest` on the Python side and `tsc --noEmit && vite build` on the UI side. No CI in v1 (deferred to v1.1); these are walked locally before tagging `v1.0.0-submission` per [`docs/plans/final-lock-checklist.md`](./plans/final-lock-checklist.md).

## Counts (current state)

```
pytest -q -m "not network"   # 340 unit tests, ~10 s, no external calls
pytest -q -m "network"       #   4 network-marked integration tests (live watsonx; ~30 s)
                             # ─────────────────────────
                             # 344 total green
```

Baseline at v6-plan start was 231 unit tests. The increase came from FR-8 (perturbations + endpoint), live-ingest endpoint + status helper, TORCS parser + calibration regression, hybrid LLM client (Ollama Protocol impl), concurrency fix for fan-mode saves, regulation-retrieval front-matter filtering, assorted edge-case coverage shipped during Weeks 1–3, and Phase 1 session-boundary work (11 new tests covering `_extract_start_time`, the `/torcs-status` enrichment, `/torcs-live` metadata embedding, `GET /api/sessions` pagination + backward compat).

## Test layout

| Path | Concern | Test count (approx) |
|---|---|---|
| `tests/test_torcs_parser.py` | TORCS JSONL → `LapFeatures`, **incl. calibration regression test** | 20+ |
| `tests/test_fastf1_parser.py` | FastF1 parquet → `LapFeatures` | 15+ |
| `tests/test_pipeline.py` | End-to-end orchestration, regulation-source scope filtering | 25+ |
| `tests/test_api.py` | All FastAPI endpoints, concurrency, fixture mode, Phase 1 session boundaries + history pagination, Phase 2 control-plane proxy (httpx MockTransport), Phase 3 SSE helpers + stream | 60+ |
| `tests/test_perturbations.py` | FR-8 three perturbation functions (golden tests) | 15+ |
| `tests/test_zone_detector.py` | `analysis/zone_detector.py` zone classification heuristics | 20+ |
| `tests/test_regs.py` | Docling chunk extraction, retrieval, front-matter filter | 25+ |
| `tests/test_validator.py` | Pass-1 deterministic validator rules | 30+ |
| `tests/test_guardian.py` | Pass-2 Granite Guardian BYOC scoring | 15+ |
| `tests/test_reasoning.py` | Granite chat client + retry-with-stricter-prompt | 20+ |
| `tests/test_fan_mode.py` | Engineer → Fan translation | 10+ |
| `tests/test_storage.py` | Atomic-write helpers, session persistence | 15+ |
| `tests/test_llm_clients_ollama.py` | `OllamaChatClient` Protocol impl, response-shape normalization, fail-loud probe | 10+ |
| `tests/test_observability.py` | OTel instrumentation hooks | 9 |
| `tests/test_*.py` (network) | Live watsonx end-to-end smoke (chat + guardian + embedding) | 4 |

## The calibration regression test (load-bearing)

`tests/test_torcs_parser.py::test_torcs_baseline_energy_calibration` locks the TORCS energy-derivation constants. It asserts that the canonical baseline capture produces per-lap harvest/deploy in the 3–7 MJ median range with no value violating the 8.5 MJ regulatory cap. This test fires the moment anyone retunes `HARVEST_KJ_PER_BRAKE_SECOND` or `DEPLOY_KJ_PER_FULL_THROTTLE_SECOND` in `analysis/torcs_energy.py` for the wrong reason — preventing silent calibration drift that would otherwise only surface during the demo when the zone detector misfires.

The test reads `data/samples/torcs_baseline.jsonl` directly; the canonical capture is intentionally tracked at ~7 MB so the regression has stable inputs across machines.

## Running tests

```bash
# Default — fast unit suite, no network
.venv/bin/pytest

# Single file / single test
.venv/bin/pytest tests/test_pipeline.py
.venv/bin/pytest tests/test_pipeline.py::test_pipeline_skips_forecast_when_under_30_laps -xvs

# Include live watsonx integration tests (consumes Essentials-tier budget)
.venv/bin/pytest -m network

# UI quality gate
cd ui && npm run typecheck && npm run build
```

## Why no CI in v1

Three reasons, in order:

1. **Never spec'd.** The original v6 plan didn't include CI; the empty `.github/workflows/ci.yml` placeholder was deleted in Week 3 as misleading.
2. **Single-operator project.** No PR review surface; the human running tests is the same human writing the code.
3. **watsonx budget discipline.** Network-marked tests hit real Essentials-tier endpoints. Running them on every push would burn the CA$10 alert budget within days. The current pattern (run network suite once at T-72h per the final-lock checklist) is cheaper and equally informative.

v1.1 will add a GitHub Actions workflow that runs the non-network suite on every PR + the network suite on a weekly cron with budget-aware retry semantics.

## Test discipline shipped during the build

- **No hardcoded FIA article numbers** anywhere in `tests/`. Per the HARD RULE in `ingest/schema.py:152-157` and `docs/04-schema.md` §6, all article-string references come from the Docling extraction at runtime via the `RegulationSource` struct.
- **Fixture-mode parity** — the UI's `client.ts` fixture path returns the same `Session` Pydantic shape the real API serves. UI tests against fixtures catch shape drift that would otherwise only surface in production.
- **`asyncio.Lock` setdefault pattern** — `tests/test_api.py` fires N=5 concurrent fan-mode requests at the same session and asserts all five fan-mode translations land (closes the v6 plan gotcha #3 TOCTOU race).
- **JSONL safe-read** — `tests/test_torcs_parser.py` includes a fixture with an intentionally-incomplete tail line; the parser must skip it silently rather than raise (closes gotcha #12).

See [`docs/plans/qa-results.md`](./plans/qa-results.md) for the 2026-05-09 audit snapshot (235-test state) — a frozen historical record per the roadmap P3.7 deliverable. Current state (305) is authoritative for submission.
