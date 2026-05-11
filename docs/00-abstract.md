# Abstract


# Locked Positioning Sentence
> OVERRIDE is an explainable AI race-strategy copilot that helps teams and fans understand 2026 hybrid energy decisions through telemetry reasoning, regulation grounding, and what-if analysis.

OVERRIDE is a copilot.
The engineer reviews; the AI explains.

OVERRIDE = Engineer grade reasoning + Explainability

Upload-first / replay-first architecture.

**The Strongest part of Override is:**
Explainable energy-strategy reasoning grounded in 2026 regulations and telemetry.

**README openning paragraph:**
> OVERRIDE is an explainable AI race-strategy copilot that helps teams and fans understand 2026 hybrid energy decisions through telemetry reasoning, regulation grounding, and what-if analysis.

## Positioning

**Primary positioning:**
AI strategy copilot for the 2026 hybrid energy era

**Secondary positioning:**
Also usable as an explainability layer for broadcasters, analysts, and advanced fans

**Target audiences:**
- Teams
- Drivers
- Fans
- Explainability


> AI that explains why an energy strategy violated or underutilized a regulation constraint

> Development accelerated using IBM Bob

Frame the system
> “strategy exploration and explainable reasoning”


# Demo Script
- TORCS simulator
- UI screen recording
- generated charts
- Langflow canvas
- Custom animation



**0:00–0:20 — Hook (Cold Open: the 2026 problem)**

- **Visual:** 
Black screen → fade in: split-screen of an old hybrid energy graph (left, simple) vs. a new 2026 multi-zone energy map (right, dense). 
Both are original generated visuals, not screenshots. 
Text overlay (A): "In 2026, F1 hybrid rules change radically."

**Voiceover:**
“In 2026, Formula 1's hybrid rules have changed radically. Every lap is now an energy decision. Teams must decide where to harvest, deploy, and conserve energy lap by lap.”

Text overlay (B): "Every lap is now an energy decision."

Visual elements.
* energy map overlay,
* sector visualization,
* regulation snippet.

Cut to: OVERRIDE logo + locked positioning sentence as text card. (3 seconds.)

⸻

**0:20–0:50 — Problem Statement**
- **Visual:** 
Raw telemetry overload — wall of numbers scrolling. 
Then a confused engineer-style avatar with a question mark. (generic schematic engineer-style)

- **Voiceover:**
“Current telemetry tools show data, but they do not explain strategy tradeoffs clearly.”
"Today's tools show data, not reasoning. AWS, Oracle, and IBM's own Ferrari app shipped for the old rules. There's no open, explainable tool for the 2026 era."

Text overlay: "Today's tools show data, not reasoning."
* raw telemetry overload,
* confusing energy traces.

⸻

**0:50–1:40 — OVERRIDE Live Demo (Engineer-Mode)**

- **Visual:** 
Browser. Drag a TORCS replay file onto the upload area. 
Loading shimmer. 
Energy curve renders. 
Zone heatmap appears with three flagged zones.

- **Click a zone.** 
Reasoning card slides in: cause → consequence → recommendation. 
Highlighted regulation citation appears in side panel.
Citation rendered dynamically from Docling extraction. (no hardcoded text)

- **Voiceover (60 words):** *"Drop in a session replay. OVERRIDE ingests the telemetry, aggregates lap-level energy features, and where there's enough history, forecasts the next five laps with IBM Granite Time Series. It detects three inefficient zones in this race. 
Click any zone - Granite 4.x Instruct explains the cause, the consequence, and grounds its recommendation 2026 F1 energy-management regulations, parsed with Docling."*


Upload replay/session file.
System:
1. parses lap data,
2. aggregates energy metrics,
3. forecasts next-lap SoC trajectory,
4. identifies inefficient deployment zones,
5. generates explanation,
6. cites regulation grounding,
7. outputs confidence + Guardian score.

This is the core scoring section.

⸻

**1:40–2:10 — Explainability (The Hero)**

- **Visual:** Slow zoom on the reasoning card. Show:
  - The thought trace
  - The regulation citation with relevant phrase highlighted
  - Pass 1: "Validation ✓" green badge
  - Pass 2: Granite Guardian risk score badge
  - A "What-if: delay deploy by 1 lap" toggle that re-runs and shows updated forecast

- **Voiceover (38 words):** *"This is the core. Every recommendation cites a specific regulation clause. Two safety passes - deterministic validation, then Granite Guardian's AI scoring on custom criteria. If either fails, it's regenerated. The engineer always sees the reasoning before any decision."

Every output is scored by Granite Guardian against custom criteria — energy-safety, regulation-consistency. If it fails, it's regenerated. The engineer always sees the reasoning before any decision."*

This section matters more than people think.

Show:

* “Why was Turn 16 inefficient?”
* “Why recommend Z-Mode in Turn 9?”
* regulation citation,
* confidence visualization,
* Guardian evaluation.

This directly satisfies:

“build trust through explainability”  

⸻

**2:10–2:30 — Fan Mode** (20s)

- **Visual:** Click "Fan Mode" toggle in header. Same data, simplified. Plain-language card replaces the technical one.
- **Sample text on screen:** *"In Turn 16, your car spent battery power on a corner where it didn't help much. That cost about half a tenth on the next straight."*

