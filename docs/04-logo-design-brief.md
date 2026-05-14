# OVERRIDE — Logo Design Brief

> **For the designer.** This brief covers the primary wordmark, secondary icon, and the visual constraints driving them. Skip to **§Deliverables** for the file list and **§Constraints** for the hard rules.

---

## 1. Project at a glance

**OVERRIDE** is an explainable AI race-strategy copilot. It helps engineers and fans understand the 2026 Formula 1 hybrid energy regulations through telemetry reasoning, FIA regulation grounding, and what-if analysis.

- **Submission**: IBM SkillsBuild AI Builders Challenge, May 2026
- **Demo deadline**: 2026-05-31
- **Audience**: race engineers (technical mode) + motorsport fans (plain-language mode)
- **Stack**: IBM Granite models on watsonx.ai (reasoning, embedding, guardian), FastAPI runtime, React UI, Langflow design canvas
- **Key positioning phrase**: *"Strategy exploration, not optimal predictor."*

The product analyses lap telemetry, surfaces inefficient zones (e.g. low-ROI energy deployment, late recharges), then explains the *why* with a verbatim citation from the FIA technical regulations. A two-pass safety architecture (deterministic validator + Granite Guardian classifier) gates every recommendation before it reaches the user.

## 2. The name

**OVERRIDE** plays on a real F1 concept: drivers have a steering-wheel button that temporarily lifts power-deployment limits in defined zones. The name evokes:

- **Driver agency** — the human chooses to deploy
- **Conscious intervention** — overriding a default, with intent
- **Decision support, never replacement** — the *human* overrides; the AI explains, doesn't decide

There is a deliberate duality: the product helps you make better override decisions, but never overrides for you.

## 3. Brand attributes (what the mark should communicate)

| Attribute | What it means visually |
|---|---|
| **Explainable** | Clear, legible, structured — not opaque or "AI-mystical" |
| **Trustworthy** | Disciplined geometry, restrained palette, no flashy gradients |
| **Race-adjacent** | Speed cues OK (motion, vector, focused) — but **no licensed F1 imagery** |
| **Technical + human** | Engineering precision balanced with approachable warmth |
| **Decisive but humble** | Confident wordmark, no exclamation points, no triumphant arrows |

Verbs we use: *supports, explains, highlights, recommends, explores.*
Verbs to avoid: *decides, automates, optimises, dominates, wins.*

## 4. Visual direction (mood, not prescription)

Think **mission-control telemetry meets editorial sports magazine**:

- Restrained, monospace-adjacent typography
- A single accent colour that feels like a "live signal" — not chrome, not neon
- Geometric forms that hint at *intervention* — a button press, a divergence, a fork in the path, a paused timeline
- The letter **O** in OVERRIDE is the natural anchor — it can carry an icon-style mark (a pressed button, a lap segment, an intercept point)

**Vibe references** (mood only, not imitation): NASA mission patches, F1 broadcast HUD overlays (post-2020 minimal era), Bloomberg Terminal, Linear app marks, Tracktor.

## 5. Constraints — hard rules

These come from the FIA submission guidelines and the project's IP policy. **All visuals must be original.**

- ❌ **No F1 broadcast footage, paddock photography, or stills** — even cropped or stylised
- ❌ **No team livery or sponsor colours** — no Ferrari red, McLaren papaya, Mercedes silver-cyan as primary palette
- ❌ **No FIA logos, badges, or trademarked icons** — no checkered flag in trade-dress configurations
- ❌ **No IBM, watsonx, or Granite logos** in the OVERRIDE mark itself — those appear separately as "Built with" credits in the README
- ❌ **No real driver names, numbers, or helmet silhouettes**
- ✅ **Generic motorsport cues are OK**: abstract speed lines, telemetry traces, sector boundaries, generic open-wheel silhouettes drawn from scratch

Documentation note: the project's `CLAUDE.md` codifies this: *"All visuals original. No F1 broadcast footage, paddock photography, or team livery."*

## 6. Deliverables

| File | What | Specs |
|---|---|---|
| `assets/logo.png` | **Primary wordmark** — full "OVERRIDE" lockup, with or without integrated icon | PNG, 2× retina, ≥ 2400 × 800 px (3:1 ratio target), transparent background |
| `assets/logo-icon.png` | **Secondary icon** — square, favicon-and-app-icon-friendly, recognisable at 32 px | PNG, 2× retina, 1024 × 1024 px, transparent background |
| `assets/logo.svg` | **Master vector** of the primary wordmark | SVG, optimised, max 50 KB |
| `assets/logo-icon.svg` | **Master vector** of the icon | SVG, optimised, max 20 KB |

**Variants needed for each:**
- Full colour (on light)
- Full colour (on dark)
- Single-colour black (on light)
- Single-colour white (on dark)
- Monochrome accent (single brand colour, on neutral)

