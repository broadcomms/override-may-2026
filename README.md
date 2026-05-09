<p align="center">
  <img src="assets/banner.png" alt="OVERRIDE — Explainable AI Race-Strategy Copilot" width="100%"/>
</p>

<h1 align="center"> 🏁 OVERRIDE</h1>

<p align="center">
  <strong>An explainable AI race-strategy copilot that helps teams and fans understand 2026 hybrid energy decisions through telemetry reasoning, regulation grounding, and what-if analysis.</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/license-Apache_2.0-blue" />
  <img src="https://img.shields.io/badge/Built_with-IBM_Granite-052FAD" />
  <img src="https://img.shields.io/badge/Powered_by-Docling-052FAD" />
  <img src="https://img.shields.io/badge/Orchestrated_with-Langflow-1A1A1A" />
  <img src="https://img.shields.io/badge/IBM_SkillsBuild-AI_Builders_Challenge_May_2026-FF4500" />
</p>

<p align="center">
  <a href="https://youtu.be/PENDING">▶️ 3-minute demo video</a>
  &nbsp;·&nbsp;
  <a href="docs/03-architecture.md">Architecture</a>
  &nbsp;·&nbsp;
  <a href="docs/04-ui-ux-design.md">UI/UX</a>
  &nbsp;·&nbsp;
  <a href="docs/04-api.md">API</a>
</p>

<!-- Demo loop GIF lands here once captured at end of P3.5 polish.
     <p align="center"><img src="assets/demo.gif" alt="OVERRIDE demo loop" width="80%"/></p>
-->

---

## What it looks like

<table>
<tr>
<td width="50%"><strong>Engineer mode — full reasoning + verbatim citation</strong><br/><img src="assets/screenshots/engineer_mode.png" alt="Engineer mode card showing cause/consequence/recommendation, reasoning chain, citation block, validator and Guardian badges"/></td>
<td width="50%"><strong>Fan mode — same intelligence, plain language</strong><br/><img src="assets/screenshots/fan-mode.png" alt="Fan mode card with headline, what happened, why it mattered, the rule"/></td>
</tr>
<tr>
<td><strong>Layered defense — system catches itself</strong><br/><img src="assets/screenshots/guardian-rejection.png" alt="Validator-failed card showing the failed rules and a red-bordered status panel"/></td>
<td><strong>Langflow canvas — design + demo layer</strong><br/><img src="assets/screenshots/langflow-canvas.png" alt="Langflow canvas with 9 OVERRIDE custom components wired end-to-end"/></td>
</tr>
</table>

---

## Why now

In 2026, Formula 1 enters the most disruptive technical regulation cycle in a decade. The MGU-H is gone. The MGU-K triples in power to 350 kW. The split between thermal and electric energy moves to roughly 50/50. DRS is replaced by Override Mode, deployed dynamically when a chasing car is within one second of the car ahead. Active aerodynamics introduces Z-Mode and X-Mode. Sustainable fuel changes engine behavior under load.

For race engineers and drivers, this means *every lap is now an energy management decision* — when to harvest, when to deploy, when to recharge, when to trigger Override. For fans, it means broadcasts become harder to follow: tactics that previously read as "they're just driving fast" now hide entire chess matches in the energy budget.

The publicly-shipped AI in this space — AWS F1 Insights, Oracle's Red Bull strategy stack, IBM's own Ferrari fan app — was built for the 2014–2025 hybrid rules. **There is no public, explainable tool for the 2026 era.**

OVERRIDE is the open-source answer: a copilot that takes a session replay, identifies inefficient deployment zones, forecasts the next five laps' state-of-charge trajectory, explains its reasoning in plain language grounded in the 2026 F1 energy-management regulations, and offers a what-if mode for testing alternative strategies.

## What it does

- **Engineer Mode** — full reasoning chains, regulation citations, confidence scores, what-if simulation.
- **Fan Mode** — same intelligence, plain language, no acronyms. *"The car used battery power too aggressively in low-return corners, leaving less energy available for the long straight."*
- **Upload-first.** Drop in a Torx-lab session, a FastF1 export, or a 2026 race replay. Get a debrief in under 30 seconds.
- **Regulation-grounded.** Every recommendation cites the relevant clause from the 2026 F1 energy-management regulations, parsed with Docling and rendered dynamically — never hardcoded.
- **Explainable.** Granite Guardian scores every recommendation on energy-safety and regulation-consistency dimensions before it's shown to the user.

