# Regulation Source - Verification Gate G-4 (closed)

> Closes verification gate **G-4** in `docs/06-roadmap.md` §4 P2.5 and risks **R13 / R14** in `docs/05-risk-register.md`. Identifies the canonical FIA document that grounds OVERRIDE's regulation citations, the article scope, and the chunking pipeline that produced the committed `data/regs/extracted_chunks.sample.json`.

## Status

| Field | Value |
|---|---|
| Gate | **G-4 - closed** |
| Closed at | 2026-05-08 |
| Re-verified at | 2026-05-09 (refresh to Issue 18) |
| Operator | Patrick Ejelle-Ndille |
| Tracked in chunk JSON | `g4_status: "closed"` |

---

## Verified citation source

**Document.** *FIA 2026 Formula 1 Technical Regulations - Section C, Issue 18, 7 May 2026.*

- Local cache: `data/regs/fia_2026_f1_regulations_-_section_c_technical_-_iss_18_-_2026-05-07.pdf` (gitignored)
- Public source: <https://www.fia.com/regulation/category/110>
- Supersedes Issue 12 (2025-06-10) - re-verified 2026-05-09 after FIA published Issue 18 on 2026-05-07.

**Article in scope.** Energy-management citations resolve to **Article C5 (Power Unit)** - the regulatory chapter that defines the 2026 hybrid power unit, its energy flow accounting, the ERS architecture, the MGU-K deployment envelope, and the energy store bounds. Subsections that ground recommendations:

| Section | Title | What OVERRIDE cites it for |
|---|---|---|
| **C5.2** | Power Unit Energy Flow | MJ accounting, harvest/deploy cap framing |
| **C5.2.6** | Fuel-flow compliance assessment | Used to ground low-ROI deploy / unused-override (Issue 18 retrieval) |
| **C5.2.9** | ES state-of-charge envelope | 4-MJ cycle limit; primary anchor for late-recharge / over-harvest |
| **C5.2.10** | Recharge per-lap cap | The 8.5 MJ/lap cap parsed by `extract_harvest_cap_mj()` |
| **C5.2.14** | ERS Policing | Per-lap cap enforcement / measurement |
| **C5.17** | Energy Recovery System (ERS) | ERS architecture, harvest semantics |
| **C5.18** | MGU-K | Deployment power envelope (350 kW) |
| **C5.19** | Energy Store | SoC bounds, capacity |
| **C5.20** | ES design and installation | Physical battery constraints |

384 chunks captured under Article C5 + the second-copy SECTION-C body - 112 unique sub-section labels. Retrieval (Granite Embedding 278M, threshold 0.3) consistently grounds energy-management zones in C5.2.x subsections (verified 2026-05-09).

**Issue 18 phrasing change.** C5.2.10 wording moved from *"energy harvested by the ERS-K, ... must not exceed 8.5MJ in each lap"* (Issue 12) to *"Recharge, as measured at the CU-K HV DC Bus, must not exceed a limit of 8.5MJ in each lap"* (Issue 18). The cap **value is unchanged** - `extract_harvest_cap_mj()` regex was updated to match both phrasings (see `core/regs.py:_HARVEST_CAP_PRIMARY_RE`).

**What's deliberately out of scope (post-submission upgrade path).** Override Mode availability rules - *"the chasing car is within one second"*, race-start procedures, qualifying mode behaviors - are governed by the **Sporting Regulations**, not the Technical Regulations.

**Section B (Sporting), Issue 06, 2026-04-28** is now cached locally at `data/regs/FIA 2026 F1 Regulations - Section B [Sporting] - Iss 06 - 2026-04-28.pdf`. Integrating it into the chunk corpus would let `unused-override` zones cite real Sporting-Reg clauses ("Override Mode may be deployed when within X seconds of the car ahead") instead of shipping with `regulation_citation = null`. This is **deferred to a post-submission upgrade**: scope expansion at Day 14 of 23, ~3-4 hours of work for a second corpus + per-zone-type retrieval routing, and not strictly required for the rubric story (the architecture already demonstrates dynamic regulation grounding via Section C). Tracked as a follow-up; current behavior remains: `unused-override` ships with `regulation_citation = null` and `confidence = "low"` per `prompts/reasoning.system.md` and the `ReasoningOutput` contract.

---

## Hard rule reaffirmed

Even with G-4 closed, **no FIA article number lives as a hardcoded literal anywhere in this codebase**. Every `RegulationSource.section` value is read at runtime from the Docling extraction. This document specifies *which* document and *which* article scope - but the strings `"C5.17"`, `"C5.18"`, etc. only appear in:

