# Testing

OVERRIDE’s current quality gate is still local-first:

- Python: `pytest`
- Frontend: `tsc -b && vite build`

There is no CI workflow in v1. The repo’s test and build truth lives in the local commands below.

## Current inventory

As of the current repo state:

- `pytest --collect-only -q -s tests` collects **439 tests**
- **4** of those tests are marked `network`
- the remaining **435** are local/offline tests
- `npm --prefix ui run build` succeeds against the current frontend

## Test layout

| File | Focus | Count |
|---|---|---:|
| `tests/test_api.py` | FastAPI surface, live ingest, control plane, SSE, deletes, what-if | 101 |
| `tests/test_forecasting.py` | TTM graceful degradation and shape handling | 12 |
| `tests/test_guardian.py` | Guardian parsing, thresholds, parallel scoring, live smoke | 38 |
| `tests/test_ingest.py` | Shared schema validation and FastF1-derived lap logic | 25 |
| `tests/test_llm_clients_ollama.py` | Ollama protocol adapter and fail-loud probe | 19 |
| `tests/test_observability.py` | OTel helpers and tracing hooks | 9 |
| `tests/test_perturbations.py` | What-if perturbation semantics | 24 |
| `tests/test_pipeline.py` | End-to-end orchestration and retry behavior | 15 |
| `tests/test_reasoning.py` | Prompt rendering, parsing, reasoning client behavior, live smoke | 20 |
| `tests/test_regs.py` | Regulation chunking, retrieval, cap extraction, live embedding smoke | 39 |
| `tests/test_torcs_control_daemon.py` | TORCS daemon launch/recovery/control behavior | 11 |
| `tests/test_torcs_driver_config_contract.py` | Driver-config contract validation | 4 |
| `tests/test_torcs_driver_recovery.py` | Managed-driver recovery and steering logic | 18 |
| `tests/test_torcs_parser.py` | JSONL parsing and energy calibration regression | 9 |
| `tests/test_validator.py` | Deterministic Pass-1 validator rules | 22 |
| `tests/test_zone_detector.py` | Deterministic zone detection heuristics | 30 |

## Network-marked tests

The network-marked tests exercise real external services and should be treated separately from the default local pass:

- `tests/test_pipeline.py::test_pipeline_live_watsonx_end_to_end`
- `tests/test_reasoning.py::test_reason_about_zone_live_watsonx`
- `tests/test_regs.py::test_embed_chunks_live_watsonx_returns_768_dim`
- `tests/test_guardian.py::test_score_recommendation_live_watsonx`

They validate the watsonx-backed production path, but they are intentionally not the default operator loop.

## Commands

### Default local suite

```bash
.venv/bin/pytest -q -m "not network"
```

### Network suite

```bash
.venv/bin/pytest -q -m network
```

### Single-file examples

```bash
.venv/bin/pytest tests/test_api.py -q
.venv/bin/pytest tests/test_pipeline.py::test_pipeline_happy_path -q
```

### Frontend build gate

```bash
npm --prefix ui run build
```

## What the tests cover well

- Replay upload and persistence lifecycle
- Live TORCS stub-session creation and later upgrade to completed sessions
- Session history enrichment from active telemetry files
- SSE stream behavior for snapshots, completed laps, and race-end detection
- Driver-profile CRUD and read-only protections
- What-if perturbation semantics and caching
- Deterministic validation and Guardian scoring
- Regulation retrieval and harvest-cap extraction
- TORCS parser safe-read behavior for malformed/incomplete JSONL tails
- Calibration regression on the real TORCS baseline capture

## Known testing posture

- v1 has no GitHub Actions workflow
- the network suite depends on live watsonx credentials and available quota
- the UI is verified via production build rather than a dedicated browser test suite

## Architecturally important regression guards

### TORCS calibration

`tests/test_torcs_parser.py::test_torcs_baseline_energy_calibration` protects the shared energy-derivation constants against silent drift. If the calibration changes for the wrong reason, downstream zone detection and reasoning quality degrade immediately.

### Active-session streaming

`tests/test_api.py` now covers:
- recovering a missing live session from its capture file
- waiting for active telemetry files to appear
- snapshot deduplication
- race-end emission after file stall
- partial-first-lap correction for mid-lap joins

### Control-plane contract

The API and daemon tests together protect:
- start/stop/recover flow
- live-session stub persistence
- control-daemon reconciliation after transient unreachable errors
- driver-profile materialization into the managed TORCS path

## Verification snapshot used for this doc refresh

The current doc refresh verified:
- `npm --prefix ui run build`
- `pytest --collect-only -q -s tests`

If you want a fresh execution proof after a change, re-run the local suite and the UI build commands above.