- **Voiceover (~16 words):** *"One click switches to Fan Mode. Same intelligence, plain language — engineers, broadcasters, and fans on the same page."*

Translate the same strategy into plain English.

Example:

“The car used battery power too aggressively in low-return corners, leaving less energy available for the long straight.”

Now you hit teams, drivers, and fans simultaneously.

⸻

**2:30–2:42 — Architecture quick-cut** (12s)
- **Visual:**
Langflow canvas screenshot (4s).
Architecture diagram (4s).
Jaeger/OpenTelemetry trace (4s).

- **Voiceover (~22 words):** *"Built on IBM watsonx.ai with Granite Instruct, Guardian, Embedding, and Time Series — plus Docling and Langflow. Open source. Apache 2.0."*

⸻

**2:42–2:55 — Closing** (13s)

- **Visual:** OVERRIDE logo + locked positioning sentence + GitHub URL.
- **Voiceover (~15 words):** *"OVERRIDE. Explainable race-strategy AI for the 2026 hybrid era. Code in the description. Built lean."*

End with:

“OVERRIDE helps racing teams and fans understand the next generation of Formula 1 energy strategy using explainable AI.”

Clean.
Focused.
Memorable.



Safer wording in the product:

“grounded in the relevant 2026 FIA energy-management regulation section”



## The Most Important Insight

You should NEVER position OVERRIDE as:

❌ “A TORCS project”

or

❌ “Built on TORCS”

That lowers perceived value immediately.

Instead position it as:

> “OVERRIDE uses replay/session telemetry generated from simulation and public racing data sources to validate explainable energy-strategy reasoning.”

TORCS becomes:

* infrastructure,
* tooling,
* validation environment,
* not the core product.

This is exactly how enterprise AI companies frame dependencies.




## Discord Pitch (#may-challenge-and-lab)

> Post early in the build window — the longer the lead time, the longer we have to course-correct on organizer feedback (risk R10). Channel: `#may-challenge-and-lab` per the kickoff webinar.

Hi Sydney and Lucas! Quick fit-check on my idea:

OVERRIDE — an explainable AI race-strategy copilot that helps engineers AND
fans understand 2026 F1 hybrid energy decisions. Upload a session replay,
get inefficient-zone analysis with reasoning grounded in the FIA's 2026
energy-management regulations (parsed with Docling), optional forecasting
via Granite Time Series, and a two-pass safety check (deterministic
validator + Granite Guardian BYOC). Two UI modes share one backend:
Engineer Mode (full reasoning chains) and Fan Mode (plain language).

Solution areas: AI Strategy & Decision Support + Fan Experience.
IBM tools: watsonx.ai (serving Granite Instruct + Guardian + Embedding),
Granite Time Series TTM-R2, Docling, Langflow.

Does this read as a clean fit for the May challenge rubric? Anything you'd
flag before I commit 25 days to the build?

Thanks 🙏


---

## The Bigger Strategic Opportunity

This is where sophisticated positioning matters.

OVERRIDE is quietly evolving into something bigger than motorsport.

The hidden value is not:

> “AI for F1”

The hidden value is:

> explainable reasoning over regulated telemetry systems.

That pattern applies to:

* aviation,
* energy grids,
* industrial systems,
* cybersecurity,
* defense,
* healthcare monitoring,
* autonomous systems,
* financial risk systems.

Formula 1 is simply:

* the narrative wedge,
* the emotionally compelling entry point,
* the visually exciting domain.

But the architecture itself is broader.

That is why your project now feels more premium than most hackathon entries.

Because it stopped being:

“an app”

and became:

a reasoning framework with a compelling vertical use case.

That is a much higher-value category.

---

Your strongest long-term move is probably NOT:

“host everything on watsonx.ai”

Instead:

* local runtime,
* optional cloud augmentation,
* portable architecture,
* model-agnostic reasoning layer.

That positioning feels:

* more technically mature,
* more enterprise-capable,
* and less “hackathon dependent.”

---

3. The new FIA regs are an architectural update, not a polish item
You downloaded eight new PDFs into data/regs/. The composition matters:
FileImplicationSection A General Provisions Iss 02 (2026-02-27)New — definitions, scopingSection B Sporting Iss 06 (2026-04-28)Override Mode availability rules — previously OUT OF SCOPE for OVERRIDESection C Technical Iss 12 (2025-06-10)The current G-4 source (canonical citation)Section C Technical Iss 18 (2026-05-07)Supersedes Iss 12 — current G-4 is now staleSection D Financial (F1 Teams)Out of scopeSection E Financial (PU Manufacturers)Out of scopeSection F Operational Iss 08 (2026-05-07)Possibly relevant for telemetry/data definitions
Two real consequences:
(a) G-4 closure is now out of date. docs/regulation-source.md and data/regs/extracted_chunks.sample.json both pin to "Issue 12 — 2025-06-10." The newer Issue 18 (May 7, 2026 — six weeks newer) is now in the corpus. The harvest_cap value of 8.5 MJ may have shifted in Issue 18; the article numbers may have renumbered; the language may differ. G-4 needs re-verification against Issue 18 before P3.5 screenshot capture and definitely before video record.

---

