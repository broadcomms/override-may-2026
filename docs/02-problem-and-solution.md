# Problem and Solution Statement
 
### The Problem
> In 2026, Formula 1 enters a radically different hybrid era — the MGU-H is removed, the MGU-K triples to 350 kW, energy splits roughly 50/50, and DRS is replaced by Override Mode. Race engineers face a brand-new problem: every lap is now an energy management decision, and existing public AI tools (AWS F1 Insights, Oracle's Red Bull stack, IBM's Ferrari fan app) were built for the 2014–2025 rules. There is no open, explainable tool for the 2026 era — for engineers or for fans trying to follow the new tactical chess match.
 
### The Solution
OVERRIDE is an upload-first AI copilot that ingests a session replay, identifies inefficient energy-deployment zones, and generates plain-language explanations grounded in the actual 2026 F1 energy-management regulations.

v1.0 ships **five IBM technologies**: **IBM Granite 4.x Instruct** for causal reasoning, **Docling** to parse and ground in the FIA's published 2026 energy-management regulation, **Granite Embedding 278M Multilingual** for regulation chunk retrieval, **Granite Guardian 3-8b** with custom Bring-Your-Own-Criteria for energy-safety and regulation-consistency scoring (preceded by a deterministic validation pass), and **Langflow** for visual orchestration design and demonstration layer. All Granite models are served via **IBM watsonx.ai** (US-South); see `docs/adrs/ADR-001-watsonx-runtime.md`.

**Granite Time Series TTM-R2** (a 5-lap state-of-charge forecast over the energy curve) is **deferred to v1.1** per the graceful-degradation guardrail — the pipeline runs end-to-end without it; the energy curve renders an explicit "Forecast unavailable — TTM-R2 deferred to v1.1" badge. The architecture (Pydantic `Forecast` schema, `forecast_fn` parameter, UI forecast-band rendering) is already in place; v1.1 only needs `core/forecasting.py` to ship as the live wrapper.

Two modes share one engine:
> - **Engineer Mode** — full reasoning chains, regulation citations, confidence scores, what-if simulation.
> - **Fan Mode** — same intelligence in plain language, designed for broadcasters and viewers trying to follow the new energy chess match.

Extending the IBM TORCS Learning Lab simulator. Open source under Apache 2.0.
 