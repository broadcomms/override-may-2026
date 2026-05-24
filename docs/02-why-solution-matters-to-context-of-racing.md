# Why OVERRIDE Matters in the Context of Racing

> Submission artifact for the IBM SkillsBuild AI Builders Challenge (May 2026). The strategic argument behind OVERRIDE lives in [`00-thesis.md`](./00-thesis.md); the technical approach in [`02-ai-and-technical-approach.md`](./02-ai-and-technical-approach.md). This document answers a single question for the racing audience: *why is this the right tool, in this sport, at this moment?*

---

## 1. The 2026 reset is real, and it changes the game

Formula 1's 2026 regulation cycle is the deepest technical reset since 2014. The combustion engine drops from delivering ~80% of total output to roughly half. The MGU-K triples to 350 kW. The MGU-H the most efficient recovery path of the previous era is gone. DRS is replaced by Override Mode, deployed dynamically when a chasing car is within roughly one second of the car ahead. Active aerodynamics introduces an X-mode (low-drag) and Z-mode (high-downforce) shift between cornering and straights. Sustainable fuel changes combustion behaviour under load. Mid-2026, the FIA already issued further refinements: qualifying harvest cap reduced from 8 MJ to 7 MJ per lap, super-clipping raised to 350 kW, deployment caps in non-straight zones for safety, low-power-start detection mode, reduced wet-weather deployment.

These are not incremental changes. They change the *unit of strategic reasoning*.

For the previous decade, fuel and tyres were the dominant strategic axes but the hybrid system was a secondary modifier. Race engineers, broadcasters, and fans could explain a race in those terms. In 2026, **every lap is now an energy management decision**: when to harvest, when to deploy, when to recharge, when to trigger Override, whether to accept a slower exit to refill the pack, whether to downshift on a straight to keep the engine in its power band. These tradeoffs happen continuously, lap by lap, and the cost of getting them wrong is no longer "lose half a tenth." A car that drains its battery without managing the recovery becomes a sitting duck on the next straight; a car that over-harvests in qualifying loses the flat-out lap.

The hardware is fixed. The strategic problem is new. A copilot that can reason about energy decisions, lap by lap, is the right shape of tool for the new era.

---

## 2. Why this hurts engineers, drivers, broadcasters, and fans differently

The 2026 changes hit the racing ecosystem at four distinct points.

**Race engineers and strategists.** The search space for a coherent energy plan has exploded. Every track now has its own profile of harvest opportunities and deployment windows that interact with the 50/50 split, with Override Mode availability, with active-aero state, and with sustainable-fuel combustion characteristics and the regulations that bound those decisions are still being amended. Engineers need an open, explainable layer that reasons over telemetry against the *current* regulation text and shows its working in a way they can audit before recommending it forward. No public open-source tool currently does that for the 2026 era.

**Drivers.** A 2026 driver is making more decisions per lap than at any point in the hybrid era. Max Verstappen has publicly described having to *downshift on a straight at full throttle* in a 2026 Monza simulation just to keep the engine in its power band. A move that goes against every instinct in racing and would damage a real gearbox if used routinely. The instincts the driver community spent a decade building no longer translate cleanly. A debrief tool that frames each lap's decisions in cause-and-consequence form, will help drivers and engineers build the new mental model faster.

**Broadcasters and motorsport analysts.** A modern F1 broadcast is a translation layer between the pit wall and the audience. In 2026, the moments that decide races are increasingly invisible to a camera. They live in the energy budget. What used to read on screen as *"they're just driving fast"* now hides an entire chess match in the energy decisions. Broadcasters need credible, plain-language explanations grounded in evidence, not a guess. Fan-companion apps from incumbents such as Oracle's Red Bull strategy stack and IBM's Ferrari fan app were built for the 2014–2025 hybrid rules; none reason over the 2026 regulation text.

**Fans.** The Formula 1's appeal has always been the chess match. The energy budget is just the latest form of that match. A fan who wants to follow the strategy story in 2026 either has to learn the acronyms (`MGU-K`, `SoC`, `Override Mode`, `X-mode`, `Z-mode`, super-clipping, low-power-start detection) or has to stop trying. A copilot that translates the engineer's reasoning into plain language, without dumbing it down, lets the audience grow with the sport instead of churning out of it.

The four audiences are different. The *missing layer* is the same: an explainable reasoning copilot, grounded in the actual regulation, that scales from pit walls to broadcast booths.

---

## 3. The gap in current racing AI

The publicly visible AI in racing has converged on three patterns:

