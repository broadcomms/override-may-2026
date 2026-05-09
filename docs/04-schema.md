# OVERRIDE — Data Schemas

> Single source of truth for the typed contracts shared by every component in the OVERRIDE pipeline. All schemas are **Pydantic v2** and live in `ingest/schema.py` (cross-cutting types) or beside the component that owns them. Backend, prompts, validator, Guardian, and UI all consume these definitions — divergence is a bug.

---

## 1. Where each schema lives

| Schema | File | Used by |
|---|---|---|
| `LapFeatures`, `LapWindow` | `ingest/schema.py` | ingest, analysis, forecasting, reasoning |
| `Zone` | `analysis/zone_detector.py` | reasoning, validator, UI |
| `Forecast` | `core/forecasting.py` | reasoning, UI (energy curve) |
| `RegulationChunk`, `RegulationCitation` | `core/regs.py` | reasoning, validator, UI |
| `ReasoningInput`, `ReasoningOutput` | `core/reasoning.py` | validator, Guardian, UI |
| `ValidatorResult` | `core/validator.py` | pipeline glue, UI badge |
| `GuardianResult` | `core/guardian.py` | pipeline glue, UI badge |
| `FanOutput` | `core/fan_mode.py` | UI (Fan Mode card) |
| `Recommendation` | `api/routes/sessions.py` | API response, UI |
| `Session`, `SessionSummary`, `SessionList` | `api/routes/sessions.py` | API response, UI |
| `LapsResponse`, `ZonesResponse` | `api/routes/sessions.py` | API response, UI |
| `WhatIfRequest`, `WhatIfResult` | `api/routes/whatif.py` | API, UI |
| `ApiError` | `api/errors.py` | every API endpoint |

> **Forward-looking note.** The `core/`, `api/`, and `analysis/` modules above are scaffolded in the repo but most are still empty stubs at the time of writing — they get implemented during roadmap **P1.4 → P2.7** (`pipeline.py` arrives at P2.7). This table is the destination, not the current state.

The reasoning, fan, and grounding **prompt contracts** (in `prompts/*.system.md`) are the JSON shape the LLM must produce — they must match `ReasoningOutput`, `FanOutput`, and the grounding step input/output described below. If a prompt and its schema disagree, the schema wins and the prompt is updated.

---

## 2. Conventions

- All times in **seconds** (float).
- All energies in **megajoules (MJ)** (float). Megajoules is the FIA's unit; do not mix with kJ or J in transit.
- All powers in **kilowatts (kW)** (float).
- All speeds in **km/h** (float).
- All `lap_number` values are **1-indexed** to match FIA convention.
- Fields that may be unknown are typed `Optional[T]` with default `None`. Never use sentinel strings like `"N/A"`.
- All JSON keys use `snake_case`. The frontend may map to camelCase at the boundary.
- Timestamps are ISO-8601 UTC strings.
- IDs are short, URL-safe slugs (e.g., `s_20260512_a4f9`), generated server-side.

---

## 3. Lap-level features

### `LapFeatures`

Produced by `ingest/torx_parser.py` and `ingest/fastf1_parser.py`. One row per completed lap.

```python
class LapFeatures(BaseModel):
    lap_number: int                    # 1-indexed
    soc_start: float                   # battery state-of-charge at lap start, [0, 1]
    soc_end: float                     # battery state-of-charge at lap end, [0, 1]
    harvest_mj: float                  # total harvested energy this lap, MJ
    deploy_mj: float                   # total deployed energy this lap, MJ
    lap_time: float                    # full lap time, seconds
    sector1_time: float                # seconds
    sector2_time: float                # seconds
    sector3_time: float                # seconds
    avg_speed: float                   # km/h
    max_speed: float                   # km/h
    override_uses: int                 # count of Override Mode activations this lap
    boost_uses: int                    # count of additional MGU-K boost windows
    recharge_zones: list[int]          # sector indices (1, 2, 3) where harvest > 0.1 MJ
    soc_source: Literal["measured", "derived"]    # provenance flag (risk R1)
```

**Derivation flag.** When `soc_start` / `soc_end` / `harvest_mj` / `deploy_mj` are not directly exposed by the source (Torx may not), they are derived from throttle/brake integrals and `soc_source` is set to `"derived"`. The derivation routine is documented in code comments and in `docs/plans/torx-telemetry-map.md`.

### `LapWindow`

A 30-lap rolling context fed into TTM-R2 forecasting and reasoning. Constructed by `core/pipeline.py`.

