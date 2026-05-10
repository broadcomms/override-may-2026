# F1 Strategy Copilot: XAI for Energy Management in TORCS (2026)

The 2026 F1 hybrid power-unit regulations driving the energy-management problem, will use TORCS as the validated sandbox, the XAI methodology (SHAP, TimeSHAP, VIPER, counterfactuals, LLM rationales), a concrete architecture blueprint with an execution plan, strategic framing on what compounds vs. commoditizes, and important caveats around eligibility, regulation drift, and tool-requirement specifics for the F1 team.

## Explainable AI (XAI) F1 Strategy Copilot for Energy Management in TORCS (IBM SkillsBuild May 2026)

**Theme:** 
> "Race to innovate. Drive AI beyond the finish line." 

**Translation:** the operators who own the explanation layer in regulated, real-time, high-stakes domains will own the next decade of enterprise AI. This is a deal memo.

**Position** An open-source, regulation-grounded, explainability-first agent template that maps cleanly onto every high-stakes regulated industry IBM sells into:
- finance
- healthcare
- manufacturing
- motorsport
- energy 

Build it once for the F1 2026, port it for life. 

The five mandated IBM tools are not arbitrary. 
They are the five tools that make enterprise AI work.
— Granite
- Docling
- Langflow
- Context Forge
- IBM Bob is not abitrary.

Building on it is free distribution.

## The energy management product fits the theme and market without contortion.

F1's 2026 power-unit reset has made energy management the dominant competitive variable in racing industry.
- Power unit is a 1.6L V6 ICE with a 350 kW MGU-K and a 50/50 ICE/electric split.
- The MGU-K is tripled from 120 kW(~160 hp) to 350 kW (~470hp), and the expensive MGU-H is deleted. 
- The energy recovery cap is now apptoximately 8.5 MJ per lap, with override/boost modes. 
- Fully sustainable 100% sysnthetic fuels are used, aiming for a net 0% carbon footprint. 

According to Motosport, drivers themselves are calling it "annoying" and "sad." https://www.motorsport.com/f1/news/f1-2026-energy-management-annoying-sad-drivers-lift-early/10794872/ The cognitive load is now a market engineers and fans alike need an XAI co-pilot. TORCS is a clean, free, well-trodden RL/imitation-learning sandbox to prove the decision-logic in days, not months. 



## Comodity 
- Raw inference
- dashboards
- telemetry plots
- generic RAG. 

## Compounds 
- a regulation-grounded knowledge graph of the FIA 2026 rule set (Docling-extracted DocTags)
- a multi-objective decision tree explained via SHAP/counterfactuals/natural-language rationales
- a reusable Langflow + Context Forge + Bob template. 
- a demo with open-source template under Apache 2.0.

## Durable Asset
- The architecture patterns and code to build a production-ready, scalable, and maintainable system. 

## Considerations
- Threat the competition as a packaging excersise not a reasearch project.
- Requires at least 1 IBM technology and using all 5 is over delivery. = Best Use of Technology. 
- TORCS-based "Build an Autonomous AI Driver" meaning TORCS choice is the officially endorsed sandbox.

## Granite
- Granite 4.1, SLM scale and Apache 2.0. 3B/8B/30B. 512K context.
- Granite 4.0-H-Small 32B-A9B MoE 
- Granite 4.0 Micro (3B) is the right default for self hosted. 
- Granite-Docling-258M, a purpose-built VLM that pairs with the Docling library.
- Granite Vision 4.1 4B for chart/table extraction of telemetry-spec PDFs and engineering reports.
- Granite 4.0 Speech (1B–2B) 
- Granite Embedding (107M / 278M multilingual; 30M/125M Slate retrieval)
- Granite Guardian (safety)
- Access serverless via watsonx.ai (pay-as-you-go RU pricing, 1 RU = 1,000 tokens)
- Access local via Ollama (local, free, no API key required) download from Huggingface.

**Default to**
- Granite 4.0 Micro (3B) for self-hosted, low-cost, high-performance inference.
- Granite-Docling-258M for the regulation-PDF parser.
- Granite 4.1 8B/30B Instruct for the synthesis/explanation step.

## Docling
- IBM Research Zurich's open-source (MIT) document processor.
- Output is a structured DoclingDocument (DocTags → JSON/Markdown)
- preserves headings, tables, equations, code, and layout.
- Supports PDF, DOCX, HTML, and more.
- ~30× speedup over standard OCR-only flows.

**Default to**
Use Docling to ingest the 2026 FIA Formula 1 Technical Regulations and Sporting Regulations PDFs, the FIA Power Unit Financial Regulations, team-published technical white papers, and any historical race-debrief PDFs the team owns. Output is a structured JSON/Markdown that can be fed into Granite for synthesis.

## Langflow
- IBM's visual workflow tool for building AI orchestration pipelines.
- Open-source, Python/FastAPI + React-Flow, drag-and-drop.
- Drag-and-drop nodes for data processing, LLM calls, and more.
- Supports Granite, Docling, watsonx.ai, MCP, integration with Bob, and more.
- This is the wiring harness that takes the demo from concept to reality.

This is your wiring harness: build the agent's tool graph here, hand it to Bob for productionization

