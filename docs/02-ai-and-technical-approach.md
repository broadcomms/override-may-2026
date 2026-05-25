# OVERRIDE - AI / Technical Approach

> Submission artifact for the IBM SkillsBuild AI Builders Challenge (May 2026). Strategic argument lives in [`00-thesis.md`](./00-thesis.md); architecture diagram in [`03-architecture.md`](./03-architecture.md); contracts in [`04-schema.md`](./04-schema.md), [`04-api.md`](./04-api.md), [`04-ui-ux-design.md`](./04-ui-ux-design.md), [`04-langflow-canvas.md`](./04-langflow-canvas.md). This document explains *how* OVERRIDE is built and *why* each component is shaped the way it is.

---

## 1. Approach in one paragraph

OVERRIDE is an **explainable AI race-strategy copilot**. A user uploads a session replay or ingests a completed TORCS live capture; OVERRIDE detects inefficient deploy / harvest / recharge / override zones with deterministic Python heuristics, retrieves the relevant section of the FIA's 2026 energy-management regulations using **Docling** with **IBM Granite Embedding** for chunk retrieval, and produces a structured causal explanation with **IBM Granite 4.x Instruct served via IBM watsonx.ai** that cites the regulation passage verbatim. Every output passes through a two-pass safety architecture - a deterministic validator first, then **IBM Granite Guardian** scoring on Bring-Your-Own-Criteria for energy-safety and regulation-consistency. The same engine renders into Engineer Mode (full reasoning, citations, and counterfactual strategy review) and Fan Mode (plain language). **Langflow** documents the orchestration as a visual canvas; FastAPI runs the production pipeline. **OVERRIDE integrates six IBM technologies - Granite Instruct, Granite Guardian, Granite Embedding, Granite Time Series TTM-R2, Docling, and Langflow.** Granite Time Series TTM-R2 runs as an optional isolated service because of torch dependency constraints; when the service is unavailable or a session lacks 30 completed laps, the pipeline returns `forecast=None` and continues from observed evidence only. (Granite Instruct, Guardian, and Embedding all run on watsonx.ai; Docling and TTM-R2 run locally. See `docs/adrs/ADR-001-watsonx-runtime.md` and `docs/adrs/ADR-004-ttm-deployment.md`.)

---

## 2. Pipeline at a glance

```
Upload  ─▶  Ingest  ─▶  Lap features  ─▶  Zone Detector  ─▶  Reasoning  ─▶  Pass 1 Validator  ─▶  Pass 2 Guardian  ─▶  Mode Router  ─▶  UI
                            │                                    ▲                       │ fail            │ fail              │
                            ▼ (optional, ≥30 laps)               │                       └─── regenerate ──┴────  retry ───────┘
                       TTM-R2 Forecast ─────────────────────────▶│
                                                                 │
                       Regulation chunks  ◀──  Docling  ◀──  FIA PDF (fetched, not committed)
                                                ▲                │
                                                └────── grounding step ───────────────────────▶ Reasoning input
```

Full Mermaid source in [`03-architecture.mmd`](./03-architecture.mmd).

The orange line is the **decision-support boundary**: nothing past Reasoning makes a recommendation visible to the user without first passing through both safety passes. A retry budget of two means failing recommendations either regenerate cleanly or ship explicitly flagged with a low-confidence badge - they are never silently dropped.

---

## 3. Components

Each component has a single responsibility, a typed contract from [`04-schema.md`](./04-schema.md), and a phase number from [`06-roadmap.md`](./06-roadmap.md).

### 3.1 Ingest (`ingest/torcs_parser.py`, `ingest/fastf1_parser.py`)

**Role.** Convert a session replay into one `LapFeatures` row per lap.

**Inputs.** TORCS simulator JSON logs, or FastF1 sessions (Parquet/CSV exports of public historical races).

