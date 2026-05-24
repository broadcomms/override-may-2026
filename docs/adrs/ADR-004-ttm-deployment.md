# ADR-004 — TTM-R2 Docker Container Deployment

- **Status**: Accepted
- **Date**: 2026-05-21
- **Supersedes**: Roadmap P2.2 deferral decision

## Context

TTM-R2 forecasting (`core/forecasting.py`) is fully implemented with comprehensive test coverage (12 test functions, 425 lines) and complete pipeline integration. However, it requires `tsfm_public` (granite-tsfm) which depends on:

- `torch < 2.11`
- `transformers < 5`

The production stack pins:

- `torch == 2.11.0`
- `transformers == 5.8.0`

These dependencies cannot coexist in the same Python environment. The implementation was deferred to v1.1 not due to incomplete code, but due to this dependency conflict.

## Decision

Deploy TTM-R2 as a **separate Docker service** with compatible dependencies, exposing an HTTP API for forecast requests.

### Architecture

```
┌─────────────────────┐         HTTP POST          ┌──────────────────────┐
│  OVERRIDE API       │  /forecast (laps JSON)     │   TTM Service        │
│  (main container)   │ ─────────────────────────▶ │   (ttm container)    │
│  torch 2.11.0       │                            │   torch ~2.10        │
│  transformers 5.8.0 │ ◀─────────────────────────  │   transformers ~4.57 │
│                     │    Forecast | None          │   tsfm_public        │
└─────────────────────┘                            └──────────────────────┘
         │                                                    │
         └────────────── override-net (Docker network) ──────┘
```

### Components

1. **`Dockerfile.ttm`**: Isolated build with torch~=2.10, transformers~=4.57, tsfm_public
2. **`ttm_service.py`**: FastAPI wrapper exposing `/forecast` and `/health` endpoints
3. **`forecast_lap_window_http()`**: HTTP client in `core/forecasting.py`
4. **`docker-compose.yml`**: TTM service with profile `ttm`, reachable at `http://ttm:8001`

### Service Contract

**Request** (`POST /forecast`):
```json
{
  "laps": [
    {
      "lap_number": 1,
      "soc_start": 1.0,
      "soc_end": 0.98,
      "harvest_mj": 3.7,
      "deploy_mj": 3.76,
      "lap_time": 110.0,
      ...
    }
  ]
}
```

**Response**:
```json
{
  "forecast": {
    "point": [0.96, 0.94, 0.92, 0.90, 0.88],
    "lower": [0.94, 0.92, 0.90, 0.88, 0.86],
    "upper": [0.98, 0.96, 0.94, 0.92, 0.90],
    "model_version": "ibm-granite/granite-timeseries-ttm-r2@d6a79570"
  },
  "laps_received": 35,
  "eligible": true
}
```

Or when forecast unavailable (graceful degradation):
```json
{
  "forecast": null,
  "laps_received": 15,
  "eligible": false
}
```

## Consequences

### Positive

- **Dependency isolation**: No version conflicts between production and TTM environments
- **Independent scaling**: TTM service can scale separately from main API
- **Graceful degradation**: Main app continues if TTM service unavailable (FR-3 compliance)
- **Clean separation**: Forecasting is truly optional, not a hard dependency
- **Testability**: Can test main app without TTM service running
- **Deployment flexibility**: Can deploy TTM service only where needed

### Negative

- **Additional container**: Adds complexity to compose stack
- **Network latency**: ~10-50ms per forecast call (acceptable for replay-first architecture)
- **Environment variable**: Requires `TTM_SERVICE_URL` configuration
- **Build time**: First build downloads model weights (~500 MB, one-time cost)

### Operational

**Starting with TTM**:
```bash
podman-compose up override ttm
```

**Starting without TTM** (default):
```bash
podman-compose up override
# Forecasts return None gracefully
```

**Environment variables** (`.env`):
```bash
# Main app
TTM_SERVICE_URL=http://ttm:8001

# TTM service (optional overrides)
TTM_CONTEXT_LENGTH=30
TTM_MIN_LAPS=30
TTM_MAX_INTERVAL_WIDTH=0.15
```

## Alternatives Considered

### 1. Separate venv + subprocess

**Approach**: Create `.venv-ttm` with compatible deps, call via subprocess.

**Rejected because**:
- More complex than HTTP (process management, serialization)
- Harder to scale horizontally
- Tighter coupling between environments
- No health check mechanism

### 2. watsonx.ai model upload

**Approach**: Upload TTM-R2 to watsonx.ai, serve alongside Granite Instruct/Guardian.

**Rejected because**:
- TTM architecture may not be supported by watsonx model serving
- Would require IBM approval/support for custom model upload
- Loses local-first benefit (no network dependency for forecasting)
- Evaluation (Gate G-3) still requires local environment

### 3. Rewrite with torch 2.11

**Approach**: Fork `tsfm_public`, update to torch 2.11 compatibility.

**Rejected because**:
- Significant engineering effort (weeks, not hours)
- Maintenance burden (tracking upstream granite-tsfm updates)
- Risk of breaking model behavior with dependency changes
- Not aligned with "use IBM tools as-is" principle

## Implementation Checklist

- [x] `Dockerfile.ttm` created
- [x] `ttm_service.py` HTTP wrapper created
- [x] `docker-compose.yml` updated with TTM service
- [x] `forecast_lap_window_http()` added to `core/forecasting.py`
- [x] ADR-004 documentation (this file)
- [x] Evaluation run in `.venv` (Gate G-3) — baseline results documented in `docs/plans/ttm-r2-mae-baseline-results.md`
- [ ] Integration test with live TTM service
- [ ] Documentation updates (README, problem-solution, roadmap)
- [ ] UI empty state text update

## Related Files

- `Dockerfile.ttm` — TTM service container definition
- `ttm_service.py` — HTTP wrapper for core/forecasting.py
- `docker-compose.yml` — Service orchestration (profile: ttm)
- `core/forecasting.py` — HTTP client wrapper (`forecast_lap_window_http`)
- `requirements-ttm.txt` — TTM-compatible dependencies
- `docs/06-roadmap.md` — P2.2 TTM-R2 forecasting, Gate G-3

## References

- ADR-001: watsonx.ai runtime (why Granite models are remote, TTM is local)
- ADR-002: TORCS as primary sandbox (synthetic energy model)
- FR-3: Graceful degradation requirement (pipeline must run without forecast)
- `docs/04-schema.md` §2: Forecast schema definition

## Evaluation

MAE validation pending. The evaluation script requires the full project dependencies, so run from the main environment:

```bash
# Use main venv (has all project dependencies)
source .venv/bin/activate
python scripts/eval_forecast_contexts.py

# Optional: Use TTM service (if running)
# Terminal 1: Start TTM service
podman-compose up override ttm

# Terminal 2: Run evaluation with HTTP client
source .venv/bin/activate
export TTM_SERVICE_URL=http://localhost:8001
python scripts/eval_forecast_contexts.py
```

**Note**: The script gracefully handles TTM unavailability by falling back to linear-trend baseline forecasting, which still provides actionable signal about SoC trajectory variance at each context length.
- `tests/test_forecasting.py`: Comprehensive test coverage (12 functions)