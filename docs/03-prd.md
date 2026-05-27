# OVERRIDE - Product Requirements Document

> Lean PRD for a 25-day single-operator build. Strategic argument lives in [`00-thesis.md`](./00-thesis.md); architecture in [`03-architecture.md`](./03-architecture.md); shapes and endpoints in [`04-schema.md`](./04-schema.md) and [`04-api.md`](./04-api.md); UI in [`04-ui-ux-design.md`](./04-ui-ux-design.md); execution plan in [`06-roadmap.md`](./06-roadmap.md). This document captures **who, what, how-good, and what's-out-of-scope** this is the contract the the rest of the planning is built on.

---

## 1. Executive summary

**OVERRIDE is an explainable AI race-strategy copilot that helps teams and fans understand 2026 hybrid energy decisions through telemetry reasoning, regulation grounding, and counterfactual strategy review.**

A user uploads a session replay (TORCS simulator output or FastF1 export); within 30 seconds OVERRIDE returns a structured debrief: detected inefficient deploy / harvest / recharge / Overtake-related zones, a causal reasoning chain per zone, a verbatim citation from the FIA's 2026 energy-management regulations, a deterministic safety pass, an AI-based safety pass, and an optional 5-lap forecast. Two UI modes share one engine:

a. **Engineer Mode** for race engineers and analysts who need full reasoning, citations, and counterfactual strategy review;

b. **Fan Mode** for broadcasters and viewers who need plain language.

OVERRIDE competes on *can it explain why*, not on *more data, faster models*. It is a strategy copilot, not a strategist. Every output is reviewed by a human.

---

## 2. Problem statement

### 2.1 The user problem

The 2026 F1 regulation cycle is the deepest technical reset since 2014. The MGU-H is removed, the MGU-K triples to 350 kW, energy splits roughly 50/50, DRS is retired, active aerodynamics handles low-drag straight-line behavior, Overtake Mode provides the race-assist energy mode under FIA F1 Regulations, and fuel is now 100% sustainable. The FIA has already published multiple 2026 regulation issues, so every lap is now an energy decision against a moving rule surface.

This produces two pains:

- **Engineers and analysts** face an exploded strategic search space without an open, explainable tool that reasons over telemetry against the new regulations. They need a debrief layer that shows reasoning and cites the rule it was grounded in.
- **Broadcasters and fans** can no longer follow what's happening on track. Energy-budget decisions are invisible on broadcast but measurable in telemetry. They need a plain-language layer that translates the same intelligence without dumbing it down.

Most public racing AI surfaces metrics or runs as closed team tooling. Those systems can be useful, but they rarely give users an open, auditable way to reason over 2026 hybrid-energy telemetry, dynamic regulation grounding, and counterfactual strategy review in one place.

### 2.2 Why now

- **Regulation surface is moving.** The FIA actively amends the regulation mid-season. Any tool that hardcodes article numbers will rot inside one season. A copilot that grounds the new rules dynamically via IBM Docling is the right shape of answer right now.
- **Open-source models are catching up.** IBM Granite 4.x Instruct, Granite Guardian, and Granite Time Series TTM-R2 collectively make a regulation-grounded reasoning copilot buildable by a single operator on a laptop in 25 days. That wasn't true 18 months ago.
- **Submission window is real.** This is for the IBM SkillsBuild AI Builders Challenge May 2026 entry. Final deadline May 31, 2026 11:59 PM ET; first-10-teams early-submission bonus targeted for May 23.

---

## 3. Target users

OVERRIDE has three audiences. The scope is **all three sharing one backend**, with rendering branching at the UI layer.

### 3.1 Primary: race engineer / strategy analyst

- Builds a mental model of energy decisions across a session.
- Needs to see the reasoning *and* the regulation it was grounded in not a number.
- Wants to test alternative strategies through counterfactual strategy review without rebuilding a simulation.
- Reviews on a laptop or 13 inch table, not a phone. Mobile is outside the submitted scope.

### 3.2 Secondary: broadcaster / motorsport analyst / advanced fan

- Translates an engineering moment into something quotable on air or in writing.
- Needs the explanation in plain language but tied to the same evidence the engineer saw.
- Cares about credibility, would not use a tool that fabricates citations.

### 3.3 Tertiary: curious motorsport fan

- Watches replays for the strategy story, not just the result.
- Wants to learn what an energy decision was without learning the acronyms first.
- Reaches the product through a shared link (broadcaster, social, challange submission page).

