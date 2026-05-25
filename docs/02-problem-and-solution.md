# Problem and Solution Statement

### The Problem
> In 2026, Formula 1 enters a radically different hybrid era - the MGU-H is removed, the MGU-K triples to 350 kW, energy splits roughly 50/50, and DRS is replaced by Override Mode.

Race engineers face a brand-new problem: every lap is now an energy management decision, and most public racing AI surfaces metrics or runs as closed team tooling. There is no open, explainable tool for the 2026 era - for engineers, analysts, broadcasters, fans, or drivers trying to understand energy-budget decisions that are invisible on broadcast but measurable in telemetry.

### The Solution
OVERRIDE is a replay-first AI copilot that ingests a TORCS or FastF1-style replay export, identifies inefficient energy-deployment zones, and generates plain-language explanations grounded in the actual 2026 F1 energy-management regulations.

OVERRIDE integrates **six IBM technologies**: **IBM Granite 4.x Instruct** for causal reasoning, **Docling** to parse and ground in the FIA's published 2026 energy-management regulation, **Granite Embedding 278M Multilingual** for regulation chunk retrieval, **Granite Guardian 3-8b** with custom Bring-Your-Own-Criteria for energy-safety and regulation-consistency scoring (preceded by a deterministic validation pass), **Granite Time Series TTM-R2** for optional 5-lap SoC forecasting (deployed as a separate Docker service per ADR-004), and **Langflow** for visual orchestration design and demonstration layer. All Granite models are served via **IBM watsonx.ai** (US-South); see `docs/adrs/ADR-001-watsonx-runtime.md`.

**TTM-R2 forecasting** is fully implemented with comprehensive test coverage but runs in a separate Docker container due to dependency conflicts (torch~=2.10 vs production's torch==2.11.0). The pipeline runs end-to-end without it per the graceful-degradation guardrail (FR-3). Start with `podman-compose up override ttm` to enable forecasting. See `docs/adrs/ADR-004-ttm-deployment.md` for architecture details.

Two modes share one engine:
> - **Engineer Mode** - full reasoning chains, regulation citations, confidence scores, and counterfactual strategy review.
> - **Fan Mode** - same intelligence in plain language, designed for broadcasters and viewers trying to follow energy-budget decisions that are invisible on broadcast but measurable in telemetry.

Extending the IBM TORCS Learning Lab simulator. Open source under Apache 2.0.