## ContextForge
- The gateway/registry/proxy that sits in front of any MCP, A2A, or REST/gRPC service. 
- It’s the "orchestrator" that routes requests, enforces rate limits, and provides a unified API surface.
- This is the piece that makes the system look like infrastructure, not a hodgepodge of tools.

## IBM Bob
- Factory that builds the front-end app, the MCP servers.
- stitches the Langflow flow into a deployable artifact

## 2026 F1 regulations
https://www.espn.com/racing/f1/story/_/id/48090668/2026-f1-rules-whats-new-cars-how-changes-affect-racing 
- This has made energy management the entire game. (ESPN 2026)
- ICE peak power dropped from ~550 kW to ~400 kW; 
- MGU-K tripled from 120 kW to 350 kW; 
- MGU-H eliminated; 
- battery still capped at 4 MJ but drivers can now deplete it ~3× per lap; 
- recoverable energy per lap up to 8.5 MJ (already cut to 8 MJ at Melbourne); 
- 4 MJ deployment bursts ≈ 11.5 seconds of full ERS-K; fuel flow cut from 100 kg/h to ~75 kg/h; 
- 100% sustainable fuels. 
- Active aero (X-mode straight-line / Z-mode corner) replaces DRS.

> Drivers must consciously lift and coast, super-clip, and decide when to spend the Override / Boost button (full 350 kW manual deployment, 290 km/h taper) and Overtake Mode (within 1 s of car ahead → +0.5 MJ on the next lap). 

 The cognitive surface area for the strategist exploded and that is the pain a copilot solves. (ESPN 2026)

## TORCS
https://torcs.sourceforge.net/

- Baseline model with known cielings.
- By Bernhard Wymann at v1.3.8 in April 2025, GPL.
- Stable C++ codebase
- SCR (Simulated Car Racing) plug-in exposing 36-sensor opponent vector + track sensors via UDP
- Python wrapper (gym_torcs) with OpenAI Gym semantics.
- IEEE CIG/CEC research staple since 2008 - DDPG, DQN, imitation learning, evolutionary controllers.
- Physics is approximate, no F1-specific hybrid energy model out of the box, no native MGU-K simulation. 
- TORCS is used for PROVING decision logic and wiring, not for production grade vehicle dynamics.
- F1-true alternatives (rFactor 2, Assetto Corsa Evo, F1 24/25 telemetry, OpenF1 API, FastF1)  

# XAI for FI
- Explainable AI for race strategy is the published and validated approach. 

## Challege Brief.
"…apply AI to improve how teams, drivers, or fans experience racing before, during, or after the race." this include AI Strategy & Decision Support, AI Analytics, AI Copilot/Assistant, AI Perception & Vision, Fan Experience. 

An explainable race-strategy copilot for the 2026 hybrid era is a textbook fit because it lands all of the five listed buckets simultaneously. (AI strategy & decision support, AI Analysitcs, AI copilot/assistant and AI perception & vision, and fan experience.)

The project must read as AI driving past the finish line of mere lap-time prediction into the territory of explainable, trusted, real-time decision support. That framing is a gift it demands an XAI angle, which is exactly our wedge.

## Learning Lab.
TORCS + gym_torcs + Python

The official May Learning Lab is "Build an Autonomous AI Driver" using a racing simulator with a baseline driver.

### Prior cohort write-ups
- University of East London, Silesian University of Technology, the Medium series by team "Simple-wood"  confirm the lab uses TORCS + gym_torcs + Python, with IBM Granite as the recommended reasoning/coding aid.
- The user's intuition on TORCS is therefore not just defensible it is exactly what the organizer expects. 

## Limitations (be honest in the README):

Physics is simplified no MGU-K, no battery SoC, no sustainable fuel model out of the box. 
We will simulate the energy model on top of TORCS (treat fuel as a kinetic-energy proxy, add a synthetic SoC/MGU-K bookkeeping layer in your gym wrapper).
- No real F1 tire-degradation curves.
- Aerodynamics and ground effect are rudimentary
- Active Aero is a fiction you bolt on.
- Visuals are dated; this is not a fan-engagement-demo killer feature.

## Tool kit

TORCS + gym_torcs running; baseline rule-based driver lapping a track. Add a Python wrapper that synthetically tracks SoC, MGU-K deployment, and a per-lap recovery cap mirroring 2026 regs.

TORCS does not natively model F1 2026 hybrid energy. You must build the SoC / MGU-K / recovery-cap layer yourself in the gym wrapper. This is straightforward but is additional engineering, not free.

## Post-submission, where the compounding lives.

- Replace TORCS energy model with calibration on OpenF1 historical 2026 telemetry.
- rFactor 2 plug-in for higher-fidelity vehicle dynamics.
- Granite Vision 4.1 4B over on-board camera for hazard / racing-line perception.
- A2A integration: split into specialized agents Federated through Context Forge (Langflow Blog)
    - Regulation Agent, 
    - Telemetry Agent, 
    - Energy Agent,
    - Explanation Agent

## Caveats
The Mercedes-AMG PETRONAS / Sutton et al. Explainable RL for F1 Race Strategy paper (SAC '25, arXiv 2501.04068) is the strongest direct precedent for this project's approach. Cite it openly in the README it strengthens the case that the methodology is industry-validated rather than speculative, and it positions the user's work as the open-source, regulation-grounded, 2026-era descendant of that line of research.