1. The cached PDF (gitignored)
2. The Docling-extracted markdown (gitignored)
3. The committed `data/regs/extracted_chunks.sample.json` (regenerable from #1 + #2)
4. **Nowhere in code, prompts, or templates.**

If you find any of those strings hardcoded in a Python file, prompt, or schema default, that's a bug - file it against the §6 hard rule in `docs/04-schema.md`.

---

## Reproducing the chunk corpus

The committed `data/regs/extracted_chunks.sample.json` was produced by:

```bash
.venv/bin/python scripts/build_chunks.py \
  --pdf data/regs/fia_2026_f1_regulations_-_section_c_technical_-_iss_18_-_2026-05-07.pdf \
  --document-title "FIA 2026 Formula 1 Technical Regulations - Section C" \
  --issue "Issue 18 - 2026-05-07" \
  --section-filter '(\bC5\b|SECTION\s+C:\s*TECHNICAL)' \
  --g4-status closed
```

The `(\bC5\b|SECTION\s+C:\s*TECHNICAL)` regex captures both occurrences of Article C5 in the document (the section index AND the second-copy body block where C5.2.x sub-articles live as bullets under a single `## SECTION C: TECHNICAL REGULATIONS` heading). Output as of 2026-05-09:

- 384 chunks (112 unique section labels)
- mean ~620 chars per chunk
- 768-dim embeddings via `ibm/granite-embedding-278m-multilingual` on watsonx.ai (US-South)
- ~13 s embedding pass + Docling extraction on a CPU laptop
- harvest cap parsed correctly: 8.5 MJ/lap (Issue 18 phrasing: *"Recharge, as measured at the CU-K HV DC Bus, must not exceed a limit of 8.5MJ in each lap"*)

When the FIA publishes a new issue (Issue 19+), regenerate by updating the `--pdf` and `--issue` arguments. The pipeline (chunker, embedder, storage) is the same; the `extract_harvest_cap_mj()` regex tolerates both Issue-12 and Issue-18 phrasings, so future minor wording shifts are absorbed without code change unless they change the cap structure entirely.

---

## What unblocks now that G-4 is closed

1. **`citation_existence` validator rule fires on real chunks.** It auto-passed on the null pathway pre-G-4; now it enforces verbatim-substring matching against the 48 committed chunks.
2. **`source_consistency` validator rule fires.** Citations from Granite must reference one of the 35+ section labels that exist in the chunk corpus.
3. **`harvest_cap` validator rule can leave NOOP mode.** Once the per-lap cap is parsed from C5.2 / C5.2.14 (a P2.6 Pass-2 follow-up), the validator's `pre_g4_behavior: noop` flag rotates to active enforcement. Until parsed: still NOOP, callers pass `cap_mj=None`.
4. **Pass-2 Guardian's `regulation_consistency` scoring becomes meaningful.** Real chunks → Granite Guardian scores citation alignment against actual regulation text rather than auto-passing on the null pathway.
5. **API `regulation_source` field starts surfacing structured data.** Pre-G-4 it was null; post-G-4 the API populates it from `load_chunks()`'s metadata + the cited chunk's `RegulationSource`.
6. **UI banner flips off.** The `04-ui-ux-design.md §7` "Regulation grounding unavailable" banner renders only when `g4_status != "closed"`. With the JSON now flagged closed, the banner stops appearing.

---

## What stays open

- **Sporting Regulations.** Override Mode availability + race-start procedures + qualifying behavior rules need a separate document fetch + extraction + a G-4-equivalent verification. Until then, `unused-override` zones cite nothing. Open as **issue:** *G-4-sporting* (small follow-up; not blocking submission).
- **Per-lap harvest cap value.** C5.2 mentions energy flow accounting but the exact MJ/lap cap (FIA refinements: 8 → 7 MJ in qualifying) lives in nearby tables. A small parser in `core/regs.py` could extract this; for now `cap_mj` stays env-tunable via `OVERRIDE_HARVEST_CAP_MJ` (see `analysis/feature_engineering.py`).
- **Mid-season amendments.** The FIA publishes regulation revisions periodically. The build script regenerates from a new PDF in one command; the public_url stays stable.

---

## References

- Pipeline implementation: `core/regs.py` (chunker + watsonx embedder + retrieval)
- Build script: `scripts/build_chunks.py`
- Validator rules: `core/validator.yaml` + `core/validator.py`
- Schema contracts: `docs/04-schema.md` §6 (hard rule on dynamic citations) + §8 (validator)
- Roadmap entry: `docs/06-roadmap.md` §4 P2.5 + §8 verification-gates table
- ADR: `docs/adrs/ADR-001-watsonx-runtime.md` (embedding model decision)
- Risk register: `docs/05-risk-register.md` R13 (regulation article number wrong) + R14 (FIA PDF redistribution licensing)