## How it works

<p align="center"><img src="assets/architecture.png" alt="OVERRIDE architecture" width="90%"/></p>

| Stage | Component | Tech |
|---|---|---|
| Ingest | `torx_parser` / `fastf1_parser` | Python, Pandas |
| Aggregate | Lap-level energy features | Custom (see `analysis/`) |
| Forecast | 5-lap SoC trajectory | **IBM Granite Time Series TTM-R2** |
| Detect | Inefficient deploy / harvest / recharge zones | Pure-Python heuristics |
| Reason | Causal reasoning chain | **IBM Granite 4.x Instruct** |
| Ground | 2026 reg article retrieval | **Docling** |
| Score | Energy-safety + regulation-consistency | **IBM Granite Guardian (latest) BYOC** |
| Orchestrate | Visual pipeline | **Langflow** |
| Translate | Engineer → Fan Mode | **IBM Granite 4.x Instruct** |


## Technology Stack
 


| Component | Role | Source — verify Day 1 |
|---|---|---|
| Granite 4 Hybrid Small | Core reasoning + Fan Mode translation | watsonx.ai US-South, `ibm/granite-4-h-small`. Credentials in `.env` |
| Granite Guardian 3-8b | Pass 2 AI-based safety + regulation-consistency scoring (BYOC) | watsonx.ai US-South, `ibm/granite-guardian-3-8b` |
| Granite Time Series TTM-R2 | **Optional** lap-aggregated SoC/harvest/deploy forecasting | HuggingFace `ibm-granite/granite-timeseries-ttm-r2` |
| Docling | Parse FIA energy-management regulation, extract relevant section | `pip install docling` |
| Langflow | **Design + demo layer**, mirrors the production pipeline | `pip install langflow` |
| IBM Bob | **Build-time only** — development partner, README acknowledgment | bob.ibm.com/trial |
 
**Observability:** direct OpenTelemetry instrumentation (FastAPI auto-instrumentor + manual spans across reasoning / guardian / regs / pipeline stages). Toggle with `OVERRIDE_TRACING=otlp` and view in Jaeger — see [`docs/plans/p3.6-jaeger-trace-capture.md`](docs/plans/p3.6-jaeger-trace-capture.md). Default is `off` (zero overhead).
 

 


## Quickstart

```bash
# 1. Clone + Python 3.12 venv
git clone <repository-url>
cd overdrive-may-2026
/opt/homebrew/bin/python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2. Configure watsonx.ai credentials
cp .env.example .env
#   then edit .env to fill in WATSONX_API_KEY, WATSONX_PROJECT_ID, WATSONX_URL
.venv/bin/python scripts/test_watsonx.py    # gate G-1 (~5s)

# 3. Run the API
.venv/bin/uvicorn api.main:app --reload --port 8000

# 4. In a second terminal, run the UI
cd ui && npm install && npm run dev
# Open http://localhost:3000 → upload data/sessions/sample_torx.json
```

Granite Instruct + Guardian + Embedding all run on watsonx.ai (US-South); only Docling chunk extraction runs locally. No 12 GB local model download. See [`docs/adrs/ADR-001-watsonx-runtime.md`](docs/adrs/ADR-001-watsonx-runtime.md) for the runtime split rationale.

### Optional: Langflow design canvas

```bash
# Separate venv — Langflow ships its own packaging constraints
python3.12 -m venv .venv-langflow
.venv-langflow/bin/pip install -r requirements-langflow.txt

LANGFLOW_COMPONENTS_PATH="$(pwd)/langflow/override_components" \
PYTHONPATH="$(pwd):$PYTHONPATH" \
.venv-langflow/bin/langflow run
# Open http://localhost:7860 → import langflow/override.flow.json
```

The canvas mirrors the production pipeline as 9 visual nodes — useful for stepping through the architecture but not required to run OVERRIDE. See [`langflow/README.md`](langflow/README.md) for the full assembly walkthrough.

## Sample data

`data/sessions/sample_torx.json` ships with a 5-lap synthetic replay that fires the `low-roi-deploy` zone detector reliably — drop it into the upload field for an end-to-end demo. No live data, no broadcast video, no proprietary feeds. Reproducible from public sources.