### 3.4 Crossover: driver / coach / driver-development engineer

- Builds new instincts around when energy should be saved, deployed, or recovered.
- Uses the same Engineer Mode debrief surface as a strategist; cause→consequence framing helps build the new mental model faster than raw telemetry.
- Not a separate UI - same engine, same Engineer Mode rendering. Listed here because the *why-it-matters* argument depends on this audience.

Four audiences, **one backend pipeline**, two UI surfaces (Engineer + Fan). Asymmetric capability table is in [`04-ui-ux-design.md` §10](./04-ui-ux-design.md#10-engineer--fan-parity-guarantees).

---

## 4. User stories

Stories are tagged by user types: 

- `[E]` Engineer, 
- `[A]` Analyst/Broadcaster, 
- `[F]` Fan. 

Acceptance criteria are abbreviated, full contracts live in the API and UI docs.

### Upload + debrief

- `[E][A][F]` As a user, I drop a TORCS JSON or FastF1 export onto the upload page and within 30 seconds I see a debrief I can read.
- `[E][A][F]` If my session is shorter than 30 laps, I still get zones and reasoning; only the forecast is gracefully hidden.
- `[E][A][F]` If parsing fails, I see *why* (`INVALID_FILE_FORMAT` or `PARSE_FAILED` with a human-readable message), not a generic 500.

### Inspect a recommendation

- `[E]` As an engineer, I click a flagged zone and see cause → consequence → recommendation, a 3–5 step reasoning chain, the verbatim regulation passage, the document/issue/section it came from, the validator badge, and the Guardian score badge all in one card.
- `[E]` I can hover the AI Safety Review badge to see the energy-safety and regulation-consistency criterion scores and rationales separately.
- `[E]` I can collapse the reasoning chain to keep the card compact; expanding is one click.
- `[A]` As an analyst, I can copy the verbatim regulation passage and the reasoning chain to paste into my own copy.

### Run a counterfactual strategy review

- `[E]` I select a counterfactual perturbation (`delay_first_deploy`, `skip_harvest_zone`, or `extend_override`) on one zone, click Run, and see the original card and the perturbed card side by side.
- `[E]` A counterfactual review that fails Pass 1 or Pass 2 is shown with the failure surfaced. The system never silently drops any result.
- `[E]` I can reset the card to the original recommendation in one click.

### Switch to Fan Mode

- `[F]` I press `F` (or the toggle) and the same zones are rendered in plain language: headline, what happened, why it mattered, and a one-sentence paraphrase of the rule.
- `[F]` Fan Mode never coaches drivers or teams, it only explains what happened.
- `[F][A]` If the engineer-mode confidence was *low*, Fan Mode prefixes *"It looks like…"* so I'm not misled.

### Trust the system

- `[E][A]` I can see at the page footer which document, issue, and section the citations are coming from. The information is read at runtime, never hardcoded.
- `[E][A]` Before regulation grounding is verified (gate G-4), I see a banner explaining citations will be generic until verification completes.
- `[E][A][F]` I can see in `/api/version` which exact Granite tags are running, so I can reproduce the result.

---

## 5. Functional requirements

Numbered for cross-reference. **MUST** is a launch blocker; **SHOULD** is a launch goal; **MAY** is a stretch.

### 5.1 Ingest

- **FR-1.1 (MUST)** Parse TORCS replay JSON into `LapFeatures` rows per [`04-schema.md` §3](./04-schema.md#3-lap-level-features).
- **FR-1.2 (MUST)** Parse FastF1 export into the same `LapFeatures` schema. Energy state may be derived from throttle/brake integrals when not natively exposed; provenance flagged in `LapFeatures.soc_source`.
- **FR-1.3 (MUST)** Reject uploads larger than 25 MB with `FILE_TOO_LARGE`. Truncate sessions over 120 laps to the most recent 120, with a note in `SessionSummary`.
- **FR-1.4 (MUST)** Never persist the raw uploaded file after parsing. Only derived artifacts in `data/sessions/{session_id}/`.

### 5.2 Heuristic zone detection

- **FR-2.1 (MUST)** Detect at least the four zone types in `ZoneType`: `low-roi-deploy`, `late-recharge`, `over-harvest`, `unused-override`. Pure Python, deterministic, AI-free.
- **FR-2.2 (MUST)** Each `Zone` carries severity (`low` / `medium` / `high`) and the supporting metrics defined in [`04-schema.md` §4](./04-schema.md#4-zone-detection).
- **FR-2.3 (SHOULD)** A session that produces zero zones renders the empty state ("*No inefficient zones detected, the session was clean.*") rather than an error.

### 5.3 Forecasting (optional)

- **FR-3.1 (MUST)** Run TTM-R2 forecasting only when `len(laps) >= max(TTM_MIN_LAPS, TTM_CONTEXT_LENGTH)` (default 30) AND prediction-interval width is below the configured threshold. Otherwise return `forecast = None`.
- **FR-3.2 (MUST)** When `forecast` is null, the energy curve renders the empty-state hint and the reasoning prompt does not reference future laps with certainty.
- **FR-3.3 (MUST)** Never return a partial / fabricated forecast.

> **Implementation note (2026-05-21).** TTM-R2 forecasting is implemented with complete test coverage (12 functions, 425 lines). Due to dependency conflicts (torch~=2.10 vs production torch==2.11.0), TTM-R2 is deployed as a separate Docker service per ADR-004. The pipeline gracefully degrades when the service is unavailable (FR-3 compliance). Start with `podman-compose up override ttm` to enable forecasting. Without the TTM service, the energy curve renders "Forecast unavailable (session requires ≥30 laps)" and reasoning continues from observed data only. See [`docs/adrs/ADR-004-ttm-deployment.md`](adrs/ADR-004-ttm-deployment.md) for architecture details and [`docs/plans/ttm-r2-mae-baseline-results.md`](plans/ttm-r2-mae-baseline-results.md) for baseline evaluation results.

### 5.4 Regulation grounding

- **FR-4.1 (MUST)** Use Docling to extract the verified energy-management section into structured chunks. The verified document, issue, and section are recorded in `docs/regulation-source.md` at gate G-4 and read at runtime via `RegulationSource`.
- **FR-4.2 (MUST)** No prompt, schema default, test fixture, or user-facing string carries a hardcoded FIA article number ever. Before G-4, prompts use generic phrasing. After G-4, citations render dynamically from the Docling extraction at runtime; the section value lives in the `RegulationSource` struct, never as a literal string in code, prompts, or templates.
- **FR-4.3 (MUST)** When grounding finds no relevant chunk, `regulation_citation` in the reasoning output is `null` and `confidence` is `low`. Citation is never fabricated.
- **FR-4.4 (MUST)** The cited passage in `RegulationCitation.passage` must appear character-for-character in the retrieved chunk text. The validator's `citation_existence` rule enforces this.

### 5.5 Reasoning

- **FR-5.1 (MUST)** Granite 4.x Instruct produces a `ReasoningOutput` matching [`04-schema.md` §7](./04-schema.md#7-reasoning) for every detected zone.
- **FR-5.2 (MUST)** Recommendation language is decision-support only. The validator's `language_safety` rule rejects `"you must"`, `"optimal"`, `"always"`, `"definitely will"`.
- **FR-5.3 (MUST)** Reasoning chain has 3–5 short steps. This is what the engineer sees, not optional.
- **FR-5.4 (MUST)** Output is JSON only, no prose preamble.

### 5.6 Two-pass safety

- **FR-6.1 (MUST)** Pass 1 (deterministic validator) runs against every reasoning output and is **never disabled** by Guardian behavior. Rule IDs in `core/validator.yaml`. On fail, regenerate with stricter prompt up to 2 retries.
- **FR-6.2 (MUST)** Pass 2 (Granite Guardian BYOC) scores `energy_safety` and `regulation_consistency`; both must score ≥ `pass_threshold` (default 0.70) per `guardian/byoc_criteria.yaml`. On fail, regenerate up to 2 retries.
- **FR-6.3 (MUST)** After 2 retries, ship the recommendation with `final_confidence = "low"` and a visible badge never silently drop.
- **FR-6.4 (MUST)** Both pass results are visible in the UI as badges. Failed Pass-1 rules are listed as chips so the failure mode is legible.

### 5.7 Fan Mode

- **FR-7.1 (MUST)** Fan output matches `FanOutput` per [`04-schema.md` §10](./04-schema.md#10-fan-mode), with the acronym substitutions defined in `prompts/fan_mode.system.md`.
- **FR-7.2 (MUST)** Fan Mode never recommends actions. It explains what happened.
- **FR-7.3 (MUST)** When the upstream confidence is `low`, Fan output prepends *"It looks like"* to `what_happened`.
- **FR-7.4 (SHOULD)** Fan Mode is generated lazily on first request, not on upload. Keeps the median upload → debrief latency below 30 s.

### 5.8 Counterfactual strategy review

- **FR-8.1 (MUST)** Three perturbations supported: `delay_first_deploy`, `skip_harvest_zone`, `extend_override`.
- **FR-8.2 (MUST)** A counterfactual review runs the **full** pipeline (detect → ground → reason → validate → Guardian) on the perturbed scenario. Failures are surfaced, not hidden.
- **FR-8.3 (MUST)** Counterfactual review controls live in Engineer Mode only. Fan Mode redirects to Engineer Mode when a counterfactual review is initiated.

### 5.9 UI

- **FR-9.1 (MUST)** Routes: `/upload`, `/sessions`, `/session/[session_id]`. Mode toggle in the header on session pages.
- **FR-9.2 (MUST)** Empty / loading / error states for: forecast unavailable, no zones detected, low confidence, validator-failed-permanently, regulation source unavailable, model unavailable. All defined in [`04-ui-ux-design.md` §7](./04-ui-ux-design.md#7-empty--loading--error-states).
- **FR-9.3 (MUST)** WCAG 2.1 AA contrast on all text. Charts paired with adjacent screen-reader-friendly data tables. Keyboard navigation for mode toggle, zone selection, and counterfactual review controls. `prefers-reduced-motion` honored.
- **FR-9.4 (SHOULD)** Sample-replay chips on `/upload` so judges and reviewers can demo the product without bringing a file.

### 5.10 Observability + reproducibility

- **FR-10.1 (MUST)** OpenTelemetry instrumentation on FastAPI middleware + manual spans around each LLM call. One trace screenshot in the README.
- **FR-10.2 (MUST)** `GET /api/version` returns build SHA and locked model versions per [`04-api.md` §4.2](./04-api.md#42-get-apiversion).
- **FR-10.3 (MUST)** All model versions pinned in `requirements.txt` and `models.json`. `models.json` is populated only after gate G-1.

---

## 6. Non-functional requirements

| Property | Target |
|---|---|
| **Latency** | Median `POST /api/sessions` response ≤ 30 s on a laptop with a healthy watsonx.ai connection. p95 ≤ 60 s. Stage budget in [`04-api.md` §5](./04-api.md#5-pipeline-timing-budget). |
| **Determinism** | Same input → same output across runs (LLM temperature pinned). End-to-end QA verifies this on 5 TORCS + 2 FastF1 replays. |
| **Reliability** | Pipeline runs end-to-end **without TTM**. Forecasting enhances; never gates. Pipeline runs end-to-end **even if Pass 2 is loosened** to a lower threshold — Pass 1 always functions. |
| **Portability** | One-command setup: `podman-compose up` for OVERRIDE alone. Auxiliary services use explicit service selection (`podman-compose up override torcs`, `podman-compose up override jaeger`, `podman-compose up override langflow`). Verified on a clean machine before submission. No GPU required — Granite reasoning happens on watsonx.ai. The clean machine only needs a network connection and a working `.env`. |
| **Accessibility** | WCAG 2.1 AA. Per FR-9.3. |
| **Observability** | Per FR-10. JSON logs, request IDs, no PII, no stack traces in prod responses. |
| **Security** | No auth in the submitted single-user environment. Inputs validated at the upload boundary. Secrets only in `.env` (gitignored). Pinned dependency versions. Detail in `05-security.md`. |
| **Storage** | Local filesystem only. No DB. Sessions stored as Parquet + JSON under `data/sessions/{session_id}/`. |
| **License** | Apache 2.0. Matches Granite licensing. |

---

## 7. Non-goals

OVERRIDE is **not**:

- A live pit-wall system. No real-time team feed. Replay-first by design.
- An autonomous strategist. Every output is reviewed by a human. Decision support, never replacement.
- An FIA-authoritative tool. Regulation interpretation remains with the FIA.
- A recap, quiz, or fan-companion app. Engineer-grade reasoning that *also* speaks to fans, not a highlight reel.
- A multi-user product. No accounts, no sharing, no presence. Auth is documented in [`04-api.md` §10](./04-api.md#10-authentication-out-of-scope-for-v1) for future-proofing only.
- Mobile-native. Desktop-first; mobile breakpoints render but show a density warning.
- A chat interface. Inputs are session uploads + UI controls, not a free-text prompt.
- A trading / financial / medical / safety-critical product. Open-source, educational, research-oriented.
- Affiliated with Formula 1, the FIA, or any team.

---

## 8. Distribution

- **Channel.** Public GitHub repository under `https://github.com/broadcomms/override-may-2026.git`, Apache 2.0 Licence.
- **Submission surface.** BeMyApp project page on the IBM SkillsBuild Challenge platform with banner, logo, summary, video, and repo link.
- **Demo path.** `podman-compose up -d` → `podman-compose logs -f` → drop a sample replay (shipped under `data/samples/`) → land on the debrief view.
- **Models.** watsonx.ai-served Granite Instruct (`ibm/granite-4-h-small`) + Granite Guardian (`ibm/granite-guardian-3-8b`), pinned with project ID and region in `models.json`. TTM-R2 stays local from HuggingFace. Docling runs locally.
- **Data.** No live data, no broadcast video, no licensed feeds. Sample replays from TORCS and FastF1; FIA PDFs fetched via `scripts/download_regulations.py` (PDFs are *not* committed).

There is no licensing, paywall, or telemetry on the user.

---

## 9. Success metrics

OVERRIDE has two scoring lenses: the IBM SkillsBuild judging rubric (external) and a small set of functional metrics (internal).

### 9.1 Judging-rubric alignment

The challenge rubric scores on Technical Execution, Innovation, Challenge Fit, and Implementation & Feasibility. OVERRIDE targets:

- **Technical Execution**: Granite Instruct, Granite Guardian, Granite TTM-R2, Docling, and Langflow all integrated. Two-pass safety visibly surfaces. README, video, repo, license, models.json all present.
- **Innovation**: Explainability-as-product, dual-mode (Engineer + Fan) sharing one engine, BYOC criteria for energy-domain safety, dynamic regulation grounding, and counterfactual review closing back through the same safety gates.
- **Challenge Fit**: Explicitly addresses both *AI Strategy & Decision Support* and *Fan Experience* solution areas from the challenge brief.
- **Implementation & Feasibility**: Runs on a linux (debian) laptop (8GB RAM, 4 vCPUs, 32GB storage), replay-first, deterministic, originals-only visuals, no licensed data dependencies.

### 9.2 Functional metrics (internal)

| Metric | Target |
|---|---|
| End-to-end run on 5 TORCS + 2 FastF1 replays | 7 / 7 produce a valid debrief |
| Median upload → debrief latency on a 47-lap session, watsonx warm | ≤ 30 s |
| Pass-1 validator pass rate on first attempt | ≥ 70% |
| Guardian pass rate on first attempt (after threshold calibration) | ≥ 60% |
| Reasoning eval harness (10 scenarios × 3 attempts, manual scoring) | average accuracy ≥ 4 / 5 |
| Forecast MAE (held-out TORCS replay, when laps ≥ 30) | recorded and shipped, not gated |
| One-command Docker setup on a clean machine | works first attempt |
| Video runtime | ≤ 2:55 |

---

## 10. Open questions

Questions that must be resolved before or during implementation but which do not block this PRD.

- **OQ-1** Which exact FIA document grounds the recommendations? Resolved at gate G-4 (roadmap P2.5). Until then, prompts use generic phrasing and the `regulation_source` API field is null.
- **OQ-2** **Resolved 2026-05-08:** watsonx.ai runtime selected. Models pinned: `ibm/granite-4-h-small`, `ibm/granite-guardian-3-8b`. See `docs/adrs/ADR-001-watsonx-runtime.md`.
- **OQ-3** Does the TORCS simulator expose battery SoC directly, or do we derive it from throttle/brake integrals? Resolved at gate G-2 (roadmap P1.3).
- **OQ-4** SSE streaming endpoint (API §4.10) — keep for the demo recording, or cut as scope creep? Decide during P3.5.
- **OQ-5** Heatmap density at >60 laps — horizontal scroll vs. 2-lap aggregation. Decide during P3.5.
- **OQ-6** Sample-replay selection — which 3 TORCS + 1 FastF1 ship as one-click samples? Curate during data-prep alongside P1.4.
- **OQ-7** ContextForge vs direct OpenTelemetry — decided at roadmap P3.6 based on remaining time budget.