**Output.** `list[LapFeatures]` with the canonical schema in [`04-schema.md` §3](./04-schema.md#3-lap-level-features): SoC start/end, harvest, deploy, lap time, sector times, speeds, override and boost counts, recharge zones.

**Energy-state derivation.** When the underlying source does not natively expose state-of-charge or energy flux (TORCS may not), values are derived from throttle and brake integrals. The `soc_source` field on every lap row is set to `"derived"` so downstream consumers - and the user - know the provenance. This is risk R1 in `05-risk-register.md`, decided at gate G-2.

### 3.2 Heuristic zone detection (`analysis/zone_detector.py`)

**Role.** Identify inefficient strategy moments using deterministic Python rules. **No AI.** This is the baseline the rest of the pipeline rests on; if every model fails, this still works.

**Zone types.** Four are in scope:

| `zone_type` | Pattern |
|---|---|
| `low-roi-deploy` | Battery deployed in a corner where the time gain per MJ is small |
| `late-recharge` | A harvest opportunity used too late or in a low-recovery window |
| `over-harvest` | Lap harvest approaches the per-lap cap with no need |
| `unused-override` | A close-following window where Override Mode could have been triggered but wasn't |

**Output.** `list[Zone]` with severity (`low` / `medium` / `high`) and per-type metrics. Granite reasons over these zones; it does *not* replace them.

### 3.3 TTM-R2 forecasting (`core/forecasting.py`) - optional

**Role.** 5-lap state-of-charge trajectory used to enrich the reasoning prompt and to render a dotted forecast continuation on the energy curve.

**Model.** `ibm-granite/granite-timeseries-ttm-r2` from HuggingFace, pinned by hash in `models.json`.

**Inputs.** A 30-lap rolling context window with five channels: SoC, harvest, deploy, lap_time, avg_speed.

**Output.** `Forecast` with point predictions and prediction intervals over the next five laps.

**Graceful degradation.** Forecasting runs only when (a) `len(laps) >= 30` and (b) the prediction-interval width stays under the configured threshold. Otherwise `forecast = None` and the rest of the pipeline proceeds - the energy curve renders an empty-state hint, the reasoning prompt switches to *"based on the observed pattern"* framing, and no fabricated forecast is ever returned. This is non-functional requirement NFR/Reliability and risk R2.

**Lap-level resolution.** TTM-R2's open-source release is documented for minutely-to-hourly resolution. Aggregating to one row per lap (~90 seconds) keeps the system inside the model's published scope and avoids overclaiming sub-second capability.

### 3.4 Regulation grounding via Docling (`core/regs.py`, `scripts/download_regulations.py`)

**Role.** Extract the section of the FIA's 2026 regulations that governs energy management, and surface the most relevant passage to the reasoning step.

**Pipeline.**

1. `scripts/download_regulations.py` fetches the public PDF from `fia.com`. The PDF is **not** committed to the repo.
2. **Docling** parses the PDF into structured DocTags, isolating the verified energy-management section.
3. Chunks are saved to `data/regs/extracted_chunks.sample.json` (small, derivative - committable).
4. `core/regs.py` performs keyword + embedding-based retrieval over the chunks (embeddings via `ibm/granite-embedding-278m-multilingual` on watsonx, 768-dim - see ADR-001), returning the most relevant `RegulationChunk` for a given zone type. **Chunks are embedded once at boot** via `scripts/embed-watsonx.sh` and persisted into `RegulationChunk.embedding`; per-query, only the zone-type query is embedded against the same model (~200–500 ms).
5. The retrieved chunk's `RegulationSource` (document title, issue, section, public URL, fetch timestamp) flows through to the reasoning prompt and into `RegulationCitation` on the output.

**Hard rule: dynamic, never hardcoded.** No prompt, schema default, fixture, or user-facing string carries a literal article number. Every `section` value is read from the Docling extraction at runtime. The FIA actively amends the regulation mid-season; any tool that hardcodes `"Article B7.2.3"` rots inside one season. Verification gate **G-4** must pass before any reasoning ships with a real citation; until then, prompts use generic phrasing and the UI shows a banner. (Risks R13, R14.)

### 3.5 Granite Instruct reasoning (`core/reasoning.py`, `prompts/reasoning.system.md`)

**Role.** Produce a structured causal explanation per detected zone, grounded in the retrieved regulation passage.

**Model.** IBM Granite 4.x Instruct (`ibm/granite-4-h-small`), served via **watsonx.ai** (US-South) using the chat API (`/ml/v1/text/chat`). The model ID, region, and project ID are pinned in `models.json` after gate **G-1**. See `docs/adrs/ADR-001-watsonx-runtime.md` for the runtime rationale.

**Prompt.** `prompts/reasoning.system.md` is the system prompt; it specifies the input shape (`lap_window`, `forecast`, `zone`, `regulation`) and the strict output contract.

**Output.** `ReasoningOutput` per [`04-schema.md` §7](./04-schema.md#7-reasoning):

- `cause` - one sentence describing what happened in the data.
- `consequence` - one sentence describing the energy or lap-time impact.
- `recommendation` - one sentence offering a strategy alternative the engineer could explore. Tone: *"consider"*, *"could explore"*. Never *"you must"*, *"optimal"*, *"always"*.
- `regulation_citation` - verbatim ≤25-word passage + structured `RegulationSource`. `null` if no relevant chunk was retrieved.
- `confidence` - one of `low`, `medium`, `high`.
- `confidence_justification` - one sentence explaining the confidence level.
- `reasoning_chain` - 3–5 short steps showing how evidence became conclusion. This is the engineer-visible trace.

**Hard rules.** Cite verbatim or set citation `null` and lower confidence. Never claim certainty about counterfactual outcomes. Never reference future laps with certainty when `forecast` is null. JSON only - no prose preamble.

### 3.6 Pass 1: deterministic validator (`core/validator.py`, `core/validator.yaml`)

**Role.** Pure-Python check that runs on every reasoning output before it enters AI safety scoring. Fast, deterministic, never disabled.

**Rules** (full set in `core/validator.yaml`):

| Rule | Check |
|---|---|
| `energy_bounds` | The recommended action keeps SoC in `[0, max]` over the next 5 laps. |
| `harvest_cap` | The implied harvest never exceeds the per-lap cap from the verified regulation. |
| `citation_existence` | `regulation_citation.passage` appears verbatim in the retrieved chunks. |
| `language_safety` | No matches for `you must`, `optimal`, `always`, `definitely will`. |
| `source_consistency` | `regulation_citation.source` matches a chunk's source field. |

**Behavior on fail.** Regenerate with a stricter prompt, max 2 retries. After 2 retries: ship the recommendation explicitly flagged with the failed rules, never silently drop. Pass 1 must remain functional even if Pass 2 thresholds are loosened - gate G-5.

### 3.7 Pass 2: Granite Guardian BYOC (`core/guardian.py`, `guardian/byoc_criteria.yaml`)

**Role.** AI-based contextual scoring on two domain-specific criteria.

**Model.** IBM Granite Guardian (`ibm/granite-guardian-3-8b`), served via **watsonx.ai**. Pinned in `models.json` after gate G-1. The model is in IBM's deprecation window (2026-05-05 → 2026-08-08); the submission lands well inside it. Migration to the next Guardian release happens post-submission per ADR-001.

**Criteria** (full rubric in `guardian/byoc_criteria.yaml`):

| Criterion | What it scores |
|---|---|
| `energy_safety` | The recommendation, if followed, would not violate energy harvest or deployment caps, drive SoC negative, or exceed the MGU-K operating envelope. |
| `regulation_consistency` | The cited passage exists, is topically aligned with the zone type, and is not contradicted by other parts of the same regulation passage. |

**Behavior on fail.** Both criteria must score ≥ `pass_threshold` (default 0.70). On fail, regenerate with an explicit-citation-required prompt, max 2 retries. After 2 retries, ship with `final_confidence = "low"` and a visible AI Safety Review badge on the card.

**Why two passes.** Pass 1 gives deterministic evidence checks before Pass 2 adds Granite Guardian semantic scoring. Both pass results are visible, so users can audit the recommendation rather than trust a black box.

### 3.8 Fan Mode translation (`core/fan_mode.py`, `prompts/fan_mode.system.md`)

**Role.** Rewrite a structured `ReasoningOutput` into a `FanOutput` with no acronyms, qualitative numbers, and a warm-but-not-condescending voice.

**Model.** Granite 4.x Instruct, slightly higher temperature than reasoning to allow more natural prose, still constrained by the strict output schema.

**Acronym substitution rules** (defined in `prompts/fan_mode.system.md`): `MGU-K` → "energy recovery system"; `SoC` → "battery level"; `deploy` → "use the boost"; `harvest` → "recharge the battery"; `Override Mode` → "the new boost button". No raw kJ / MJ numbers; qualitative descriptors only.

**Lazy execution.** Fan Mode runs on first request, not on upload. Keeps median upload→debrief latency under 30 s. The toggle in the header (`E` / `F`) calls the Fan endpoint per zone; switching back to Engineer is free.

**Confidence handling.** When the upstream confidence is `low`, Fan output prepends *"It looks like…"* to `what_happened` so the audience is not misled.

**Hard rule.** Fan Mode never recommends actions to drivers or teams. It explains what happened. Counterfactual strategy review controls live in Engineer Mode only.

### 3.9 Langflow canvas (`langflow/override.flow.json`) - design layer

**Role.** A visual mirror of the production pipeline that judges and contributors can read at a glance, plus a one-shot demo flow that runs end-to-end on a sample replay during the video recording.

**Scope.** Langflow is **not the production runtime.** The production path is FastAPI for performance and reliability. The canvas documents architecture and powers the demo cut. Full canvas spec in [`04-langflow-canvas.md`](./04-langflow-canvas.md).

### 3.10 FastAPI runtime (`api/`)

**Role.** Production HTTP layer. Endpoints, request/response shapes, error envelope, observability, rate limits, and timing budget defined in [`04-api.md`](./04-api.md).

**Key properties.** No auth in the submitted single-user environment. OpenTelemetry instrumentation on every span. Sessions stored on local disk only (Parquet + JSON under `data/sessions/{session_id}/`). No database. Median pipeline budget: ≤ 30 s end-to-end on a warm watsonx.ai connection.

### 3.11 Frontend (`ui/`)

**Role.** Engineer Mode and Fan Mode rendering against the FastAPI surface. Built with React + Vite + Tailwind. Full UI/UX spec in [`04-ui-ux-design.md`](./04-ui-ux-design.md).

---

## 4. Why these choices

Every non-obvious decision in OVERRIDE traces back to the thesis in [`00-thesis.md`](./00-thesis.md).

- **Explainability over speed.** Public AI tools in this space already optimize for prediction quality. The scarce resource in the 2026 era is *understandable* output. OVERRIDE shows reasoning chains, cites regulations verbatim, and surfaces both safety passes - judges and engineers can *audit* the model.
- **Replay-first, not live.** Live trackside inference would require licensed team telemetry we cannot honestly source. Replay-first makes the system deterministic, demoable, and accurate about what it is.
- **Heuristics first, then AI.** Pure-Python zone detection runs every time. Granite reasons over the heuristics; it does not replace them. If every model fails, the heuristic baseline still produces useful zones.
- **Lap-aggregated forecasting.** Stays inside TTM-R2's documented operating range and avoids overclaiming.
- **Graceful degradation.** Pipeline runs end-to-end without TTM. Forecasting is enhancement, not gating.
- **Two-pass safety.** Pass 1 gives deterministic evidence checks before Pass 2 adds Granite Guardian semantic scoring. Both pass results are visible, so users can audit the recommendation rather than trust a black box.
- **Dynamic regulation grounding.** Article numbers are read from the Docling extraction at runtime. The regulation moves; hardcoded prose rots.
- **One engine, two surfaces.** Engineer Mode and Fan Mode share reasoning, grounding, and Guardian scoring. Only rendering differs. The explainability story scales from pit wall to broadcast booth without forking the model.
- **Decision support, never replacement.** Language enforced everywhere - *supports / explains / highlights / recommends*, never *decides / autonomously / optimal*. This is also a regulatory framing for the IBM SkillsBuild brief, which excludes "autonomous systems that replace human decision-making."
- **Langflow as design layer, FastAPI as runtime.** Visual orchestration documents architecture; FastAPI carries the production path.

---

## 5. Required IBM and open-source technologies

The challenge brief requires at least one IBM AI-supported technology (Granite, Docling, Langflow, or Context Forge). OVERRIDE uses **six**:

| Technology | Role | Source |
|---|---|---|
| **IBM Granite 4.x Instruct** | Causal reasoning + Fan Mode translation | watsonx.ai US-South (`ibm/granite-4-h-small`), pinned in `models.json` |
| **IBM Granite Guardian** | Pass-2 BYOC safety scoring | watsonx.ai US-South (`ibm/granite-guardian-3-8b`), pinned in `models.json` |
| **IBM Granite Embedding** | Regulation chunk retrieval (P2.5) | watsonx.ai US-South (`ibm/granite-embedding-278m-multilingual`), 768-dim |
| **IBM Granite Time Series TTM-R2** | Optional 5-lap SoC forecasting | HuggingFace `ibm-granite/granite-timeseries-ttm-r2` |
| **Docling** | FIA regulation parsing and structured extraction | `pip install docling` |
| **Langflow** | Visual orchestration design + demo layer | `pip install langflow` |

Optional polish: ContextForge for an MCP-gateway Jaeger trace screenshot. Direct OpenTelemetry instrumentation in FastAPI is a clean fallback (decided at roadmap P3.6).

---

## 6. Reproducibility

OVERRIDE is built to run end-to-end on a clean machine without bespoke setup:

- **One-command install.** `podman-compose up` starts the FastAPI runtime and serves the built UI bundle as static files from `:8000`. When TORCS, Jaeger, Langflow, or TTM-R2 are needed, the supported commands are `podman-compose up override torcs`, `podman-compose up override jaeger`, `podman-compose up override langflow`, and `podman-compose up override ttm`. Granite reasoning calls go to watsonx.ai using credentials from `.env`. The README's Quickstart is the contract.
- **Pinned versions.** `requirements.txt` pins Python deps; `models.json` records the watsonx model IDs, region, project-ID env var, and TTM-R2 HuggingFace revision. Locked at gate G-1 before any reasoning code is written.
- **Public data only.** Sample replays in `data/samples/` come from the IBM TORCS Learning Lab simulator and FastF1 historical sessions. The FIA regulation PDF is fetched via `scripts/download_regulations.py` - never committed.
- **Deterministic outputs.** LLM temperature pinned. End-to-end QA on roadmap P3.7 verifies the same input produces the same output across runs on 5 TORCS + 2 FastF1 replays.
- **Versioned API surface.** `GET /api/version` returns build SHA + locked model versions so any reviewer can reproduce a result.
- **Originals only.** No F1 broadcast footage, paddock photography, or team livery in any submission asset. TORCS output, UI recordings, generated charts, Langflow canvas, and original animations only.

---

## 7. Limitations honestly stated

- Demo data uses the IBM TORCS Learning Lab simulator and FastF1 historical replays - this is not authoritative team telemetry.
- The 2026 regulations are still evolving; the system reads the current public PDF and grounds in it, but newer amendments require re-ingestion.
- TTM-R2 forecasting requires 30-lap context windows; sessions shorter than that fall back to heuristic-only mode (forecast unavailable).
- Fan Mode uses an LLM for plain-language translation; it is Guardian-screened but is not a substitute for professional commentary.
- OVERRIDE is **not** a live pit-wall system, **not** an autonomous strategist, **not** an FIA-authoritative tool, and **not** affiliated with Formula 1, the FIA, or any team.

These are repeated in the README and the demo video to make sure the system's posture is unmistakable.