Total: 4 source files (2 PNGs + 2 SVGs) × 5 variants = **20 exports**, organised in `assets/brand/`.

## 7. Typography

Open to designer judgement. Suggested directions:

- **Geometric sans** with technical character (e.g. Inter, IBM Plex Sans, Söhne, Suisse Int'l) — fits the engineering tone
- **Mono-influenced sans** for the wordmark only (e.g. JetBrains Mono, IBM Plex Mono) — emphasises telemetry-as-readout feel
- **Editorial serif accent** OK for taglines but not the wordmark itself

If using IBM Plex (royalty-free, open-source): aligns with the IBM SkillsBuild context without using IBM's trademark. Recommended.

## 8. Colour palette — proposed direction

A two-colour system + one accent. Designer free to refine; below is the working hypothesis:

| Role | Suggested | Why |
|---|---|---|
| Primary dark | `#0F172A` (slate-900) | Mission-control neutral; reads as "instrument panel" |
| Primary light | `#F8FAFC` (slate-50) | Clean canvas, high legibility |
| Signal accent | `#06B6D4` (cyan-500) **OR** `#F59E0B` (amber-500) | Live-data feel; one or the other, not both. Cyan = data; amber = caution/intervention |
| Success | `#10B981` (emerald-500) | Used in Pass-1/Pass-2 green states in the UI |
| Failure | `#EF4444` (red-500) | Layered-defense rejection card |

The accent colour drives the icon mark. **Avoid red as primary** — it's reserved for rejection/failure semantics in the UI and would conflict.

## 9. Don'ts (specific traps)

- ❌ **No "AI brain" or neural-network-as-icon** — overused; doesn't fit the explainability angle
- ❌ **No racing helmet silhouettes** — reads too narrow + IP-adjacent
- ❌ **No checkered flag** — reads cliché + FIA-adjacent
- ❌ **No purple gradient SaaS-startup aesthetic** — too generic
- ❌ **No bold italics for the wordmark** — fast/aggressive cue, conflicts with "decision support, not replacement"
- ❌ **No literal stopwatch / timer iconography** — we're not a lap timer
- ❌ **No emoji or pictographs in the lockup**

## 10. Where the logo will appear

Sizing/usage context for the designer to test against:

| Context | Size | Mark |
|---|---|---|
| README.md hero (top of repo) | 800 × 200 px region | Primary wordmark, on light |
| Demo video opening frame | 1920 × 1080 frame, mark ~40% width | Primary wordmark, on dark |
| App header (UI top-left) | 32 px tall | Icon + small wordmark |
| Browser favicon | 32 px square | Icon only |
| BeMyApp portal listing | Square thumbnail, 256 px | Icon only |
| Slide deck / submission PDF | Centre of title slide, 600 × 200 px | Primary wordmark, on light |

**Critical recognition test**: the icon must be readable at 32 px and instantly recognisable at 16 px. If the icon needs >2 visual elements to read, it's too complex.

## 11. One-line creative brief (TL;DR for the designer)

> *Design a confident, restrained wordmark for OVERRIDE — an explainable AI copilot for race-strategy decisions. The mark should feel like instrument-panel telemetry: precise, geometric, single-accent, no F1 trade-dress. The icon should hint at intentional human intervention — a pressed button, a marked sector, a chosen path — not automation. Wordmark-led, icon-supported. All visuals original.*

## 12. Timeline

- **Now**: brief delivered
- **+5 days**: 3 directional concepts (rough wordmark + icon pairing) for review
- **+7 days**: revisions on chosen direction
- **+10 days**: final files delivered
- **2026-05-31**: demo submission deadline (logo must be in repo + on submission portal)

That gives ~3 weeks total — comfortable but not luxurious. Two rounds of revisions max.

## 13. Final file delivery

Designer to commit (or hand off as zip) to:

```
assets/
├── logo.png            ← primary wordmark, on transparent
├── logo.svg            ← master vector
├── logo-icon.png       ← square icon
├── logo-icon.svg       ← master vector
└── brand/
    ├── logo-on-dark.png
    ├── logo-on-light.png
    ├── logo-mono-black.svg
    ├── logo-mono-white.svg
    ├── icon-on-dark.png
    ├── icon-on-light.png
    ├── icon-mono-black.svg
    └── icon-mono-white.svg
```

---

## Contact / context for the designer

- Project lead: Patrick Ejelle-Ndille (patrick@broadcomms.net)
- Repo: this directory (private until submission)
- Working artifacts to look at: `README.md` (project pitch), `docs/00-abstract.md`, `docs/04-ui-ux-design.md` (already-built UI screenshots in `assets/screenshots/`)
- Existing UI screenshots showing the product's visual language: `assets/screenshots/engineer_mode.png`, `fan-mode.png`, `guardian-rejection.png`, `sessions.png`, `upload.png` — these reflect the current Tailwind palette (slate + accents)

Match the logo to that palette so README + demo video + UI feel of-a-piece.