```python
class LapWindow(BaseModel):
    session_id: str
    laps: list[LapFeatures]            # length 1–30; reasoning accepts shorter, TTM does not
    soc_max: float                     # battery capacity, MJ (used for [0, max] bounds)
    track_id: Optional[str] = None     # e.g., "monza", "silverstone"; informational only
```

Reasoning never receives more than 30 laps to keep prompt size bounded. If the session has more laps, the most recent 30 are used.

---

## 4. Zone detection

### `ZoneType` (enum)

```python
class ZoneType(str, Enum):
    LOW_ROI_DEPLOY = "low-roi-deploy"
    LATE_RECHARGE = "late-recharge"
    OVER_HARVEST = "over-harvest"
    UNUSED_OVERRIDE = "unused-override"
```

These four values are the only zone types in scope. They mirror the patterns identified in P1.5 of the roadmap and the `zone_type` enum in `prompts/grounding.system.md`.

### `Zone`

```python
class Zone(BaseModel):
    zone_id: str                       # short slug, e.g., "z_t16_l23"
    zone_type: ZoneType
    lap_number: int                    # 1-indexed
    sector: Literal[1, 2, 3]
    severity: Literal["low", "medium", "high"]
    metrics: dict[str, float]          # supporting numbers, schema below
    description: str                   # one-sentence English summary, deterministic (no LLM)
```

`metrics` keys depend on `zone_type`:

| `zone_type` | Required `metrics` keys |
|---|---|
| `low-roi-deploy` | `deploy_mj`, `time_gain_s`, `roi_mj_per_s` |
| `late-recharge` | `harvest_mj`, `lap_time_cost_s`, `available_window_s` |
| `over-harvest` | `harvest_mj`, `cap_mj`, `headroom_mj` |
| `unused-override` | `gap_to_leader_s`, `available_override_mj`, `straight_length_m` |

---

## 5. Forecasting

### `Forecast`

Optional. Produced by `core/forecasting.py` only when `len(laps) >= 30` and the prediction-interval width is below the configured threshold.

```python
class Forecast(BaseModel):
    horizon_laps: int                  # always 5
    point: list[float]                 # length 5, predicted SoC, [0, 1]
    lower: list[float]                 # length 5, prediction-interval lower bound
    upper: list[float]                 # length 5, prediction-interval upper bound
    mae_validation: Optional[float]    # held-out MAE recorded during P2.2
    model_version: str                 # pinned, e.g., "ibm-granite/granite-timeseries-ttm-r2@<hash>"
```

When forecasting is unavailable, the field carrying a `Forecast` is set to `None` and the UI renders the empty state ("forecast unavailable"). **No partial / fabricated forecast is ever returned.**

---

## 6. Regulation grounding

### `RegulationChunk`

Produced by `core/regs.py` from Docling DocTags extraction.

```python
class RegulationChunk(BaseModel):
    chunk_id: str                      # short slug, stable across runs
    text: str                          # verbatim passage, ≤ 1000 chars
    source: RegulationSource
    keywords: list[str]                # extracted at index time
    embedding: Optional[list[float]] = None    # 768-dim from ibm/granite-embedding-278m-multilingual via watsonx (see ADR-001); None if vector search is disabled
```

### `RegulationSource`

```python
class RegulationSource(BaseModel):
    document_title: str                # e.g., "FIA 2026 Formula 1 Technical Regulations"
    issue: str                         # e.g., "Issue 12 — 2025-06-10"
    section: str                       # e.g., "C.5.4" — read from extracted DocTag, never hardcoded
    public_url: str                    # the FIA URL the PDF was fetched from
    fetched_at: datetime               # ISO-8601 UTC
```

**Hard rule.** No prompt, schema default, test fixture, or user-facing string carries a hardcoded FIA article string — ever. Before verification gate **G-4** (per `06-roadmap.md` §4 P2.5), prompts use generic phrasing and the `RegulationSource` API field is null. After G-4, every `section` value is read out of the Docling extraction at runtime and lives only in this struct — never as a literal in code, prompts, or templates.

### `RegulationCitation`

The reduced form attached to a `ReasoningOutput`.

```python
class RegulationCitation(BaseModel):
    passage: str                       # ≤ 25 words, verbatim from RegulationChunk.text
    source: RegulationSource           # passed through from the chunk
```

---

## 7. Reasoning

### `ReasoningInput`

Constructed by `core/pipeline.py` and passed into `core/reasoning.py`.