- **Closed strategy stacks** at the team level (Oracle/Red Bull, Mercedes' internal tools). Powerful, proprietary, not auditable, and designed for the previous regulation cycle.
- **Telemetry analytics dashboards** for fans (AWS F1 Insights, IBM's Ferrari fan app). Surface metrics, recap moments, score driver performance but they don't reason over the regulation, and they don't show their inner working.
- **Generic LLM chat layers** layered over racing data. Conversational, sometimes impressive, but they hallucinate citations, lack safety scoring, and have no concept of decision-support framing.

None of these:

- Reason explicitly over the 2026 energy-management regulation text.
- Cite the specific clause that grounds each recommendation, dynamically rendered so it survives FIA amendments.
- Show a deterministic and an AI-based safety pass before any output is shown to the user.
- Ship as open source against a public, reproducible data path.
- Let a user run a *what-if* perturbation against a session they brought themselves and watch the same safety gates run on the perturbed scenario.

There is no open, explainable tool for the 2026 era. That is the gap OVERRIDE is built into.

---

## 4. Why an explainable, regulation-grounded copilot is the right shape of answer

OVERRIDE's central design choice is **explainability over speed**. This is a direct response to what is scarce in the 2026 Hybride energy era.

Public AI tools in this space already optimize for prediction quality. The scarce resource is *understandable* output. A faster predictor that cannot explain itself is a liability when the regulations move mid-season and a recommendation has to survive engineering scrutiny, broadcast quote-checking, or a curious fan asking *why?*. Therefore,an explainable copilot that shows a reasoning chain, cites the regulation passage verbatim, and runs every output through both a deterministic and an AI-based safety pass before it reaches the user, is the most useful thing an open-source AI can be for the 2026 era.

Three design properties matter to the racing audience specifically:

- **Decision support, never replacement.** The IBM SkillsBuild brief explicitly excludes "autonomous systems that replace human decision-making"; the racing community more broadly is allergic to systems that try to drive the car or to call the strategy. OVERRIDE uses the language of **explanation** everywhere ( *supports*, *explains*, *highlights*, *recommends*) and never **decides** (*autonomously*, *optimal*). The engineer reviews; the AI explains.
- **Two-pass safety, made visible.** A deterministic Pass 1 validator checks energy bounds, harvest caps, citation existence, and language safety. A Pass 2 Granite Guardian scorer applies custom Bring-Your-Own-Criteria for energy-safety and regulation-consistency. Both passes' outcomes are *shown* to the user as separate badges. When the system rejects its own output, the racing audience sees that not a black box.
- **Dynamic regulation grounding.** The regulation surface is moving. Article numbers and clauses are read from the Docling extraction at runtime; nothing in OVERRIDE's code, prompts, or templates carries a hardcoded literal. When the FIA issues the next amendment, the system simple re-ingests the new rules and the citations update automatically, no code changes required.

These properties are what makes OVERRIDE useful in racing strategy context. It is not the smartest predictor; it is the most *trustworthy* explanation layer for a sport where the rules change mid-season and the audience needs help following along.

---

## 5. One engine, four audiences

The product surface mirrors the strategic split outlined in §2.

| Audience | Surface | What they see |
|---|---|---|
| Race engineer / strategist | Engineer Mode | Cause → consequence → recommendation, full reasoning chain, verbatim regulation passage with document title and section, validator + Guardian badges, what-if perturbations |
| Broadcaster / motorsport analyst | Engineer Mode (light) → Fan Mode | Same evidence; broadcasters can copy the verbatim regulation passage for credibility, then switch to Fan Mode for the on-air phrasing |
| Curious fan | Fan Mode | Headline, what happened, why it mattered, plain-language paraphrase of the rule. No acronyms, no raw kJ/MJ numbers, no coaching language |
| Driver / coach | Engineer Mode | The same debrief surface as a strategist; drivers iterating on instinct against a new physics need cause-and-consequence framing, not raw telemetry |

One backend pipeline, ingest, zone detection, optional forecasting, regulation grounding, reasoning, two-pass safety feeds all four. Only rendering branches at the UI. The explainability story scales from pit wall to broadcast booth without forking the model.

---

## 6. Honest about scope, honest about limits

The racing audience is sophisticated and skeptical. OVERRIDE is explicit about what it is and is not, on every surface (README, demo video, in-product banner):

- **Not a live pit-wall system.** No real-time team feed; it is replay-first by design.
- **Not an autonomous strategist.** Every output is reviewed and decisions made by a human.
- **Not an FIA-authoritative tool.** Regulation interpretation remains with the FIA.
- **Not a recap, quiz, or fan-companion app.** Engineer-grade reasoning that *also* speaks to fans, not a highlight reel.
- **Not affiliated with Formula 1, the FIA, or any team.** Open-source project, educational, research-oriented, Apache 2.0 License.

Demo data uses the IBM TORCS Learning Lab simulator and FastF1 historical replays, not tested on any authoritative team telemetry. The 2026 regulations are still evolving, and the system reads the current public PDF and grounds in it; newer amendments require re-ingestion. TTM-R2 forecasting requires 30-lap context windows; shorter sessions fall back to heuristic-only mode and the UI says so. Fan Mode uses an LLM for plain-language translation; it is Guardian-screened but is not a substitute for professional commentary.

Stating these limits clearly, in the language of the sport, is the only way an explainability tool earns trust. OVERRIDE is honest about the scope it cannot and should not cover.

---

## 7. Summary

**The 2026 regulation cycle changed the unit of strategic reasoning in F1.** Engineers, drivers, broadcasters, and fans each lost a piece of the mental model that worked from 2014 to 2025, and existing public AI tools built for the previous era do not fill the gap. OVERRIDE is an explainable race-strategy copilot that reasons over telemetry, grounds every recommendation in the actual FIA regulation text via Docling, surfaces both a deterministic and an AI-based safety pass, and renders into Engineer Mode or Fan Mode on the same engine.

It is the right tool for the 2026 era because in a regulation cycle this disruptive, the scarce resource is not faster predictions it is *understandable* ones. A copilot that shows its reasoning, cites the regulation it is grounded in, and translates the same explanation for an engineer and a fan is the most useful thing an open-source AI can be for racing right now.
