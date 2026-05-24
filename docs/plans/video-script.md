# OVERRIDE - Submission Video Script

> **Runtime target:** 2:55 maximum.  
> **Narration target:** about 145 spoken words per minute.  
> **Current source of truth:** live cockpit first, completed-session trust proof second. This supersedes the older fixture-only script and the older "do not show what-if" note.

---

## Segment 1 - Hook: the 2026 energy problem - 0:00-0:18

**Visual**
- Black screen for one beat.
- Cut to `assets/video/segment_01_split.png`: old simple energy line versus dense 2026 energy map.
- Overlay: "Every lap is now an energy decision."
- End on `assets/brand/logo-on-dark.png`.

**VO**

> In 2026, Formula 1's hybrid rules change the shape of racing. The battery is no longer a background system. Every lap is now an energy decision.

---

## Segment 2 - Problem: data is visible, reasoning is not - 0:18-0:40

**Visual**
- Use `assets/graphics/TELEMETRY.mp4` or `assets/graphics/TELEMETRY-NUMS.mp4`.
- Cut to telemetry-overload frame, then a clean product screenshot.
- Overlay: "Telemetry shows what happened. Strategy needs why."

**VO**

> Teams can see telemetry, but the new strategic question is harder: where did we waste energy, what rule bounds the choice, and how should a human review the tradeoff?

---

## Segment 3 - Live cockpit: AI during the run - 0:40-1:18

**Visual**
- Start at `/upload`, race control visible.
- Click **Start race**.
- Cut to `/cockpit`: timing rail, TORCS frame, hybrid rail.
- Scroll to the AI Race Engineer card.
- Toggle Engineer to Fan inside the live cockpit card.

**VO**

> OVERRIDE connects the IBM TORCS learning lab to a live race cockpit. It streams lap telemetry, tracks state of charge, harvest, deploy, and race timing, then highlights deterministic energy pressure while Granite prepares a readable race-engineer explanation.

---

## Segment 4 - Debrief: the system catches strategy risk - 1:18-1:55

**Visual**
- Stop or use a completed capture; return to `/upload`.
- Click **Ingest** on a live capture.
- Show parsing state briefly.
- Land on completed session detail.
- Hold on KPI strip and post-race intelligence.
- Scroll to the first recommendation card.

**VO**

> After the run, one click turns the capture into a full debrief. OVERRIDE finds inefficient zones, grades battery risk, and surfaces the moments that matter: not just a chart, but cause, consequence, recommendation, and evidence.

---

## Segment 5 - Explainability: regulation grounding plus two safety passes - 1:55-2:22

**Visual**
- Tight frame on a recommendation card.
- Expand the reasoning chain.
- Highlight citation block and footer source.
- Hold on badges: Validation, AI Safety Review, Confidence.
- Show one validator rejection card if time permits.

**VO**

> This is the trust layer. Every recommendation is grounded in a Docling-parsed regulation passage. Pass one is deterministic validation. Pass two is Granite Guardian with custom safety criteria. If the system catches a malformed answer, it shows the failure instead of hiding it.

---

## Segment 6 - What-if and Fan Mode: same engine, different audiences - 2:22-2:42

**Visual**
- Open the What-if rail on a recommendation.
- Run **delay first deploy** or show the completed before/after diff.
- Toggle the completed session to Fan Mode.
- Hold on the plain-language recommendation.

**VO**

> Engineers can test a counterfactual and see the same pipeline rerun on the alternate strategy. Fan Mode translates the same evidence into plain language, so teams, drivers, broadcasters, and fans share one explanation.

---

## Segment 7 - Stack and close - 2:42-2:55

**Visual**
- Three quick cuts: `assets/screenshots/langflow-canvas.png`, `assets/architecture.png`, `assets/screenshots/jaeger-trace.png`.
- Final card: OVERRIDE wordmark, "Decision support, never replacement."

**VO**

> Built on IBM watsonx.ai, Granite Instruct, Guardian, Embedding, TTM-R2, Docling, and Langflow. OVERRIDE: explainable race-strategy AI for the 2026 hybrid era.

---

## Voiceover Word Count

| Segment | Words |
|---|---:|
| 1 | 25 |
| 2 | 27 |
| 3 | 30 |
| 4 | 31 |
| 5 | 34 |
| 6 | 30 |
| 7 | 21 |
| **Total** | **198** |

At 145 wpm, narration is about 82 seconds, leaving about 93 seconds for cursor movement, transitions, and visual hold time.

## Recording Rules

- Use the live cockpit as the proof-of-life moment, then completed debrief as the trust moment.
- Do not position OVERRIDE as "a TORCS project"; TORCS is the reproducible racing sandbox.
- Use "supports", "explains", "highlights", and "recommends"; avoid "decides", "autonomous", and "optimal".
- Avoid hardcoded FIA article narration. Say "the cited regulation passage" or "Docling-parsed regulation passage" unless the UI itself renders the section dynamically.
- Keep all visuals original: OVERRIDE UI, TORCS simulator, Langflow canvas, architecture diagram, Jaeger trace, and generated graphics only.