`data/regs/` ships with the FIA 2026 Technical Regulations (Section C, Issue 18) and pre-built Docling-extracted chunks (`extracted_chunks.sample.json`, 384 chunks across 112 unique sections). The system parses the 8.5 MJ harvest cap directly from the regulation text — never hardcoded.

> **Note**: full Torx Learning Lab integration (additional sample replays in `data/samples/`) is pending IBM Torx GitHub access; the synthetic sample + FastF1 path cover the demo end-to-end without it.

## Live performance (today, 2026-05-09)

End-to-end pipeline run on watsonx.ai Essentials, single zone, no retries:

| Stage | Latency | Notes |
|---|---|---|
| Ingest + Zone Detector | ~200 ms | local, deterministic |
| Reg Retriever (Granite Embedding) | ~2.5 s | watsonx round-trip + cosine + keyword score |
| Reasoning (Granite 4-h-small Instruct) | ~4.0 s | 5-step chain + verbatim citation |
| Validator (Pass-1, deterministic) | <10 ms | 5 rule classes, no LLM |
| Guardian (Pass-2, Granite Guardian 3-8b) | ~1.5 s | 2 BYOC criteria scored in parallel |
| Total | **~8.2 s** | first-try pass for engineer happy path |

Test suite: **231 unit tests + 4 network integration tests = 235 green**. UI bundle: 178 kB gzipped (React 18 + Recharts + custom components).

## Design decisions

- **Upload-first, not live.** Live trackside inference would require licensed F1 data we don't have. Replay-first makes the system deterministic, demoable, and honest about what it is: a *strategy exploration tool*, not a production race-control system.
- **Lap-aggregated forecasting.** TTM-R2's open-source release is documented for minutely-to-hourly resolution. By aggregating to one row per lap (~90 seconds), we operate well within its scope and avoid the temptation to overclaim 3.7 Hz capability.
- **Graceful degradation.** The pipeline runs end-to-end without TTM. TTM enhances; it doesn't gate. Sessions with too few laps simply skip the forecast; reasoning continues from observed evidence.
- **Two-pass safety.** Pass 1 (deterministic validation) protects the demo if Pass 2 (Granite Guardian) integration is rough. Both pass results are shown to the user — judges see a layered, defense-in-depth architecture.
- **Regulation grounding > telemetry brilliance.** Most racing-AI projects compete on "more data, faster models." OVERRIDE competes on *can it explain why*. Granite reasons over telemetry evidence and cites the verified regulation.
- **Decision support, not replacement.** Per the IBM SkillsBuild Challenge guidance, OVERRIDE is a copilot. The engineer (or curious fan) is always the decision-maker. The AI shows reasoning, cites regulations, and surfaces tradeoffs — it never *acts*.
- **Langflow is the design + demo layer.** Production runtime is FastAPI for performance and reliability. Langflow visually documents and demonstrates the architecture; it does not gate the production code path.


## Limitations

- Demo data uses synthetic Torx-shaped JSON and FastF1 historical replays; this is not authoritative team telemetry.
- The 2026 regulations evolve via FIA-published Issues (currently grounded in Section C, Issue 18, dated 2026-05-07). Newer amendments require re-ingestion via `scripts/build_chunks.py`. Section B (Sporting) integration deferred to post-submission.
- TTM-R2 forecasting (optional per FR-3) is not yet shipped — the pipeline runs end-to-end without it; sessions that lack a forecast lower their reported confidence accordingly.
- Fan Mode uses an LLM for plain-language translation; it is Guardian-screened but is not a substitute for professional commentary.

## What this is not

- **Not a live pit-wall system.** No real-time team feed.
- **Not an autonomous strategist.** Every output is reviewed by a human.
- **Not an FIA-authoritative tool.** Reg interpretations are model-grounded; final reading lies with the FIA.
- **Not affiliated with Formula 1, the FIA, or any team.** Open-source educational/research project.

## Acknowledgements

Built for the IBM SkillsBuild AI Builders Challenge, May 2026, organized by BeMyApp. Development accelerated using IBM Bob. Foundation laid by the IBM Torx Learning Lab. Grounded in IBM Granite 4.x Instruct, Granite Guardian (latest), Granite Time Series TTM-R2, Docling, and Langflow.

## License

Apache 2.0 — See [LICENSE](LICENSE).