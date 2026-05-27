# Thesis

> **OVERRIDE is an explainable AI race-strategy copilot that helps teams and fans understand 2026 hybrid energy decisions through telemetry reasoning, regulation grounding, and counterfactual strategy review.**

This document states the central argument behind OVERRIDE: what changed in 2026, what new problem that change created, why existing tooling does not address it, and why an explainability-first copilot grounded in the actual FIA regulations is the right shape of answer.

---

## 1. The 2026 disruption

Formula 1's 2026 regulation cycle is the deepest technical reset since 2014. Five changes matter for race strategy:

- **50/50 power split.** The combustion engine drops from ~80% of total output to roughly half. The MGU-K triples in power to 350 kW. Battery is no longer the side-show - it carries half the lap.
- **MGU-H removed.** The single most efficient recovery path of the previous era is gone. The car's only meaningful way to refill the battery is now braking, which fundamentally rewrites where and how energy can be replenished.
- **DRS retired; active aero and Overtake Mode replace its job.** Active aerodynamics handles the low-drag straight-line behavior that DRS made visible, while Overtake Mode provides the race-assist energy mode when available under FIA F1 Regulations. That shifts the strategy question from a fixed flap zone to an energy-and-aero decision.
- **Active aerodynamics (X-Mode / Z-Mode).** Front and rear wings shift between high-grip and low-drag positions automatically through the lap. The aerodynamic state of the car is now another time-varying input that strategy must reason about.
- **100% sustainable fuel.** Combustion behaviour under load is materially different from prior fuels.

On top of those baseline rules, the FIA has already published multiple 2026 regulation issues. The regulation surface is *moving* - any tool that hardcodes article numbers will be wrong inside a season.

## 2. The new problem class

These changes do not just shift numbers. They change the unit of strategic reasoning.

In the 2014–2025 era, fuel and tyres were the dominant strategic axes; the hybrid system was a secondary modifier. Engineers and broadcasters could explain a race in those terms.

In 2026, **every lap is an energy decision**. Where to harvest, where to deploy, when to trigger Overtake Mode, when to accept a slower exit to refill the pack, whether to downshift on a straight to keep the engine in its power band - these tradeoffs happen continuously, lap by lap, and the cost of getting them wrong is no longer "lose half a tenth." A car that drains its battery without managing the recovery becomes a sitting duck on the next straight; a car that over-harvests in qualifying loses the flat-out lap.

This creates two distinct user pains:

- **For engineers and analysts**, the search space for a coherent energy plan has exploded, while the public open-source tooling to *reason* over telemetry against the new regulations does not yet exist.
- **For broadcasters, analysts, and fans**, the spectacle is harder to follow because energy-budget decisions are invisible on broadcast but measurable in telemetry.

The common thread is **explainability**. The data pipelines exist. The reasoning layer that connects telemetry to regulation to plain-language consequence does not.

## 3. The gap in existing tooling

Most public racing AI surfaces metrics or runs as closed team tooling. Those systems can be useful, but they are not designed as open, auditable reasoning layers for the 2026 hybrid-energy reset. The gap is a system that can:

- Reason explicitly over the 2026 energy-management regulation text.
- Show their working in a way an engineer can audit or a fan can follow.
- Ship as open source against a public, reproducible data path.
- Let a user run a counterfactual strategy review against a session they brought themselves.

There is no open, explainable tool for the 2026 era. That is the gap OVERRIDE is built into.

## 4. The claim

> The right way to help teams and fans navigate the 2026 energy era is **not** to ship a faster predictor. It is to ship an **explainable copilot** that grounds every recommendation in the actual FIA regulation text and shows its reasoning.

OVERRIDE competes on *can it explain why*, not on *more data, faster models*. Concretely, it ingests a session replay, identifies inefficient deploy / harvest / recharge zones, optionally forecasts a five-lap state-of-charge trajectory, generates a causal reasoning chain, grounds the recommendation in the relevant 2026 energy-management regulation section parsed dynamically with Docling, and surfaces both a deterministic safety pass and an AI-based safety pass to the user before any output is shown.

The same engine drives two surfaces: an **Engineer Mode** with full reasoning chains, regulation citations, confidence scores, and counterfactual strategy review; and a **Fan Mode** that translates the same intelligence into plain language for broadcasters, analysts, and viewers.

## 5. Design choices and why

Every non-obvious decision in OVERRIDE traces back to the thesis above:

- **Upload-first / replay-first, not live trackside.** Live inference would require licensed team telemetry we cannot honestly source. Replay-first makes the system deterministic, demoable, and accurate about what it is - a *strategy exploration* tool, not a production race-control system.
- **Lap-aggregated forecasting.** Granite Time Series TTM-R2's open-source release is documented for minutely-to-hourly resolution. Aggregating to one row per lap (~90 seconds) keeps the system inside the model's published scope and avoids overclaiming sub-second capability.
- **Graceful degradation.** The pipeline runs end-to-end without TTM. Forecasting enhances; it does not gate. Sessions shorter than the model's context window simply skip the forecast and continue from observed evidence.
- **Two-pass safety.** Pass 1 gives deterministic evidence checks before Pass 2 adds Granite Guardian semantic scoring. Both pass results are visible, so users can audit the recommendation rather than trust a black box.
- **Regulation grounding via Docling, never hardcoded.** Article numbers and clauses are rendered dynamically from the Docling extraction. Because the FIA actively amends the regulation mid-season, any tool that hardcodes "Article B7.2.3" into prose will rot.
- **Decision support, never decision replacement.** Every output uses the language of explanation - *supports, explains, highlights, recommends* - never *decides, autonomously, optimal*. The engineer (or curious fan) is always the decision-maker.
- **Langflow as the design + demo layer; FastAPI as the production runtime.** Langflow visually documents and demonstrates the architecture. The runtime path is Python/FastAPI for performance and reliability.
- **One engine, two surfaces.** Engineer Mode and Fan Mode share the same reasoning, regulation grounding, and Guardian scoring. Only the rendering differs. This means the explainability story scales from pit wall to broadcast booth without forking the model.

## 6. What OVERRIDE is not

Stating the boundaries is part of the thesis:

- **Not a live pit-wall system.** No real-time team feed.
- **Not an autonomous strategist.** Every output is reviewed by a human.
- **Not an FIA-authoritative tool.** Regulation interpretation remains with the FIA.
- **Not a recap or fan-companion app.** OVERRIDE is engineer-grade reasoning that *also* speaks to fans, not a quiz or a highlight reel.
- **Not affiliated with Formula 1, the FIA, or any team.** Open-source, educational, research-oriented.

## 7. Why this matters

The IBM SkillsBuild AI Builders Challenge frames the brief as "turn complex racing data into smarter, more explainable insights" and rewards solutions that "build trust through explainability." OVERRIDE takes that brief literally. It argues that in a regulation cycle this disruptive, the scarce resource is not faster predictions - it is *understandable* ones. A copilot that can show its reasoning, cite the regulation it is grounded in, and translate the same explanation for an engineer and a fan is the most useful thing an open-source AI can be in the 2026 era.

That is the thesis. Everything else in this repository - the architecture, the prompts, the safety passes, the Langflow canvas, the demo script - is a consequence of it.