```python
class ReasoningInput(BaseModel):
    session_id: str
    lap_window: LapWindow
    forecast: Optional[Forecast]       # None = forecast unavailable
    zone: Zone                         # one input -> one ReasoningOutput
    regulation: Optional[RegulationChunk]   # None if grounding found nothing relevant
```

### `ReasoningOutput`

Produced by Granite Instruct under `prompts/reasoning.system.md`. **This shape is normative — the prompt must match it.**

```python
class ReasoningOutput(BaseModel):
    cause: str                         # 1 sentence
    consequence: str                   # 1 sentence
    recommendation: str                # 1 sentence; tone: "consider", "could explore"
    regulation_citation: Optional[RegulationCitation]
    confidence: Literal["low", "medium", "high"]
    confidence_justification: str      # 1 sentence
    reasoning_chain: list[str]         # 3–5 short steps, each ≤ 20 words
```

When `regulation` is `None` in the input, `regulation_citation` is `None` in the output and `confidence` is `"low"`. The prompt enforces this; the validator re-checks it.

---

## 8. Validation (Pass 1)

### `ValidatorResult`

Produced by `core/validator.py`. Mirrors the rule set in `core/validator.yaml`.

```python
class ValidatorResult(BaseModel):
    passed: bool
    failed_rules: list[str]            # rule IDs from validator.yaml
    retry_count: int                   # 0, 1, or 2
    notes: list[str]                   # short messages per failed rule
```

Rule IDs:
- `energy_bounds`
- `harvest_cap` — **before gate G-4 this rule is a no-op** (returns pass). The per-lap cap is loaded from `RegulationSource` at G-4; until the verified cap exists there is nothing to check against.
- `citation_existence` — before G-4, no chunks are retrieved, so this rule is automatically satisfied for `regulation_citation = null`.
- `language_safety`
- `source_consistency` — before G-4, the rule is satisfied for `regulation_citation = null`.

On `passed=False` and `retry_count<2`, the pipeline regenerates the reasoning with a stricter prompt. On `retry_count==2` and still failing, the recommendation is **not** shipped — the API returns it with a low-confidence flag and the failed rules in the response so the UI can render the failure (no silent drop).

---

## 9. AI safety scoring (Pass 2)

### `GuardianResult`

Produced by `core/guardian.py`. Mirrors `guardian/byoc_criteria.yaml`.

```python
class GuardianResult(BaseModel):
    passed: bool                       # True iff every criterion >= pass_threshold
    pass_threshold: float              # default 0.70, mirrors YAML
    scores: dict[str, float]           # {"energy_safety": 0.84, "regulation_consistency": 0.91}
    rationales: dict[str, str]         # {"energy_safety": "stays under cap...", ...}
    retry_count: int                   # 0, 1, or 2
    final_confidence: Literal["low", "medium", "high"]   # set after retries
```

If both criteria score ≥ `pass_threshold`, `passed=True` and the recommendation ships. If a criterion fails, the pipeline regenerates with the explicit-citation prompt (max 2 retries). After 2 retries, the recommendation ships with `final_confidence="low"` — never silently dropped.

---

## 10. Fan Mode

### `FanOutput`

Produced by Granite Instruct under `prompts/fan_mode.system.md`. Consumes a `ReasoningOutput`.

```python
class FanOutput(BaseModel):
    headline: str                      # ≤ 14 words
    what_happened: str                 # 1–2 sentences, no acronyms
    why_it_mattered: str               # 1–2 sentences, qualitative impact
    the_rule: Optional[str]            # 1 sentence paraphrase; None if regulation_citation was None
```

If the underlying `ReasoningOutput.confidence` is `"low"`, the prompt prepends `"It looks like"` to `what_happened` (per `prompts/fan_mode.system.md`).

---

## 11. API surface types

These are the response shapes the FastAPI layer returns. Detailed endpoint behavior lives in `04-api.md`; this section defines only the data shapes.

### `Recommendation`

The unit the UI renders per zone. One per detected zone.

```python
class Recommendation(BaseModel):
    zone: Zone
    reasoning: ReasoningOutput
    fan: Optional[FanOutput]                 # populated only when mode == "fan" or both
    validator: ValidatorResult
    guardian: GuardianResult
```

### `SessionSummary`

Lightweight session-level metadata (returned by `GET /api/sessions`).

```python
class SessionSummary(BaseModel):
    session_id: str
    uploaded_at: datetime
    source: Literal["torx", "fastf1"]
    lap_count: int                     # post-truncation, if any
    forecast_available: bool
    zone_count: int
    track_id: Optional[str] = None
    note: Optional[str] = None         # surface-level message about the session
                                       # (e.g., "Truncated from 147 to 120 laps")
```

