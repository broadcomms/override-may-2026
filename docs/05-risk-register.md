# Risk Register

> Living register of identified risks to the OVERRIDE v1.0 submission (IBM SkillsBuild AI Builders Challenge, May 2026). Each row records a risk, its likelihood/impact rating at the time of identification, the chosen mitigation, and the date by which the mitigation needed to be in place. Rows R13–R18 were added or upgraded during P3.7 audit; mitigations referencing v1.1 features are explicitly tagged.
>

> Section numbering starts at §11 because this register was historically the eleventh section of a larger combined design doc; the earlier sections moved out to dedicated files (`docs/02-*`, `docs/03-*`, `docs/04-*`, `docs/05-security.md`, `docs/06-roadmap.md`, `docs/07-deployment.md`). Cross-referenced from `docs/05-security.md` §"Out of scope" and from each ADR's "Consequences" section that touches a tracked risk.
>

> Per `.bob/rules.md` this file is **not** a transient plan - it survives across PRs.

## 11. Risk Register
 
| ID | Risk | Likelihood | Impact | Mitigation | Decision date |
|---|---|---|---|---|---|
| R1 | TORCS simulator doesn't expose energy state | Medium | High | Derive synthetic energy from throttle/brake integral; document derivation | Day 3 EOD |
| R2 | TTM-R2 lap-aggregation gives poor accuracy | Medium | Medium | TTM is optional. Pipeline runs end-to-end on heuristics alone. UI shows "forecast unavailable" cleanly when TTM is skipped | Day 7 EOD |
| R3 | Docling fails on FIA reg PDF complexity | Low | Medium | Manual extraction of verified section as fallback; still demonstrates Docling concept on a smaller scope | Day 10 EOD |
| R4 | Guardian BYOC scoring is too strict, blocks all output | Medium | High | Pass 1 (deterministic validator) always works regardless of Guardian. Guardian threshold tunable; calibrate on 20 samples | Day 11 EOD |
| R5 | UI takes longer than 4 days | High | High | Drop Fan Mode UI, keep Engineer Mode only; Fan Mode becomes a single example card in the demo | Day 14 EOD |
| R6 | ContextForge setup eats > 1 day | Medium | Low | Skip ContextForge entirely; use direct OpenTelemetry instrumentation in FastAPI for trace screenshot | Day 18 morning |
| R7 | Video runs over 3:00 | Medium | High | **Closed**: final submission video completed and linked through `https://override-video.patrickndille.com`; keep the forwarding URL stable through judging | Final close |
| R8 | Video hosting or processing fails on submission day | Low | High | **Closed**: canonical portal/README link is the forwarding URL `https://override-video.patrickndille.com`, so the underlying host can change without editing submission copy | Final close |
| R9 | Repo missing required README sections | Low | Medium | Use §3 template; lint with §12 checklist | Day 23 EOD |
| R10 | Discord feedback flags an issue late | Medium | Medium | Pitch on Day 2, not later; allows 21+ days for course correction | Day 2 EOD |
| R11 | Solo burnout in week 3 | Medium | High | Day 18 ContextForge decision is also a burnout-relief gate; cut scope, not days off | Day 18 EOD |
| R12 | IBM-Ferrari overlap perception | Low | High | Explicit "What this is not" section in README; Engineer Mode framing in video | Day 23 EOD |
| **R13** | **Regulation article number is wrong / unverifiable** | **Medium** | **High** | **Day 10 verification gate. Generic phrasing in prompts/UI until verified. Citation rendered dynamically from extraction, never hardcoded** | **Day 10 EOD** |
| **R14** | **FIA PDF redistribution licensing risk** | **Low** | **Medium** | **Never commit full PDF. Use `download_regulations.py` + `data/regs/README.md` documenting source. Only commit derivative `extracted_chunks.sample.json`** | **Day 10 EOD** |
| **R15** | **Copyrighted F1 footage in video** | **Low** | **High** | **Closed**: final video uses original TORCS, UI, generated charts, Langflow canvas, and custom animation assets. No broadcast clips. Royalty-free music only | **Final close** |
| **R16** | **watsonx.ai connection or Granite model IDs are wrong** | **Medium** | **Medium** | **Gate G-1: `scripts/test_watsonx.py` returns ✓ before any reasoning code. Model IDs + region + project-ID-var pinned in `models.json`. ADR-001 captures the migration from Ollama** | **G-1 (P1.1)** |
| **R17** | **Granite Guardian 3-8b deprecation (withdrawn 2026-08-08)** | **Low** | **Low** | **Submission window (May 31) is well inside the deprecation window - safe for the build. Track lifecycle docs; migrate to next Guardian release post-submission** | **Post-submission** |
| **R18** | **watsonx.ai network outage or latency spike during the demo** | **Low** | **High** | **Quota exhaustion no longer applies - upgraded to watsonx.ai Essentials tier 2026-05-09 with CA$10 budget alerts on Runtime + Studio. v1.0 mitigations: (1) demo video pre-records the canonical run; (2) `tests/fixtures/layered_defense_demo.json` ships a sample output for offline review; (3) Cloudflare WAF rate-limit on `POST /api/sessions` at ~5 req/min/IP (per 07-deployment.md §2). An application-layer rate-limit guard at FastAPI is deferred to v1.1 - the WAF rule is the v1.0 floor** | **P3.7 + P5.1** |
 
---
