# OVERRIDE Demo Video Storyboard

**Target runtime:** 2:55  
**Strategic spine:** show a live racing moment first, then prove that OVERRIDE can explain and safely audit the strategy after the run.  
**Audience promise:** teams, drivers, broadcasters, and fans can understand the same energy decision at the right level of detail.

## Story Arc

1. The 2026 hybrid rules make energy the new strategic battleground.
2. Current telemetry surfaces data, but users still need the reasoning behind energy choices.
3. OVERRIDE watches a TORCS run live and highlights energy pressure as a race-engineer copilot.
4. The completed capture becomes a regulation-grounded debrief.
5. Trust is visible: Docling citation, deterministic validation, Granite Guardian scoring.
6. What-if and Fan Mode prove the same engine serves engineers, drivers, broadcasters, and fans.
7. The stack closes the challenge-fit loop: Granite, watsonx.ai, Docling, Langflow, TTM-R2, and open-source reproducibility.

## Shot Board

| Time | Shot | Source Asset / Route | On-Screen Proof |
|---:|---|---|---|
| 0:00-0:18 | 2026 reset cold open | `assets/video/segment_01_split.png`, `assets/brand/logo-on-dark.png` | Every lap is now an energy decision |
| 0:18-0:40 | Problem | `assets/graphics/TELEMETRY.mp4` or `assets/graphics/TELEMETRY-NUMS.mp4` | Telemetry is visible; reasoning is missing |
| 0:40-1:18 | Live cockpit | `/upload` -> `/cockpit` | TORCS frame, live telemetry, hybrid rail, AI Race Engineer |
| 1:18-1:55 | Completed debrief | `/upload` capture ingest -> `/session/:id` | KPI strip, race report, zones, energy curve |
| 1:55-2:22 | Explainability hero | Recommendation card and validator rejection card | Cause, consequence, reasoning chain, citation, Validation, Guardian |
| 2:22-2:42 | Counterfactual + fan translation | What-if diff, Fan Mode cards | Same pipeline reruns; same evidence becomes plain language |
| 2:42-2:55 | Architecture + close | Langflow canvas, architecture, Jaeger trace, logo | IBM stack, traceability, decision support |

## Most Captivating Moment

The strongest judge-facing beat is not the race launch by itself. It is the transition from live cockpit to completed debrief:

> "The thing you just watched becomes an auditable AI explanation, grounded in regulation and safety-scored before the user sees it."

That sequence makes the project feel real, not just analytical. It also lets the video satisfy all four judging prompts in under three minutes:

- **Problem:** 2026 energy decisions are harder to understand.
- **Solution:** live cockpit plus completed debrief explains the decisions.
- **Tech stack:** Granite, Guardian, Embedding, TTM-R2, Docling, Langflow, watsonx.ai.
- **Value:** human-reviewed strategy support for teams and clearer race understanding for fans.

## Required Visual Evidence

- Live race: `temp/screenshots/05-cockpit.png`, `temp/screenshots/06-ai-race-engineer.png`, `temp/screenshots/06-ai-race-fan-mode.png`.
- Completed debrief: `temp/screenshots/12-session-details.png`, `temp/screenshots/23-race-report.png`.
- Trust proof: `temp/screenshots/15-recommendation-card.png`, `temp/screenshots/16-recommendation-card-chain-of-reasoning.png`, `assets/screenshots/guardian-rejection.png`.
- What-if: `temp/screenshots/17-recommendation-card-whatif-analysis.png`, `temp/screenshots/19-what-if-analysis.png`.
- Fan value: `temp/screenshots/25-fan-mode-recommendation.png`.
- Stack: `assets/screenshots/langflow-canvas.png`, `assets/architecture.png`, `assets/screenshots/jaeger-trace.png`.