`note` is rendered as a small caption on the session card and on `/sessions`. It is not error-channel — errors use `ApiError`. Use it for non-fatal events the user should know about (truncation, derived energy state, missing track ID, etc.).

### `Session`

Full debrief (returned by `GET /api/sessions/{id}` and as the `201` body of `POST /api/sessions`).

```python
class Session(BaseModel):
    summary: SessionSummary
    laps: list[LapFeatures]
    forecast: Optional[Forecast]
    recommendations: list[Recommendation]    # ordered by lap_number
    regulation_source: Optional[RegulationSource]   # for the citations cited; null if none used
```

### `SessionList`

Paged listing returned by `GET /api/sessions`.

```python
class SessionList(BaseModel):
    sessions: list[SessionSummary]
    next_offset: Optional[int]               # null when there are no more results
    total: int
```

### `LapsResponse`

Lap-level slice returned by `GET /api/sessions/{id}/laps`. Kept narrow so chart renders are cheap.

```python
class LapsResponse(BaseModel):
    session_id: str
    laps: list[LapFeatures]
```

### `ZonesResponse`

Recommendations slice returned by `GET /api/sessions/{id}/zones`.

```python
class ZonesResponse(BaseModel):
    session_id: str
    recommendations: list[Recommendation]
    regulation_source: Optional[RegulationSource]
```

### `WhatIfRequest` / `WhatIfResult`

```python
class WhatIfRequest(BaseModel):
    zone_id: str
    parameter: Literal["delay_first_deploy", "skip_harvest_zone", "extend_override"]
    delta: float                       # parameter-specific magnitude (e.g., laps to delay)


class WhatIfResult(BaseModel):
    original: Recommendation           # the recommendation before the what-if
    modified: Recommendation           # regenerated with the perturbation applied
    forecast_delta: Optional[Forecast] # forecast under the perturbed scenario; None if N/A
    note: str                          # one sentence summarizing the perturbation
```

`WhatIfResult` runs the full pipeline (detect → ground → reason → validate → guardian) on the perturbed zone, so both passes apply. A what-if can fail Pass 1 or Pass 2 — that result is shown, not hidden.

---

## 12. Errors

### `ApiError`

Returned by any FastAPI endpoint on failure. The frontend renders error states from this shape.

```python
class ApiError(BaseModel):
    error_code: Literal[
        "INVALID_FILE_FORMAT",
        "FILE_TOO_LARGE",
        "PARSE_FAILED",
        "FORECAST_UNAVAILABLE",
        "MODEL_UNAVAILABLE",
        "RATE_LIMITED",
        "NOT_FOUND",
        "INTERNAL_ERROR",
    ]
    message: str                       # human-readable, safe to display in UI
    detail: Optional[str] = None       # diagnostic; never PII; never stack traces in prod
    request_id: str                    # for log correlation
```

`FORECAST_UNAVAILABLE` is **not** an error for the pipeline as a whole — only for endpoints that explicitly serve the forecast resource (e.g., `GET /api/sessions/{id}/forecast`). A short session, or one with a wide TTM prediction interval, still produces zones, reasoning, and recommendations; the forecast is simply absent. The specific reason (`lap_count < 30` vs. `prediction_interval_width > threshold`) is carried in `ApiError.detail`, not in the `error_code` — the user-facing meaning is the same: "we could not give you a confident forecast for this session."

---

## 13. Schema versioning

- Schemas are versioned implicitly by the repo tag (`v0.0.1`, `v0.1.0`, `v1.0.0`).
- Until `v1.0.0`, breaking changes are allowed in the same PR that updates every consumer (parsers, prompts, validator, Guardian, UI).
- After `v1.0.0`, breaking changes require an ADR in `docs/adrs/` and a deprecation period.

---

## 14. Open items

- **`metrics` validation** — current spec leaves `Zone.metrics` as a free-form `dict[str, float]`. Tightening this into per-`zone_type` Pydantic discriminated unions is a P2.1 follow-up; tracked as ADR-002 candidate.
- ~~**Embedding storage** — decide model and dimensionality before committing chunks.~~ **Resolved 2026-05-08:** `ibm/granite-embedding-278m-multilingual` on watsonx.ai, dimension 768. See `docs/adrs/ADR-001-watsonx-runtime.md` § "Embeddings for retrieval".
- **`SessionSummary.track_id`** — populated only when the source clearly identifies a circuit; informational only, never used for control flow.
